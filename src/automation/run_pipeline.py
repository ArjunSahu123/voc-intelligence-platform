"""One-command weekly automation: ingest -> clean -> load -> classify ->
metrics -> anomaly detection -> alerts -> report.

Run: python -m src.automation.run_pipeline --incremental

Each step is wrapped so a failure doesn't take down steps that don't depend
on it (e.g. if Claude classification fails due to a rate limit, metrics/
report still generate from whatever was already classified) — the run
summary at the end reports exactly what succeeded and what didn't, so a
scheduled/cron run fails loudly in logs rather than silently skipping steps.
"""
import argparse
import sys
import time
from datetime import date

from src.classification.classify_reviews import classify_reviews
from src.cleaning.clean_text import build_processed_dataset
from src.common.config import ACTIVE_LLM_API_KEY, APP_PACKAGE, COUNTRY, DATA_PROCESSED_DIR, LANG, REPORTS_DIR
from src.ingestion.load_to_db import load_reviews
from src.ingestion.scrape_reviews import scrape
from src.metrics.compute_metrics import compute_issue_trends, compute_weekly_metrics, _load_joined, _upsert
from src.common.models import IssueTrend, WeeklyMetric
from src.anomaly.detect_anomalies import detect_anomalies
from src.alerts.generate_alerts import generate_alerts
from src.reports.weekly_report import generate_report, html_from_markdown, render_pdf


def run_step(name: str, fn, *args, **kwargs):
    print(f"\n=== {name} ===")
    start = time.time()
    try:
        result = fn(*args, **kwargs)
        print(f"  OK ({time.time() - start:.1f}s): {result if not isinstance(result, (list, dict)) else ''}")
        return {"step": name, "status": "ok", "result": result, "seconds": round(time.time() - start, 1)}
    except Exception as exc:  # noqa: BLE001 - a pipeline step failing must not crash the whole run
        print(f"  FAILED ({time.time() - start:.1f}s): {exc}", file=sys.stderr)
        return {"step": name, "status": "failed", "error": str(exc), "seconds": round(time.time() - start, 1)}


def main():
    parser = argparse.ArgumentParser(description="Run the full weekly VoC pipeline end to end.")
    parser.add_argument("--incremental", action="store_true", help="Only scrape reviews newer than what's on disk.")
    parser.add_argument("--scrape-target", type=int, default=2000, help="Reviews to fetch on a backfill run.")
    parser.add_argument("--classify-limit", type=int, default=500, help="Max reviews to classify this run.")
    parser.add_argument("--skip-classification", action="store_true")
    parser.add_argument("--skip-alerts", action="store_true", help="Skip LLM root-cause/recommendation generation.")
    args = parser.parse_args()

    summary = []

    summary.append(
        run_step(
            "1. Ingest reviews",
            scrape,
            app_id=APP_PACKAGE,
            country=COUNTRY,
            lang=LANG,
            target=args.scrape_target,
            incremental=args.incremental,
        )
    )

    def _clean_and_save():
        df = build_processed_dataset()
        df.to_csv(DATA_PROCESSED_DIR / "reviews_processed.csv", index=False)
        return f"{len(df)} rows"

    summary.append(run_step("2. Clean text", _clean_and_save))
    summary.append(run_step("3. Load to DB", load_reviews))

    if not args.skip_classification:
        if not ACTIVE_LLM_API_KEY:
            summary.append({"step": "4. Classify reviews", "status": "skipped", "reason": "no LLM API key configured"})
        else:
            summary.append(run_step("4. Classify reviews", classify_reviews, limit=args.classify_limit))
    else:
        summary.append({"step": "4. Classify reviews", "status": "skipped", "reason": "--skip-classification"})

    def _metrics():
        df = _load_joined()
        if df.empty:
            return "no reviews"
        weekly = compute_weekly_metrics(df)
        trends = compute_issue_trends(df)
        _upsert(WeeklyMetric, weekly.to_dict(orient="records"), ["week_start_date"])
        _upsert(IssueTrend, trends.to_dict(orient="records"), ["week_start_date", "category_id"])
        return f"{len(weekly)} weeks, {len(trends)} trend rows"

    summary.append(run_step("5. Compute metrics", _metrics))
    summary.append(run_step("6. Detect anomalies", detect_anomalies))

    if not args.skip_alerts:
        if not ACTIVE_LLM_API_KEY:
            summary.append({"step": "7. Generate alerts", "status": "skipped", "reason": "no LLM API key configured"})
        else:
            summary.append(run_step("7. Generate alerts", generate_alerts))
    else:
        summary.append({"step": "7. Generate alerts", "status": "skipped", "reason": "--skip-alerts"})

    def _report():
        md = generate_report()
        stamp = date.today().isoformat()
        (REPORTS_DIR / f"weekly_report_{stamp}.md").write_text(md, encoding="utf-8")
        html_content = html_from_markdown(md)
        (REPORTS_DIR / f"weekly_report_{stamp}.html").write_text(html_content, encoding="utf-8")
        render_pdf(html_content, REPORTS_DIR / f"weekly_report_{stamp}.pdf")
        return f"reports/weekly_report_{stamp}.{{md,html,pdf}}"

    summary.append(run_step("8. Generate weekly report", _report))

    print("\n" + "=" * 50)
    print("PIPELINE SUMMARY")
    print("=" * 50)
    for s in summary:
        print(f"  [{s['status'].upper():8}] {s['step']}")

    if any(s["status"] == "failed" for s in summary):
        sys.exit(1)


if __name__ == "__main__":
    main()
