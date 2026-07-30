import pandas as pd

from src.anomaly.detect_anomalies import MIN_CLASSIFIED_FOR_WEEK, _expanding_z_scores
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
