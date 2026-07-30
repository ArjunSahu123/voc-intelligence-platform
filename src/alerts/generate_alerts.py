"""Orchestrates: detect anomalies -> root-cause them -> recommend -> persist.

For each statistical anomaly from detect_anomalies(), this pulls evidence
(root_cause_analysis), turns it into a product recommendation
(generate_recommendations), and writes both an Alert and a linked
Recommendation row. Skips anomalies for weeks/categories that already have
an open alert on the same metric, so re-running the pipeline doesn't spam
duplicate alerts.
"""
import json

from src.anomaly.detect_anomalies import detect_anomalies
from src.common.db import init_db, session_scope
from src.common.models import Alert, Category, Recommendation
from src.recommendations.generate_recommendations import generate_recommendation
from src.root_cause.root_cause_analysis import analyze_root_cause


def _metric_name(anomaly: dict, category_name: str | None) -> str:
    if anomaly["type"] == "issue_spike":
        return f"issue_pct:{category_name}"
    return "avg_rating"


def _already_alerted(session, metric_name: str, week_start_date) -> bool:
    return (
        session.query(Alert)
        .filter(Alert.metric_name == metric_name, Alert.week_start_date == week_start_date)
        .first()
        is not None
    )


def generate_alerts() -> dict:
    init_db()
    result = detect_anomalies()
    anomalies = result["anomalies"]

    with session_scope() as session:
        category_names = {c.category_id: c.name for c in session.query(Category).all()}

    created, skipped, failed = 0, 0, 0

    for anomaly in anomalies:
        category_name = category_names.get(anomaly["category_id"]) if anomaly["category_id"] else None
        metric_name = _metric_name(anomaly, category_name)

        with session_scope() as session:
            if _already_alerted(session, metric_name, anomaly["week_start_date"]):
                skipped += 1
                continue

        root_cause = analyze_root_cause(anomaly)
        if root_cause is None:
            failed += 1
            continue

        recommendation = generate_recommendation(anomaly, root_cause, category_name)

        with session_scope() as session:
            alert = Alert(
                week_start_date=anomaly["week_start_date"],
                metric_name=metric_name,
                category_id=anomaly["category_id"],
                severity=anomaly["severity"],
                z_score=anomaly["z_score"],
                current_value=anomaly["current_value"],
                root_cause_summary=root_cause["theme_summary"],
                representative_quotes=json.dumps(root_cause["representative_quotes"]),
                status="open",
            )
            session.add(alert)
            session.flush()  # populate alert.alert_id

            if recommendation:
                session.add(
                    Recommendation(
                        alert_id=alert.alert_id,
                        category_id=anomaly["category_id"],
                        title=recommendation["title"],
                        probable_causes="; ".join(root_cause["probable_causes"]),
                        customer_impact=recommendation["customer_impact"],
                        business_impact=recommendation["business_impact"],
                        recommended_investigation=recommendation["recommended_investigation"],
                        suggested_fix=recommendation["suggested_fix"],
                        metrics_to_monitor="; ".join(recommendation["metrics_to_monitor"]),
                    )
                )
        created += 1

    return {"anomalies_found": len(anomalies), "alerts_created": created, "skipped_existing": skipped, "failed": failed}


def main():
    result = generate_alerts()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
