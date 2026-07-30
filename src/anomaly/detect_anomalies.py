"""Statistical anomaly detection over weekly issue trends and ratings.

Methodology (documented per the project brief, not just implemented):

- For each category, at each week, we compare against an EXPANDING window of
  all prior weeks (not a fixed trailing window) because a young product
  analytics deployment starts with very little history — a fixed 4-week
  rolling window would report "insufficient data" for a category's first
  month. As more weeks accumulate this naturally becomes a longer, more
  stable baseline. (Documented future improvement: once 12+ weeks of history
  exist, switch to a trailing 8-week window so the baseline adapts to slow
  seasonal drift instead of being diluted by the product's entire past.)
- z_score = (this week's value - mean of prior weeks) / std of prior weeks.
  Requires at least 2 prior weeks (std of 1 point is undefined) — earlier
  weeks get z_score = None, which callers must treat as "not enough history
  yet," not "no anomaly."
- wow_growth_pct = week-over-week % change, needs only 1 prior week.
- A z_score alone can flag noise from tiny categories (2 reviews -> 4 reviews
  is a 100% "spike" that means nothing). MIN_VOLUME_FOR_ALERT gates alerting
  on absolute issue_count, not just the statistical score. That alone is
  still not enough, though: a category can clear MIN_VOLUME_FOR_ALERT while
  the WEEK it belongs to is itself tiny (e.g. 7 issues out of just 12 total
  classified reviews that week — a swing driven entirely by small-sample
  noise, observed directly in this project's data from Google Play's
  review-indexing lag). MIN_CLASSIFIED_FOR_WEEK additionally gates on the
  week's total classified volume (the denominator behind issue_pct), same
  reasoning as MIN_REVIEWS_FOR_HEADLINE in health_score.py.
- Fallback trigger when z_score is unavailable (fewer than 2 prior weeks of
  history — true for any category in a deployment's first ~3 weeks):
  WOW_GROWTH_FALLBACK_THRESHOLD_PCT flags a category whose issue_pct grew
  by a large relative amount week-over-week, even without a full
  statistical baseline. This is a deliberately weaker signal than a z-score
  anomaly (no notion of "how unusual is this given historical variance"),
  so it's capped at "warning" severity regardless of magnitude and tagged
  with detection_method="wow_growth_fallback" so a PM can tell the two
  apart. Without this, a real, sizable swing in a brand-new product's first
  month would never surface until 3+ weeks of history accumulate — too
  slow to be useful when it matters most.

This module only computes statistics and writes them back onto issue_trends
/ weekly_metrics; deciding which anomalies become Alert rows is
src/alerts/generate_alerts.py's job (separate module so "what counts as
statistically unusual" and "what's worth paging a PM about" can evolve
independently).
"""
import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.common.db import ENGINE
from src.common.models import IssueTrend
from src.metrics.health_score import MIN_REVIEWS_FOR_HEADLINE

Z_SCORE_WARNING_THRESHOLD = 2.0
Z_SCORE_CRITICAL_THRESHOLD = 3.0
MIN_VOLUME_FOR_ALERT = 5  # minimum issue_count in the week for a category anomaly to be actionable
MIN_REVIEWS_FOR_RATING_ALERT = 30  # a week with fewer reviews than this can swing wildly on noise alone
MIN_CLASSIFIED_FOR_WEEK = MIN_REVIEWS_FOR_HEADLINE  # same threshold health_score.py uses for "enough data"
WOW_GROWTH_FALLBACK_THRESHOLD_PCT = 30.0  # relative growth that flags a category when no z-score baseline exists yet


def _expanding_z_scores(series: pd.Series) -> pd.Series:
    prior_mean = series.expanding().mean().shift(1)
    prior_std = series.expanding().std().shift(1)
    z = (series - prior_mean) / prior_std
    return z.where(prior_std > 0)  # undefined (0 or 1 prior points, or zero variance) -> NaN


def compute_issue_trend_stats() -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT trend_id, week_start_date, category_id, issue_count, issue_pct FROM issue_trends",
        ENGINE,
        parse_dates=["week_start_date"],
    )
    if df.empty:
        return df

    df = df.sort_values(["category_id", "week_start_date"])
    df["wow_growth_pct"] = df.groupby("category_id")["issue_pct"].pct_change() * 100
    df["z_score"] = df.groupby("category_id")["issue_pct"].transform(_expanding_z_scores)
    return df


def compute_weekly_metric_stats() -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT metric_id, week_start_date, avg_rating, negative_review_ratio, total_reviews FROM weekly_metrics",
        ENGINE,
        parse_dates=["week_start_date"],
    )
    if df.empty:
        return df

    df = df.sort_values("week_start_date")
    df["rating_z_score"] = _expanding_z_scores(df["avg_rating"])
    df["negative_ratio_z_score"] = _expanding_z_scores(df["negative_review_ratio"])
    return df


def _write_back(model, df: pd.DataFrame, id_col: str, cols: list[str]):
    if df.empty:
        return
    rows = df[[id_col] + cols].replace({float("nan"): None}).to_dict(orient="records")
    with ENGINE.begin() as conn:
        for row in rows:
            pk_val = row.pop(id_col)
            conn.execute(model.__table__.update().where(getattr(model, id_col) == pk_val).values(**row))


def detect_anomalies() -> dict:
    trend_stats = compute_issue_trend_stats()
    metric_stats = compute_weekly_metric_stats()

    _write_back(IssueTrend, trend_stats, "trend_id", ["wow_growth_pct", "z_score"])
    # rating_z_score / negative_ratio_z_score are derived signals used only to build the
    # anomalies list below — weekly_metrics has no column for them, so nothing is written back.

    anomalies = []

    if not trend_stats.empty:
        # Total classified reviews that week = sum of issue_count across all
        # categories that week (every classified review has exactly one
        # primary category).
        classified_per_week = trend_stats.groupby("week_start_date")["issue_count"].transform("sum")
        volume_ok = (trend_stats["issue_count"] >= MIN_VOLUME_FOR_ALERT) & (classified_per_week >= MIN_CLASSIFIED_FOR_WEEK)

        z_score_flag = trend_stats["z_score"].abs() >= Z_SCORE_WARNING_THRESHOLD
        wow_fallback_flag = (
            trend_stats["z_score"].isna()
            & trend_stats["wow_growth_pct"].notna()
            & (trend_stats["wow_growth_pct"].abs() >= WOW_GROWTH_FALLBACK_THRESHOLD_PCT)
        )

        flagged = trend_stats[(z_score_flag | wow_fallback_flag) & volume_ok]
        for _, row in flagged.iterrows():
            has_z_score = pd.notna(row["z_score"])
            if has_z_score:
                severity = "critical" if abs(row["z_score"]) >= Z_SCORE_CRITICAL_THRESHOLD else "warning"
                detection_method = "z_score"
            else:
                severity = "warning"  # wow-growth fallback is a weaker signal, never auto-escalated to critical
                detection_method = "wow_growth_fallback"

            anomalies.append(
                {
                    "type": "issue_spike",
                    "week_start_date": row["week_start_date"].date(),
                    "category_id": int(row["category_id"]),
                    "z_score": round(float(row["z_score"]), 2) if has_z_score else None,
                    "wow_growth_pct": round(float(row["wow_growth_pct"]), 1) if pd.notna(row["wow_growth_pct"]) else None,
                    "current_value": float(row["issue_pct"]),
                    "issue_count": int(row["issue_count"]),
                    "severity": severity,
                    "detection_method": detection_method,
                }
            )

    if not metric_stats.empty:
        rating_drops = metric_stats[
            (metric_stats["rating_z_score"] <= -Z_SCORE_WARNING_THRESHOLD)
            & (metric_stats["total_reviews"] >= MIN_REVIEWS_FOR_RATING_ALERT)
        ]
        for _, row in rating_drops.iterrows():
            severity = "critical" if row["rating_z_score"] <= -Z_SCORE_CRITICAL_THRESHOLD else "warning"
            anomalies.append(
                {
                    "type": "rating_drop",
                    "week_start_date": row["week_start_date"].date(),
                    "category_id": None,
                    "z_score": round(float(row["rating_z_score"]), 2),
                    "wow_growth_pct": None,
                    "current_value": float(row["avg_rating"]),
                    "issue_count": None,
                    "severity": severity,
                    "detection_method": "z_score",
                }
            )

    return {"anomalies": anomalies, "weeks_analyzed": len(metric_stats)}


def main():
    result = detect_anomalies()
    print(f"Analyzed {result['weeks_analyzed']} weeks, found {len(result['anomalies'])} anomalies.")
    for a in result["anomalies"]:
        print(f"  {a}")


if __name__ == "__main__":
    main()
