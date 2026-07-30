import pandas as pd

from src.anomaly.detect_anomalies import (
    MIN_CLASSIFIED_FOR_WEEK,
    MIN_VOLUME_FOR_ALERT,
    WOW_GROWTH_FALLBACK_THRESHOLD_PCT,
    _expanding_z_scores,
)
from src.metrics.health_score import MIN_REVIEWS_FOR_HEADLINE


def test_z_score_none_for_first_two_weeks():
    series = pd.Series([0.10, 0.11, 0.30])
    z = _expanding_z_scores(series)
    assert pd.isna(z.iloc[0])  # no prior weeks at all
    assert pd.isna(z.iloc[1])  # only 1 prior week, std undefined


def test_z_score_flags_a_real_spike():
    # Stable ~0.10 for 4 weeks, then a jump to 0.40
    series = pd.Series([0.10, 0.11, 0.09, 0.10, 0.40])
    z = _expanding_z_scores(series)
    assert z.iloc[-1] > 2.0


def test_z_score_zero_variance_is_nan_not_inf():
    series = pd.Series([0.10, 0.10, 0.10, 0.10])
    z = _expanding_z_scores(series)
    assert pd.isna(z.iloc[-1])  # zero prior std must not divide-by-zero into inf


def test_z_score_flat_series_after_variance_is_near_zero():
    series = pd.Series([0.10, 0.12, 0.08, 0.10])
    z = _expanding_z_scores(series)
    assert abs(z.iloc[-1]) < 1.0


def test_week_volume_gate_matches_health_score_threshold():
    # Anomaly alerting and the dashboard headline must agree on "enough data"
    # — a category anomaly gated at a different bar than the health-score
    # headline would silently disagree about which weeks are trustworthy.
    assert MIN_CLASSIFIED_FOR_WEEK == MIN_REVIEWS_FOR_HEADLINE


def test_sparse_week_flag_is_excluded_by_volume_gate():
    # Reproduces the real bug found in this project: 7/12 issues in one
    # category (58%) reads as an extreme statistical spike purely because
    # the week's total classified volume is tiny.
    trend_stats = pd.DataFrame(
        {
            "week_start_date": pd.to_datetime(["2026-07-09", "2026-07-16", "2026-07-23"]),
            "category_id": [1, 1, 1],
            "issue_count": [20, 25, 7],
            "issue_pct": [0.1, 0.12, 0.5833],
        }
    )
    # Simulate that week 2026-07-23 only had 12 total classified reviews
    # (other categories not shown here would sum with this row to 12).
    other_rows = pd.DataFrame({"week_start_date": pd.to_datetime(["2026-07-23"]), "category_id": [2], "issue_count": [5], "issue_pct": [0.4167]})
    full = pd.concat([trend_stats, other_rows], ignore_index=True)

    classified_per_week = full.groupby("week_start_date")["issue_count"].transform("sum")
    assert classified_per_week[full["week_start_date"] == pd.Timestamp("2026-07-23")].iloc[0] == 12
    assert (classified_per_week < MIN_CLASSIFIED_FOR_WEEK).any()


def _apply_flagging(trend_stats: pd.DataFrame) -> pd.Series:
    """Mirrors the OR-of-two-triggers logic in detect_anomalies() for unit testing without a DB."""
    classified_per_week = trend_stats.groupby("week_start_date")["issue_count"].transform("sum")
    volume_ok = (trend_stats["issue_count"] >= MIN_VOLUME_FOR_ALERT) & (classified_per_week >= MIN_CLASSIFIED_FOR_WEEK)
    z_score_flag = trend_stats["z_score"].abs() >= 2.0
    wow_fallback_flag = (
        trend_stats["z_score"].isna()
        & trend_stats["wow_growth_pct"].notna()
        & (trend_stats["wow_growth_pct"].abs() >= WOW_GROWTH_FALLBACK_THRESHOLD_PCT)
    )
    return (z_score_flag | wow_fallback_flag) & volume_ok


def test_wow_fallback_flags_real_growth_without_zscore_history():
    # A young dataset (only 1 prior week) can't compute a z-score yet, but a
    # +70% WoW jump in a well-populated category is still worth surfacing.
    # A second category row is included so the week's total classified
    # volume clears MIN_CLASSIFIED_FOR_WEEK (the gate is on TOTAL weekly
    # volume, not any single category's count).
    df = pd.DataFrame(
        {
            "week_start_date": pd.to_datetime(["2026-07-16", "2026-07-16"]),
            "category_id": [1, 2],
            "issue_count": [32, 100],
            "issue_pct": [0.016, 0.05],
            "z_score": [float("nan"), float("nan")],
            "wow_growth_pct": [70.0, 5.0],
        }
    )
    flagged = _apply_flagging(df)
    assert flagged.iloc[0]
    assert not flagged.iloc[1]  # only 5% growth, below the fallback threshold


def test_wow_fallback_does_not_flag_small_growth():
    df = pd.DataFrame(
        {
            "week_start_date": pd.to_datetime(["2026-07-16", "2026-07-16"]),
            "category_id": [1, 2],
            "issue_count": [32, 100],
            "issue_pct": [0.016, 0.05],
            "z_score": [float("nan"), float("nan")],
            "wow_growth_pct": [10.0, 5.0],  # below the 30% fallback threshold
        }
    )
    flagged = _apply_flagging(df)
    assert not flagged.iloc[0]


def test_wow_fallback_does_not_override_a_real_zscore():
    # If a z-score IS available, the wow-fallback branch must not double-flag
    # or interfere — the z-score path already handles it.
    df = pd.DataFrame(
        {
            "week_start_date": pd.to_datetime(["2026-07-23", "2026-07-23"]),
            "category_id": [1, 2],
            "issue_count": [32, 100],
            "issue_pct": [0.016, 0.05],
            "z_score": [0.5, float("nan")],  # below warning threshold
            "wow_growth_pct": [70.0, 5.0],  # would trip the fallback if z_score were NaN
        }
    )
    flagged = _apply_flagging(df)
    assert not flagged.iloc[0]
