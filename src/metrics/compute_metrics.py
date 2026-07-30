"""Computes weekly_metrics and issue_trends from reviews + classifications.

Denominator choice, stated explicitly because it matters: `issue_pct` and the
health-score ratio inputs are computed against `total_classified` (reviews
that have gone through the LLM classifier that week), not `total_reviews`
(every review scraped that week). If only a sample of a week's reviews has
been classified so far, using total_reviews would silently understate every
issue percentage. avg_rating and negative_review_ratio, by contrast, use
every review (rating requires no classification).

Idempotent: re-running recomputes and upserts every week present in the
data, so it can safely run after every classification batch.

Week bucketing: TRAILING windows anchored to the most recent review in the
dataset, not fixed Monday-Sunday calendar weeks. A calendar-week scheme
truncates whatever week contains "now" to however many days have elapsed
since that Monday — for a scrape that runs mid-week, the most recent
(and most dashboard-visible) bucket ends up an arbitrary partial slice
(e.g. 2 days' worth of reviews), which then reads as a wild swing in
avg_rating/health score purely from small-sample noise, not a real signal.
Anchoring windows to end at the latest scraped review instead means the
"current" window is always a full WINDOW_DAYS-day period. The tradeoff:
re-running the pipeline after new reviews arrive shifts every window's
boundaries (since the anchor moves), so week_start_date values are not
stable across runs the way calendar weeks would be — acceptable here
because weekly_metrics/issue_trends are fully recomputed from raw reviews
every run anyway, not incrementally appended to.
"""
import argparse

import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.common.db import ENGINE
from src.common.models import WeeklyMetric, IssueTrend
from src.metrics.health_score import compute_health_score

SEVERITY_WEIGHTS = {"low": 1, "medium": 2, "high": 4, "critical": 8}
WINDOW_DAYS = 7


def _assign_trailing_windows(review_dates: pd.Series, window_days: int = WINDOW_DAYS) -> pd.Series:
    anchor = review_dates.max().normalize()
    days_before_anchor = (anchor - review_dates.dt.normalize()).dt.days
    window_idx = days_before_anchor // window_days
    return anchor - pd.to_timedelta(window_idx * window_days + (window_days - 1), unit="D")


def _load_joined() -> pd.DataFrame:
    query = """
        SELECT
            r.review_id, r.rating, r.review_date,
            rc.severity, rc.sentiment,
            c.name AS primary_category
        FROM reviews r
        LEFT JOIN review_classifications rc ON rc.review_id = r.review_id
        LEFT JOIN categories c ON c.category_id = rc.primary_category_id
    """
    df = pd.read_sql(query, ENGINE, parse_dates=["review_date"])
    df["week_start_date"] = _assign_trailing_windows(df["review_date"])
    return df


def _upsert(model, rows: list[dict], conflict_cols: list[str]):
    if not rows:
        return
    with ENGINE.begin() as conn:
        stmt = sqlite_insert(model.__table__).values(rows)
        update_cols = {c.name: stmt.excluded[c.name] for c in model.__table__.columns if c.name not in conflict_cols}
        stmt = stmt.on_conflict_do_update(index_elements=conflict_cols, set_=update_cols)
        conn.execute(stmt)


def compute_weekly_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    weeks = sorted(df["week_start_date"].unique())
    prev_negative_ratio = None

    for week_start in weeks:
        week_df = df[df["week_start_date"] == week_start]
        total_reviews = len(week_df)
        avg_rating = week_df["rating"].mean()
        negative_ratio = (week_df["rating"] <= 2).sum() / total_reviews

        classified = week_df[week_df["primary_category"].notna()]
        total_classified = len(classified)
        crash_mentions = int((classified["primary_category"] == "App Crash").sum())
        critical_issue_count = int((classified["severity"] == "critical").sum())

        health = compute_health_score(
            avg_rating=avg_rating,
            critical_issue_count=critical_issue_count,
            crash_mentions=crash_mentions,
            total_classified=total_classified,
            negative_ratio_this_week=negative_ratio,
            negative_ratio_last_week=prev_negative_ratio,
        )
        prev_negative_ratio = negative_ratio

        week_end = week_start + pd.Timedelta(days=6)
        days_in_week = (min(week_end, df["review_date"].max()) - week_start).days + 1
        days_in_week = max(days_in_week, 1)

        rows.append(
            {
                "week_start_date": week_start.date(),
                "week_end_date": week_end.date(),
                "total_reviews": total_reviews,
                "avg_rating": round(float(avg_rating), 3),
                "negative_review_ratio": round(float(negative_ratio), 4),
                "reviews_per_day": round(total_reviews / days_in_week, 2),
                "crash_mentions": crash_mentions,
                "critical_issue_count": critical_issue_count,
                "product_health_score": health["overall"],
            }
        )

    return pd.DataFrame(rows)


def compute_issue_trends(df: pd.DataFrame) -> pd.DataFrame:
    from src.common.db import session_scope
    from src.common.models import Category

    with session_scope() as session:
        category_ids = {c.name: c.category_id for c in session.query(Category).all()}

    classified = df[df["primary_category"].notna()].copy()
    classified["severity_weight"] = classified["severity"].map(SEVERITY_WEIGHTS).fillna(1)

    rows = []
    for week_start, week_df in classified.groupby("week_start_date"):
        total_classified_week = len(week_df)
        for category, cat_df in week_df.groupby("primary_category"):
            issue_count = len(cat_df)
            issue_pct = issue_count / total_classified_week
            severity_score = round(100 * cat_df["severity_weight"].sum() / total_classified_week, 2)
            rows.append(
                {
                    "week_start_date": week_start.date(),
                    "category_id": category_ids[category],
                    "issue_count": issue_count,
                    "issue_pct": round(issue_pct, 4),
                    "severity_score": severity_score,
                }
            )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Compute weekly_metrics and issue_trends from the DB.")
    parser.parse_args()

    df = _load_joined()
    if df.empty:
        print("No reviews in the database yet.")
        return

    weekly = compute_weekly_metrics(df)
    trends = compute_issue_trends(df)

    _upsert(WeeklyMetric, weekly.to_dict(orient="records"), ["week_start_date"])
    _upsert(IssueTrend, trends.to_dict(orient="records"), ["week_start_date", "category_id"])

    print(f"Computed {len(weekly)} weekly_metrics rows and {len(trends)} issue_trends rows.")


if __name__ == "__main__":
    main()
