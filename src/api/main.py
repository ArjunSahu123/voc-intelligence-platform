"""FastAPI service exposing the platform's computed state to any consumer
(dashboard, PM-facing internal tool, Slack bot, etc.) — the DB stays the
single source of truth, this is a read layer over it.

Run: uvicorn src.api.main:app --reload --port 8000
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.common.config import REPORTS_DIR
from src.common.db import ENGINE, init_db
from src.metrics.health_score import (
    crash_subscore,
    critical_subscore,
    rating_subscore,
    select_headline_weeks,
    trend_subscore,
)

app = FastAPI(
    title="Voice of Customer Intelligence Platform API",
    description="Product health, issue trends, alerts, and recommendations derived from customer reviews.",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    init_db()


def _df(query: str, params: dict | None = None) -> pd.DataFrame:
    return pd.read_sql(query, ENGINE, params=params or {})


@app.get("/latest-health")
def latest_health():
    weeks = _df("SELECT * FROM weekly_metrics ORDER BY week_start_date")
    if weeks.empty:
        raise HTTPException(404, "No weekly_metrics computed yet.")
    this_week, last_week, excluded_tail = select_headline_weeks(weeks)

    classified = _df(
        "SELECT COUNT(*) AS n FROM review_classifications rc "
        "JOIN reviews r ON r.review_id = rc.review_id WHERE r.review_date >= :ws AND r.review_date < :we",
        {"ws": str(this_week["week_start_date"]), "we": str(pd.Timestamp(this_week["week_start_date"]) + pd.Timedelta(days=7))},
    )
    total_classified = int(classified["n"].iloc[0]) if not classified.empty else 0

    subscores = {
        "rating_subscore": rating_subscore(this_week["avg_rating"]),
        "critical_subscore": critical_subscore(int(this_week["critical_issue_count"]), total_classified),
        "crash_subscore": crash_subscore(int(this_week["crash_mentions"]), total_classified),
        "trend_subscore": trend_subscore(
            this_week["negative_review_ratio"], last_week["negative_review_ratio"] if last_week is not None else None
        ),
    }

    return {
        "week_start_date": str(pd.Timestamp(this_week["week_start_date"]).date()),
        "product_health_score": this_week["product_health_score"],
        "subscores": {k: round(v, 1) for k, v in subscores.items()},
        "avg_rating": this_week["avg_rating"],
        "total_reviews": int(this_week["total_reviews"]),
        "critical_issue_count": int(this_week["critical_issue_count"]),
        "crash_mentions": int(this_week["crash_mentions"]),
        "previous_week_health_score": last_week["product_health_score"] if last_week is not None else None,
        "still_indexing_tail_weeks": excluded_tail["week_start_date"].astype(str).tolist(),
    }


@app.get("/issues")
def issues(week: str | None = Query(None, description="ISO date of the week_start_date; defaults to latest.")):
    if week is None:
        latest = _df("SELECT MAX(week_start_date) AS w FROM issue_trends")
        if latest.empty or latest["w"].iloc[0] is None:
            return {"week": None, "issues": []}
        week = latest["w"].iloc[0]

    df = _df(
        """
        SELECT it.week_start_date, c.name AS category, c.journey_stage, it.issue_count,
               it.issue_pct, it.severity_score, it.wow_growth_pct, it.z_score
        FROM issue_trends it JOIN categories c ON c.category_id = it.category_id
        WHERE it.week_start_date = :week
        ORDER BY it.severity_score DESC
        """,
        {"week": week},
    )
    return {"week": week, "issues": df.to_dict(orient="records")}


@app.get("/trends")
def trends(category: str | None = None, weeks: int = 12):
    query = """
        SELECT it.week_start_date, c.name AS category, it.issue_count, it.issue_pct, it.severity_score, it.wow_growth_pct
        FROM issue_trends it JOIN categories c ON c.category_id = it.category_id
    """
    params = {}
    if category:
        query += " WHERE c.name = :category"
        params["category"] = category
    query += " ORDER BY it.week_start_date DESC"

    df = _df(query, params)
    if not df.empty:
        weeks_available = sorted(df["week_start_date"].unique())[-weeks:]
        df = df[df["week_start_date"].isin(weeks_available)]
    return {"trends": df.to_dict(orient="records")}


@app.get("/alerts")
def alerts(status: str = "open", limit: int = 20):
    df = _df(
        """
        SELECT a.alert_id, a.detected_at, a.week_start_date, a.metric_name, a.severity, a.z_score,
               a.current_value, a.root_cause_summary, a.representative_quotes, a.status,
               c.name AS category
        FROM alerts a LEFT JOIN categories c ON c.category_id = a.category_id
        WHERE a.status = :status ORDER BY a.detected_at DESC LIMIT :limit
        """,
        {"status": status, "limit": limit},
    )
    records = df.to_dict(orient="records")
    for r in records:
        if r.get("representative_quotes"):
            try:
                r["representative_quotes"] = json.loads(r["representative_quotes"])
            except (TypeError, json.JSONDecodeError):
                pass
    return {"alerts": records}


@app.get("/recommendations")
def recommendations(alert_id: int | None = None, limit: int = 20):
    query = "SELECT * FROM recommendations"
    params = {}
    if alert_id is not None:
        query += " WHERE alert_id = :alert_id"
        params["alert_id"] = alert_id
    query += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit
    return {"recommendations": _df(query, params).to_dict(orient="records")}


@app.get("/report")
def report(format: str = Query("markdown", enum=["markdown", "html", "pdf"])):
    ext = {"markdown": "md", "html": "html", "pdf": "pdf"}[format]
    candidates = sorted(REPORTS_DIR.glob(f"weekly_report_*.{ext}"), reverse=True)
    if not candidates:
        raise HTTPException(404, f"No {ext} report has been generated yet. Run src/reports/weekly_report.py.")
    if format == "pdf":
        return FileResponse(candidates[0], media_type="application/pdf", filename=candidates[0].name)
    return {"path": str(candidates[0]), "content": candidates[0].read_text(encoding="utf-8")}


@app.get("/dashboard-data")
def dashboard_data():
    return {
        "health": latest_health(),
        "issues": issues(None),
        "trends": trends(None, weeks=12),
        "alerts": alerts("open", 20),
        "recommendations": recommendations(None, 20),
    }
