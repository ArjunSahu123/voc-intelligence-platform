"""Deterministic severity-vs-volume prioritization — no LLM call needed.

This is the actual product-analyst judgment layer, separated on purpose from
the LLM-generated per-alert recommendations (recommendations table): those
answer "what caused THIS specific spike," this answers "given everything we
know right now, where should the team spend the next sprint." A classic
2x2 impact/effort-style framework, using real computed metrics as the axes
instead of subjective impact/effort guesses:

  X-axis: issue_pct          — how much of the customer base hits this (reach)
  Y-axis: severity_intensity — average severity weight PER ISSUE in the
                               category (how badly it degrades the experience
                               when it does happen), deliberately NOT the
                               volume-weighted severity_score used elsewhere
                               in this platform — severity_score bakes in
                               issue_count, so plotting it against issue_pct
                               (also volume-based) just re-splits categories
                               by size rather than isolating severity as an
                               independent axis. severity_intensity =
                               severity_score / (100 * issue_pct), which
                               algebraically recovers the category's average
                               severity_weight per issue regardless of volume.

Quadrants (split at the median of each axis, among ACTIONABLE categories —
"General Feedback" is excluded because it's a catch-all bucket for reviews
with no specific complaint, not a fixable problem):

  Fix Now           high reach + high severity  -> broad AND bad. Top priority.
  Quick Wins        high reach + low severity   -> annoys many, breaks nothing.
                                                    Cheap, visible improvement.
  Investigate Deeply low reach + high severity  -> rare but dangerous (fraud,
                                                    safety, data loss). Worth
                                                    understanding even at low
                                                    volume, because severity
                                                    this high usually means
                                                    expensive downstream cost.
  Monitor           low reach + low severity    -> not worth acting on yet;
                                                    watch for growth.

Median-split (not fixed thresholds) is a deliberate choice: it always
produces a meaningful 2x2 regardless of the product's absolute issue rates,
which vary a lot by category/vertical — a fixed "5% = high volume" threshold
would need re-tuning per product, a median split doesn't.
"""
import pandas as pd

from src.common.db import ENGINE
from src.metrics.health_score import select_headline_weeks

EXCLUDED_CATEGORIES = {"General Feedback"}  # catch-all bucket, not an actionable finding


def assign_quadrants(week_df: pd.DataFrame) -> tuple[pd.DataFrame, float, float]:
    """Pure function: takes a DataFrame with issue_pct/severity_score columns,
    returns (df with severity_intensity + quadrant columns added, reach_median, severity_median).
    Separated from build_roadmap() so the quadrant logic is unit-testable without a DB.
    """
    week_df = week_df.copy()
    week_df["severity_intensity"] = week_df["severity_score"] / (100 * week_df["issue_pct"])

    reach_median = week_df["issue_pct"].median()
    severity_median = week_df["severity_intensity"].median()

    def quadrant(row):
        high_reach = row["issue_pct"] >= reach_median
        high_severity = row["severity_intensity"] >= severity_median
        if high_reach and high_severity:
            return "Fix Now"
        if high_reach and not high_severity:
            return "Quick Wins"
        if not high_reach and high_severity:
            return "Investigate Deeply"
        return "Monitor"

    week_df["quadrant"] = week_df.apply(quadrant, axis=1)
    return week_df, reach_median, severity_median


def build_roadmap(week_start_date=None) -> dict:
    query = """
        SELECT it.week_start_date, c.name AS category, c.journey_stage,
               it.issue_count, it.issue_pct, it.severity_score
        FROM issue_trends it JOIN categories c ON c.category_id = it.category_id
    """
    df = pd.read_sql(query, ENGINE, parse_dates=["week_start_date"])
    if df.empty:
        return {"week_start_date": None, "quadrants": {}, "narrative": []}

    if week_start_date:
        target_week = pd.Timestamp(week_start_date)
    else:
        # Default to the same "enough data" headline week the dashboard/report
        # use — not just the latest week, which may be a sparse still-indexing
        # tail (see health_score.select_headline_weeks).
        weekly = pd.read_sql("SELECT week_start_date, total_reviews FROM weekly_metrics", ENGINE, parse_dates=["week_start_date"])
        this_week, _, _ = select_headline_weeks(weekly)
        target_week = this_week["week_start_date"]
    week_df = df[df["week_start_date"] == target_week].copy()
    week_df = week_df[~week_df["category"].isin(EXCLUDED_CATEGORIES)]
    if week_df.empty:
        return {"week_start_date": str(target_week.date()), "quadrants": {}, "narrative": []}

    week_df, reach_median, severity_median = assign_quadrants(week_df)

    quadrants = {}
    for q in ["Fix Now", "Quick Wins", "Investigate Deeply", "Monitor"]:
        subset = week_df[week_df["quadrant"] == q].sort_values("severity_intensity", ascending=False)
        quadrants[q] = subset[
            ["category", "journey_stage", "issue_count", "issue_pct", "severity_score", "severity_intensity"]
        ].round({"severity_intensity": 2}).to_dict(orient="records")

    narrative = []
    if quadrants["Fix Now"]:
        names = ", ".join(r["category"] for r in quadrants["Fix Now"])
        narrative.append(
            f"**Fix Now:** {names} — these hit a wide share of customers AND degrade the experience "
            "badly when they do. Prioritize engineering/ops investigation this sprint; these are the "
            "categories most likely to be denting the Product Health Score directly."
        )
    if quadrants["Quick Wins"]:
        names = ", ".join(r["category"] for r in quadrants["Quick Wins"])
        narrative.append(
            f"**Quick Wins:** {names} — high reach but lower severity. These are usually the cheapest "
            "way to move the needle on overall sentiment: a broad, low-severity friction point is often "
            "a smaller fix (copy, UX nudge, FAQ) than a high-severity one."
        )
    if quadrants["Investigate Deeply"]:
        names = ", ".join(r["category"] for r in quadrants["Investigate Deeply"])
        narrative.append(
            f"**Investigate Deeply:** {names} — low volume but high severity (the kind of category that "
            "includes fraud, safety, or total-failure complaints). Low reach today doesn't mean low risk: "
            "worth a root-cause pass even at small sample size, because severity this high usually means "
            "expensive downstream cost (chargebacks, trust, churn) per incident."
        )
    if quadrants["Monitor"]:
        names = ", ".join(r["category"] for r in quadrants["Monitor"])
        narrative.append(f"**Monitor:** {names} — neither high reach nor high severity right now. Track for growth, no action needed yet.")

    return {
        "week_start_date": str(target_week.date()),
        "reach_median": round(float(reach_median), 4),
        "severity_median": round(float(severity_median), 2),
        "quadrants": quadrants,
        "narrative": narrative,
    }
