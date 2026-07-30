"""Streamlit dashboard — the internal analytics tool a PM would actually use.

Run: streamlit run src/dashboard/app.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # streamlit runs this file directly, not via -m

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.anomaly.detect_anomalies import detect_anomalies
from src.common.db import ENGINE
from src.metrics.health_score import MIN_REVIEWS_FOR_HEADLINE, select_headline_weeks
from src.recommendations.strategic_roadmap import build_roadmap
from src.root_cause.root_cause_analysis import fetch_affected_reviews

st.set_page_config(page_title="Voice of Customer Intelligence Platform", layout="wide")

QUADRANT_COLORS = {"Fix Now": "#d62728", "Quick Wins": "#2ca02c", "Investigate Deeply": "#ff7f0e", "Monitor": "#7f7f7f"}


@st.cache_data(ttl=300)
def load_table(query: str, params: dict | None = None) -> pd.DataFrame:
    return pd.read_sql(query, ENGINE, params=params or {})


@st.cache_data(ttl=300)
def cached_anomalies() -> list[dict]:
    return detect_anomalies()["anomalies"]


@st.cache_data(ttl=300)
def cached_roadmap(week_start_date):
    return build_roadmap(week_start_date)


def get_week_options() -> pd.DataFrame:
    df = load_table("SELECT week_start_date, week_end_date, total_reviews FROM weekly_metrics ORDER BY week_start_date DESC")
    for col in ("week_start_date", "week_end_date"):
        df[col] = pd.to_datetime(df[col])
    return df


def week_bounds(weeks_df: pd.DataFrame, selected_week):
    """Returns (start_ts, end_exclusive_ts) for the selected week, or None if 'All time'."""
    if selected_week is None:
        return None
    row = weeks_df[weeks_df["week_start_date"] == selected_week].iloc[0]
    return row["week_start_date"], row["week_end_date"] + pd.Timedelta(days=1)


def default_target_week(selected_week, weeks_df: pd.DataFrame):
    """The week to show when the user hasn't picked one via the sidebar filter.

    Must NOT be a bare `.max()` on whatever dates happen to be present — that
    silently picks the sparse still-indexing tail week (see
    health_score.select_headline_weeks) rather than the real headline week,
    which is exactly the bug that made Weekly Changes look empty.
    """
    if selected_week is not None:
        return selected_week
    this_week, _, _ = select_headline_weeks(weeks_df)
    return this_week["week_start_date"]


def page_executive_overview(selected_week, weeks_df):
    st.title("Executive Overview")
    st.caption(
        "The headline numbers a PM would check first thing Monday morning: is the product healthier or "
        "worse than last week, and by how much."
    )
    weekly = load_table("SELECT * FROM weekly_metrics ORDER BY week_start_date")
    if weekly.empty:
        st.warning("No weekly_metrics yet — run src/metrics/compute_metrics.py.")
        return

    weekly["week_start_date"] = pd.to_datetime(weekly["week_start_date"])

    if selected_week is None:
        this_week, last_week, excluded_tail = select_headline_weeks(weekly)
        if not excluded_tail.empty:
            st.caption(
                f"Note: {len(excluded_tail)} more recent week(s) starting "
                f"{', '.join(excluded_tail['week_start_date'].dt.date.astype(str))} are excluded from the headline "
                "above — Google Play review indexing lags a few days, so the most recent days always look "
                "artificially sparse until more reviews finish moderation. Shown in the trend charts below instead."
            )
    else:
        weekly_sorted = weekly.sort_values("week_start_date").reset_index(drop=True)
        idx = weekly_sorted.index[weekly_sorted["week_start_date"] == selected_week][0]
        this_week = weekly_sorted.iloc[idx]
        last_week = weekly_sorted.iloc[idx - 1] if idx > 0 else None
        if this_week["total_reviews"] < MIN_REVIEWS_FOR_HEADLINE:
            st.caption(
                f"⚠️ This week has only {int(this_week['total_reviews'])} reviews — below the "
                f"{MIN_REVIEWS_FOR_HEADLINE}-review threshold used for the automatic headline. Numbers below are "
                "real but may swing on small-sample noise."
            )

    cols = st.columns(4)
    cols[0].metric("Product Health Score", f"{this_week['product_health_score']:.1f}/100",
                    delta=None if last_week is None else round(this_week["product_health_score"] - last_week["product_health_score"], 1))
    cols[1].metric("Avg Rating", f"{this_week['avg_rating']:.2f}/5",
                    delta=None if last_week is None else round(this_week["avg_rating"] - last_week["avg_rating"], 2))
    cols[2].metric("Reviews This Week", int(this_week["total_reviews"]))
    cols[3].metric("Critical Issues", int(this_week["critical_issue_count"]))
    st.caption(
        "**Health Score**: weighted composite of ratings, critical issues, trend direction, and crashes (0-100, "
        "higher is better) — see the Product Health page for the full breakdown. **Critical Issues**: reviews "
        "classified as severity='critical' (money lost with no resolution, safety issue, total app failure)."
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=weekly["week_start_date"], y=weekly["product_health_score"], name="Health Score", mode="lines+markers"))
    if selected_week is not None:
        fig.add_vline(x=this_week["week_start_date"], line_dash="dash", line_color="orange")
    fig.update_layout(title="Product Health Score Over Time", yaxis_range=[0, 100])
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Every point is one week's composite score. A falling line means something in the 4 weighted components got worse — check Product Health for which one.")

    fig2 = px.line(weekly, x="week_start_date", y="avg_rating", markers=True, title="Average Rating Over Time")
    fig2.update_yaxes(range=[1, 5])
    if selected_week is not None:
        fig2.add_vline(x=this_week["week_start_date"], line_dash="dash", line_color="orange")
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("Raw average star rating (1-5) across ALL reviews that week, independent of the health score — the number every external stakeholder sees on the Play Store listing.")


def page_issue_trends(selected_week, weeks_df):
    st.title("Issue Trends")
    st.caption(
        "Which stage of the customer journey is generating complaints, and is it getting better or worse "
        "week over week. Use the controls below to focus on specific categories or metrics."
    )
    trends = load_table(
        """
        SELECT it.week_start_date, c.name AS category, c.journey_stage,
               it.issue_count, it.issue_pct, it.severity_score, it.wow_growth_pct, it.z_score
        FROM issue_trends it JOIN categories c ON c.category_id = it.category_id
        """
    )
    if trends.empty:
        st.warning("No issue_trends yet — reviews need to be classified first (src/classification/classify_reviews.py).")
        return

    all_categories = sorted(trends["category"].unique())
    col_a, col_b = st.columns([2, 1])
    with col_a:
        chosen_categories = st.multiselect("Categories to show", all_categories, default=all_categories)
    with col_b:
        metric = st.radio("Metric", ["issue_pct", "severity_score", "issue_count"], horizontal=True)
    metric_labels = {
        "issue_pct": "% of classified reviews that week naming this category",
        "severity_score": "severity-weighted score (low=1, medium=2, high=4, critical=8 issue weight, scaled)",
        "issue_count": "raw count of classified reviews naming this category",
    }

    filtered_trends = trends[trends["category"].isin(chosen_categories)] if chosen_categories else trends
    fig = px.line(filtered_trends, x="week_start_date", y=metric, color="category", markers=True,
                  title=f"{metric} by Category, Over Time")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"y-axis = {metric_labels[metric]}. Toggle categories in the legend, or use the controls above to change what's plotted.")

    st.subheader("Severity Heatmap (Category x Week)")
    st.caption("Darker = more severity-weighted issues that week for that category. Good for spotting a category that's consistently bad vs. one that spiked once.")
    pivot = trends.pivot_table(index="category", columns="week_start_date", values="severity_score", aggfunc="mean")
    if not pivot.empty:
        fig_hm = px.imshow(pivot, aspect="auto", color_continuous_scale="Reds", labels=dict(color="Severity Score"))
        st.plotly_chart(fig_hm, use_container_width=True)

    target_week = default_target_week(selected_week, weeks_df)
    st.subheader(f"Week Detail — {pd.Timestamp(target_week).date()}")
    st.dataframe(trends[trends["week_start_date"] == target_week].sort_values("severity_score", ascending=False), use_container_width=True)


def page_customer_journey(selected_week, weeks_df):
    st.title("Customer Journey")
    st.caption(
        "Every category rolls up to one of 8 journey stages (Discovery, Ordering, Payment, Fulfillment, "
        "Post-Order, Platform, Account, Other) — this view answers 'which PART of the app is hurting us most,' "
        "one level up from individual categories."
    )
    query = """
        SELECT c.journey_stage, SUM(it.issue_count) AS issue_count
        FROM issue_trends it JOIN categories c ON c.category_id = it.category_id
    """
    params = {}
    if selected_week is not None:
        query += " WHERE it.week_start_date = :week"
        params["week"] = str(pd.Timestamp(selected_week).date())
    query += " GROUP BY c.journey_stage ORDER BY issue_count DESC"

    trends = load_table(query, params)
    if trends.empty:
        st.warning("No classified reviews yet.")
        return
    title = f"Issues by Journey Stage — {'All Time' if selected_week is None else pd.Timestamp(selected_week).date()}"
    fig = px.bar(trends, x="journey_stage", y="issue_count", title=title, color="journey_stage")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Bar height = total classified reviews naming any category within that journey stage. This is a sum, so it's driven by volume, not severity — pair with the Strategic Roadmap page for a severity-aware view.")


def page_ratings(selected_week, weeks_df):
    st.title("Ratings")
    st.caption("Raw star-rating distribution, independent of the LLM classification pipeline — every review has a rating even before it's been categorized.")
    reviews = load_table("SELECT rating, review_date, app_version FROM reviews")
    if reviews.empty:
        st.warning("No reviews loaded.")
        return
    reviews["review_date"] = pd.to_datetime(reviews["review_date"])

    bounds = week_bounds(weeks_df, selected_week)
    if bounds is not None:
        start, end = bounds
        reviews = reviews[(reviews["review_date"] >= start) & (reviews["review_date"] < end)]
        if reviews.empty:
            st.warning("No reviews in the selected week.")
            return

    fig = px.histogram(reviews, x="rating", nbins=5, title="Rating Distribution")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"{len(reviews)} reviews. A distribution skewed to 1 and 5 stars (a 'barbell') usually means polarized experiences rather than consistent mediocrity — worth checking Issue Trends for what's driving the 1-star cluster.")

    by_version = reviews.groupby("app_version")["rating"].agg(["mean", "count"]).reset_index()
    by_version = by_version[by_version["count"] >= 5].sort_values("count", ascending=False).head(15)
    fig2 = px.bar(by_version, x="app_version", y="mean", title="Average Rating by App Version (min 5 reviews)")
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("Versions with fewer than 5 reviews are excluded (too noisy to trust an average). A version noticeably lower than its neighbors is a signal to check what shipped in that release.")


def page_product_health(selected_week, weeks_df):
    st.title("Product Health Score Breakdown")
    st.markdown(
        "Weighted composite: **40% Ratings + 30% Critical Issues + 20% Trend + 10% Crash Reports** "
        "— see `src/metrics/health_score.py` for the fully documented reasoning behind each weight."
    )
    st.caption(
        "Ratings weighted highest because it's the number every external stakeholder already sees. Critical "
        "Issues second because those carry direct revenue/trust/legal exposure regardless of volume. Trend "
        "(week-over-week direction) and Crash Reports round it out at lower weight — useful signal, not the "
        "headline metric on their own."
    )
    weekly = load_table("SELECT * FROM weekly_metrics ORDER BY week_start_date")
    if weekly.empty:
        st.warning("No weekly_metrics yet.")
        return
    if selected_week is not None:
        weekly["week_start_date"] = pd.to_datetime(weekly["week_start_date"])
        weekly = weekly[weekly["week_start_date"] == selected_week]
    st.dataframe(weekly, use_container_width=True)


def page_alerts(selected_week, weeks_df):
    st.title("Alerts")
    st.caption(
        "Statistically-gated anomalies (z-score vs. historical baseline, or a WoW-growth fallback when there's "
        "not yet enough history for a baseline) that cleared a minimum volume threshold — see Root Cause & "
        "Recommendations for the evidence and suggested fix behind each one."
    )
    query = """
        SELECT a.*, c.name AS category
        FROM alerts a LEFT JOIN categories c ON c.category_id = a.category_id
    """
    params = {}
    if selected_week is not None:
        query += " WHERE a.week_start_date = :week"
        params["week"] = str(pd.Timestamp(selected_week).date())
    query += " ORDER BY a.detected_at DESC"

    alerts = load_table(query, params)
    if alerts.empty:
        st.info("No LLM-analyzed alerts for this selection yet. See the Root Cause & Recommendations page for statistically-detected anomalies awaiting analysis.")
        return

    for _, a in alerts.iterrows():
        badge = {"critical": "🔴", "warning": "🟠", "info": "🔵"}.get(a["severity"], "⚪")
        with st.expander(f"{badge} [{a['status'].upper()}] {a['metric_name']} — week of {a['week_start_date']}"):
            st.write(f"**z-score:** {a['z_score']}  |  **current value:** {a['current_value']}")
            st.write(f"**Root cause:** {a['root_cause_summary']}")
            if a.get("representative_quotes"):
                try:
                    quotes = json.loads(a["representative_quotes"])
                    for q in quotes:
                        st.markdown(f"> {q}")
                except (TypeError, json.JSONDecodeError):
                    pass


def page_root_cause(selected_week, weeks_df):
    st.title("Root Cause & Recommendations")
    st.caption(
        "The structured investigation behind each flagged issue: what happened, how it was broken down, what "
        "the evidence actually says, and what to do about it — the same process a PM would run manually, "
        "automated end to end."
    )

    anomalies = cached_anomalies()
    if not anomalies:
        st.info("No statistically-flagged anomalies right now — either everything is stable, or there isn't yet enough history/volume to detect one (see Alerts page caption).")
        return

    category_names = load_table("SELECT category_id, name FROM categories").set_index("category_id")["name"].to_dict()
    existing_alerts = load_table(
        """
        SELECT a.week_start_date, a.category_id, a.root_cause_summary, a.representative_quotes,
               r.title, r.customer_impact, r.business_impact, r.recommended_investigation,
               r.suggested_fix, r.metrics_to_monitor
        FROM alerts a LEFT JOIN recommendations r ON r.alert_id = a.alert_id
        """
    )

    for anomaly in anomalies:
        category = category_names.get(anomaly["category_id"], "Overall Ratings")
        week = anomaly["week_start_date"]
        method = anomaly.get("detection_method", "z_score")

        st.subheader(f"{'🔴' if anomaly['severity']=='critical' else '🟠'} {category} — week of {week}")

        st.markdown("**1. Problem Statement**")
        if method == "wow_growth_fallback":
            st.write(
                f"{category} grew {anomaly['wow_growth_pct']:+.0f}% week-over-week "
                f"({anomaly['issue_count']} issues, {anomaly['current_value']*100:.1f}% of classified reviews that week). "
                "Flagged by growth threshold — not enough historical weeks yet for a full statistical (z-score) baseline."
            )
        else:
            st.write(
                f"{category} issue rate is {abs(anomaly['z_score']):.1f} standard deviations "
                f"{'above' if anomaly['z_score'] > 0 else 'below'} its historical average "
                f"({anomaly['current_value']*100:.1f}% of classified reviews that week, {anomaly['issue_count']} issues)."
            )

        st.markdown("**2. How This Was Structured**")
        st.write(
            f"Isolated to a single category ({category}) rather than treated as a general rating drop — "
            "this separates 'is it broad-based across the product or concentrated in one journey stage' before "
            "looking for a cause. Volume-gated (minimum issue count AND minimum total classified reviews that "
            "week) so the finding isn't small-sample noise."
        )

        match = existing_alerts[
            (existing_alerts["week_start_date"] == str(week)) & (existing_alerts["category_id"] == anomaly["category_id"])
        ] if not existing_alerts.empty else pd.DataFrame()

        st.markdown("**3. Evidence**")
        if not match.empty and pd.notna(match.iloc[0]["root_cause_summary"]):
            row = match.iloc[0]
            st.write(row["root_cause_summary"])
            if pd.notna(row["representative_quotes"]):
                try:
                    for q in json.loads(row["representative_quotes"]):
                        st.markdown(f"> {q}")
                except (TypeError, json.JSONDecodeError):
                    pass
        else:
            sample_reviews = fetch_affected_reviews(anomaly)
            if not sample_reviews.empty:
                st.caption("Raw evidence (LLM theme summary pending — quota not yet available):")
                for r in sample_reviews.head(3).itertuples():
                    st.markdown(f"> ({r.rating}/5) \"{r.content_clean[:200]}\"")
            else:
                st.caption("No affected reviews retrieved.")

        st.markdown("**4. Recommendation**")
        if not match.empty and pd.notna(match.iloc[0]["title"]):
            row = match.iloc[0]
            st.write(f"**{row['title']}**")
            st.write(f"Customer impact: {row['customer_impact']}")
            st.write(f"Business impact: {row['business_impact']}")
            st.write(f"Suggested fix: {row['suggested_fix']}")
            st.write(f"Metrics to monitor: {row['metrics_to_monitor']}")
        else:
            st.caption("Pending — run `src/alerts/generate_alerts.py` once LLM API quota is available to generate a data-backed recommendation for this finding.")

        st.divider()


def page_strategic_roadmap(selected_week, weeks_df):
    st.title("Strategic Roadmap")
    st.caption(
        "Where should the team spend the next sprint, given everything we know right now — a reach-vs-severity "
        "prioritization matrix computed directly from real data, no LLM involved. Answers 'what's next,' as "
        "opposed to Root Cause & Recommendations, which answers 'what happened with THIS specific spike.'"
    )

    roadmap = cached_roadmap(str(selected_week.date()) if selected_week is not None else None)
    if not roadmap["quadrants"]:
        st.warning("No classified issue data yet.")
        return

    st.caption(f"Based on week of {roadmap['week_start_date']} — the same headline week shown on Executive Overview.")

    rows = []
    for quadrant, items in roadmap["quadrants"].items():
        for item in items:
            rows.append({**item, "quadrant": quadrant})
    plot_df = pd.DataFrame(rows)

    fig = px.scatter(
        plot_df, x="issue_pct", y="severity_intensity", color="quadrant", text="category",
        color_discrete_map=QUADRANT_COLORS, size="issue_count", size_max=40,
        title="Reach (issue %) vs. Severity Intensity (avg severity per issue)",
    )
    fig.add_vline(x=roadmap["reach_median"], line_dash="dot", line_color="gray")
    fig.add_hline(y=roadmap["severity_median"], line_dash="dot", line_color="gray")
    fig.update_traces(textposition="top center")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Dot size = issue volume. Dotted lines = median split (see src/recommendations/strategic_roadmap.py for "
        "why median-split, and why severity is measured per-issue rather than volume-weighted)."
    )

    st.subheader("Recommendations")
    for line in roadmap["narrative"]:
        st.markdown(line)

    st.subheader("Full Breakdown")
    for quadrant in ["Fix Now", "Quick Wins", "Investigate Deeply", "Monitor"]:
        items = roadmap["quadrants"].get(quadrant, [])
        if items:
            st.markdown(f"**{quadrant}**")
            st.dataframe(pd.DataFrame(items), use_container_width=True)


def page_weekly_changes(selected_week, weeks_df):
    st.title("Weekly Changes")
    st.caption("Which categories moved the most vs. the prior week — the first place to look when the Executive Overview health score changes.")
    trends = load_table(
        """
        SELECT it.week_start_date, c.name AS category, it.issue_pct, it.wow_growth_pct, it.issue_count
        FROM issue_trends it JOIN categories c ON c.category_id = it.category_id
        """
    )
    if trends.empty:
        st.warning("No issue_trends yet.")
        return
    target_week = default_target_week(selected_week, weeks_df)
    st.caption(f"Showing changes for week of {pd.Timestamp(target_week).date()} (categories with fewer than 3 classified issues are excluded as too noisy to trust)")
    latest = trends[(trends["week_start_date"] == target_week) & (trends["issue_count"] >= 3)]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📈 Declining (getting worse)")
        st.dataframe(latest[latest["wow_growth_pct"] > 0].sort_values("wow_growth_pct", ascending=False), use_container_width=True)
    with col2:
        st.subheader("📉 Improving")
        st.dataframe(latest[latest["wow_growth_pct"] < 0].sort_values("wow_growth_pct"), use_container_width=True)


def page_experiments(selected_week, weeks_df):
    st.title("Experiments (A/B Test Proposals)")
    st.caption("Turns a recommendation into a rigorous test: real power-analysis sample sizes (scipy, not an LLM guess), guardrail metrics, and a rollout plan.")
    experiments = load_table(
        """
        SELECT e.*, r.title AS recommendation_title
        FROM experiments e LEFT JOIN recommendations r ON r.recommendation_id = e.recommendation_id
        ORDER BY e.created_at DESC
        """
    )
    if experiments.empty:
        st.info("No experiments proposed yet. Run src/experiments/ab_test_design.py <recommendation_id>.")
        return

    bounds = week_bounds(weeks_df, selected_week)
    if bounds is not None:
        start, end = bounds
        experiments["created_at"] = pd.to_datetime(experiments["created_at"])
        experiments = experiments[(experiments["created_at"] >= start) & (experiments["created_at"] < end)]
        if experiments.empty:
            st.info("No experiments were created during the selected week.")
            return

    for _, e in experiments.iterrows():
        with st.expander(f"🧪 {e['recommendation_title'] or 'Experiment #' + str(e['experiment_id'])}"):
            st.write(f"**Hypothesis:** {e['hypothesis']}")
            st.write(f"**Primary metric:** {e['primary_metric']}")
            st.write(f"**Sample size / variant:** {e['sample_size_per_variant']}  |  **Duration:** {e['duration_days']} days")
            st.write(f"**Baseline rate:** {e['baseline_rate']*100:.1f}%  |  **MDE:** {e['mde_pct']:.0f}% relative")
            st.write(f"**Success criteria:** {e['success_criteria']}")
            st.write(f"**Rollout plan:** {e['rollout_plan']}")


def page_review_explorer(selected_week, weeks_df):
    st.title("Review Explorer")
    st.caption("Every classified review, filterable — for spot-checking whether the automated classification agrees with your own reading of the raw text.")
    reviews = load_table(
        """
        SELECT r.review_id, r.review_date, r.rating, r.app_version, r.content_clean,
               c.name AS category, rc.severity, rc.sentiment
        FROM reviews r
        LEFT JOIN review_classifications rc ON rc.review_id = r.review_id
        LEFT JOIN categories c ON c.category_id = rc.primary_category_id
        """,
    )
    if reviews.empty:
        st.warning("No reviews loaded.")
        return
    reviews["review_date"] = pd.to_datetime(reviews["review_date"])

    min_date, max_date = reviews["review_date"].min(), reviews["review_date"].max()
    bounds = week_bounds(weeks_df, selected_week)
    default_range = (
        (pd.to_datetime(min_date).date(), pd.to_datetime(max_date).date())
        if bounds is None
        else (bounds[0].date(), (bounds[1] - pd.Timedelta(days=1)).date())
    )

    with st.sidebar:
        st.subheader("Filters")
        date_range = st.date_input("Date range", default_range)
        ratings = st.multiselect("Rating", sorted(reviews["rating"].unique()), default=sorted(reviews["rating"].unique()))
        versions = st.multiselect("App version", sorted(reviews["app_version"].dropna().unique()))
        categories = st.multiselect("Issue category", sorted(reviews["category"].dropna().unique()))
        severities = st.multiselect("Severity", sorted(reviews["severity"].dropna().unique()))

    filtered = reviews.copy()
    if len(date_range) == 2:
        filtered = filtered[
            (filtered["review_date"] >= pd.Timestamp(date_range[0]))
            & (filtered["review_date"] <= pd.Timestamp(date_range[1]) + pd.Timedelta(days=1))
        ]
    if ratings:
        filtered = filtered[filtered["rating"].isin(ratings)]
    if versions:
        filtered = filtered[filtered["app_version"].isin(versions)]
    if categories:
        filtered = filtered[filtered["category"].isin(categories)]
    if severities:
        filtered = filtered[filtered["severity"].isin(severities)]

    st.write(f"{len(filtered)} reviews match filters")
    st.dataframe(filtered.sort_values("review_date", ascending=False), use_container_width=True, height=600)


PAGES = {
    "Executive Overview": page_executive_overview,
    "Issue Trends": page_issue_trends,
    "Customer Journey": page_customer_journey,
    "Strategic Roadmap": page_strategic_roadmap,
    "Root Cause & Recommendations": page_root_cause,
    "Ratings": page_ratings,
    "Product Health": page_product_health,
    "Alerts": page_alerts,
    "Weekly Changes": page_weekly_changes,
    "Experiments": page_experiments,
    "Review Explorer": page_review_explorer,
}

with st.sidebar:
    st.title("VoC Intelligence")
    selected = st.radio("Page", list(PAGES.keys()))

    st.divider()
    st.subheader("Week")
    weeks_df = get_week_options()
    if weeks_df.empty:
        selected_week = None
        st.caption("No weeks computed yet.")
    else:
        week_choices = ["All time"] + list(weeks_df["week_start_date"])
        week_pick = st.selectbox(
            "Filter to a specific week",
            week_choices,
            format_func=lambda w: "All time" if w == "All time" else (
                f"Week of {pd.Timestamp(w).date()} "
                f"({int(weeks_df.loc[weeks_df['week_start_date'] == w, 'total_reviews'].iloc[0])} reviews)"
            ),
        )
        selected_week = None if week_pick == "All time" else week_pick

PAGES[selected](selected_week, weeks_df)
