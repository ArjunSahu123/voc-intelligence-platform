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

from src.common.db import ENGINE
from src.metrics.health_score import MIN_REVIEWS_FOR_HEADLINE, select_headline_weeks

st.set_page_config(page_title="Voice of Customer Intelligence Platform", layout="wide")


@st.cache_data(ttl=300)
def load_table(query: str, params: dict | None = None) -> pd.DataFrame:
    return pd.read_sql(query, ENGINE, params=params or {})


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


def page_executive_overview(selected_week, weeks_df):
    st.title("Executive Overview")
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

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=weekly["week_start_date"], y=weekly["product_health_score"], name="Health Score", mode="lines+markers"))
    if selected_week is not None:
        fig.add_vline(x=this_week["week_start_date"], line_dash="dash", line_color="orange")
    fig.update_layout(title="Product Health Score Over Time", yaxis_range=[0, 100])
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.line(weekly, x="week_start_date", y="avg_rating", markers=True, title="Average Rating Over Time")
    fig2.update_yaxes(range=[1, 5])
    if selected_week is not None:
        fig2.add_vline(x=this_week["week_start_date"], line_dash="dash", line_color="orange")
    st.plotly_chart(fig2, use_container_width=True)


def page_issue_trends(selected_week, weeks_df):
    st.title("Issue Trends")
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

    fig = px.line(trends, x="week_start_date", y="issue_pct", color="category", markers=True,
                  title="Issue % of Classified Reviews, by Category")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Severity Heatmap (Category x Week)")
    pivot = trends.pivot_table(index="category", columns="week_start_date", values="severity_score", aggfunc="mean")
    if not pivot.empty:
        fig_hm = px.imshow(pivot, aspect="auto", color_continuous_scale="Reds", labels=dict(color="Severity Score"))
        st.plotly_chart(fig_hm, use_container_width=True)

    target_week = selected_week if selected_week is not None else trends["week_start_date"].max()
    st.subheader(f"Week Detail — {pd.Timestamp(target_week).date()}")
    st.dataframe(trends[trends["week_start_date"] == target_week].sort_values("severity_score", ascending=False), use_container_width=True)


def page_customer_journey(selected_week, weeks_df):
    st.title("Customer Journey")
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
    fig = px.bar(trends, x="journey_stage", y="issue_count", title=title)
    st.plotly_chart(fig, use_container_width=True)


def page_ratings(selected_week, weeks_df):
    st.title("Ratings")
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

    by_version = reviews.groupby("app_version")["rating"].agg(["mean", "count"]).reset_index()
    by_version = by_version[by_version["count"] >= 5].sort_values("count", ascending=False).head(15)
    fig2 = px.bar(by_version, x="app_version", y="mean", title="Average Rating by App Version (min 5 reviews)")
    st.plotly_chart(fig2, use_container_width=True)


def page_product_health(selected_week, weeks_df):
    st.title("Product Health Score Breakdown")
    st.markdown(
        "Weighted composite: **40% Ratings + 30% Critical Issues + 20% Trend + 10% Crash Reports** "
        "— see `src/metrics/health_score.py` for the fully documented reasoning behind each weight."
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
        st.info("No alerts for this selection. Run src/alerts/generate_alerts.py after classifying reviews across 2+ weeks.")
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


def page_weekly_changes(selected_week, weeks_df):
    st.title("Weekly Changes")
    trends = load_table(
        """
        SELECT it.week_start_date, c.name AS category, it.issue_pct, it.wow_growth_pct, it.issue_count
        FROM issue_trends it JOIN categories c ON c.category_id = it.category_id
        """
    )
    if trends.empty:
        st.warning("No issue_trends yet.")
        return
    target_week = selected_week if selected_week is not None else trends["week_start_date"].max()
    st.caption(f"Showing changes for week of {pd.Timestamp(target_week).date()}")
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
