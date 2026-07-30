"""Generates the weekly product report (Markdown + HTML) from the database.

The narrative Executive Summary / Open Questions / Next Actions sections are
LLM-written (given the week's actual computed numbers as context, so the
LLM is synthesizing prose from real data, not inventing figures). If no
ANTHROPIC_API_KEY is configured or the call fails, the report still
generates with a template-based summary instead of failing outright — the
weekly automation run should never be blocked on the narrative layer.
"""
import argparse
from datetime import date

import markdown2
import pandas as pd

from src.common.config import ACTIVE_LLM_API_KEY, REPORTS_DIR
from src.common.db import ENGINE
from src.common.llm_client import call_structured
from src.metrics.health_score import select_headline_weeks

MIN_ISSUE_VOLUME_FOR_TREND = 3  # ignore categories with too few classified reviews to trust wow_growth_pct


def _all_weeks() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM weekly_metrics ORDER BY week_start_date", ENGINE, parse_dates=["week_start_date"]
    )


def _issue_trends_for_week(week_start_date) -> pd.DataFrame:
    query = """
        SELECT it.*, c.name AS category_name
        FROM issue_trends it
        JOIN categories c ON c.category_id = it.category_id
        WHERE it.week_start_date = :week
        ORDER BY it.severity_score DESC
    """
    return pd.read_sql(query, ENGINE, params={"week": str(week_start_date)})


def _open_alerts_and_recs() -> pd.DataFrame:
    query = """
        SELECT a.alert_id, a.week_start_date, a.metric_name, a.severity, a.z_score,
               a.root_cause_summary, a.representative_quotes,
               r.title AS recommendation_title, r.suggested_fix, r.recommended_investigation,
               r.customer_impact, r.business_impact
        FROM alerts a
        LEFT JOIN recommendations r ON r.alert_id = a.alert_id
        WHERE a.status = 'open'
        ORDER BY a.detected_at DESC
        LIMIT 10
    """
    return pd.read_sql(query, ENGINE)


REPORT_NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "next_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["executive_summary", "open_questions", "next_actions"],
}


def _llm_narrative(context: str) -> dict:
    if ACTIVE_LLM_API_KEY:
        try:
            return call_structured(user_message=context, json_schema=REPORT_NARRATIVE_SCHEMA, tool_name="report_narrative")
        except Exception:
            pass
    return {
        "executive_summary": "Automated narrative unavailable this run (no LLM access) — see the tables below for the underlying numbers.",
        "open_questions": ["Set an LLM provider API key (`ANTHROPIC_API_KEY` or `GEMINI_API_KEY`) to generate a narrative summary."],
        "next_actions": ["Review the Biggest Issues and Alerts sections directly."],
    }


def generate_report() -> str:
    weeks = _all_weeks()
    if weeks.empty:
        raise RuntimeError("No weekly_metrics found. Run compute_metrics.py first.")

    this_week, last_week, excluded_tail = select_headline_weeks(weeks)

    trends = _issue_trends_for_week(this_week["week_start_date"].date())
    trending_trusted = trends[trends["issue_count"] >= MIN_ISSUE_VOLUME_FOR_TREND]
    declining = trending_trusted[trending_trusted["wow_growth_pct"] > 0].sort_values("wow_growth_pct", ascending=False)
    improving = trending_trusted[trending_trusted["wow_growth_pct"] < 0].sort_values("wow_growth_pct")

    alerts_df = _open_alerts_and_recs()

    context = (
        f"Week of {this_week['week_start_date'].date()}: "
        f"{int(this_week['total_reviews'])} reviews, avg rating {this_week['avg_rating']:.2f}, "
        f"health score {this_week['product_health_score']:.1f}/100"
        + (f" (last week: {last_week['product_health_score']:.1f}/100)." if last_week is not None else ".")
        + f"\nBiggest issue categories this week: "
        + ", ".join(f"{r.category_name} ({r.issue_pct*100:.1f}%)" for r in trends.head(5).itertuples())
        + f"\nOpen alerts: {len(alerts_df)}."
        + "\nWrite an honest, specific executive summary (not generic filler) plus open questions and next actions "
        "a PM should act on this week."
    )
    narrative = _llm_narrative(context)

    lines = [f"# Weekly Product Report — Week of {this_week['week_start_date'].date()}\n"]

    if not excluded_tail.empty:
        tail_weeks = ", ".join(str(d.date()) for d in excluded_tail["week_start_date"])
        lines.append(
            f"_Note: {len(excluded_tail)} more recent week(s) starting {tail_weeks} are excluded from this "
            "report's headline — Google Play's review-indexing lag means the most recent few days always "
            "look artificially sparse at scrape time. They'll be included once review volume for those "
            "weeks catches up in a later run._\n"
        )

    lines.append("## Executive Summary\n")
    lines.append(narrative["executive_summary"] + "\n")

    lines.append("## Top Findings\n")
    lines.append(
        f"- **{int(this_week['total_reviews'])} reviews** this week, average rating **{this_week['avg_rating']:.2f}/5**\n"
        f"- **Product Health Score: {this_week['product_health_score']:.1f}/100**"
        + (
            f" ({'up' if this_week['product_health_score'] >= last_week['product_health_score'] else 'down'} "
            f"from {last_week['product_health_score']:.1f} last week)\n"
            if last_week is not None
            else "\n"
        )
        + f"- **{int(this_week['critical_issue_count'])}** critical-severity issues, "
        f"**{int(this_week['crash_mentions'])}** crash mentions\n"
    )

    lines.append("## Biggest Issues\n")
    if trends.empty:
        lines.append("_No classified reviews yet this week._\n")
    else:
        lines.append("| Category | Issue % | Severity Score | WoW Growth |\n|---|---|---|---|\n")
        for r in trends.head(8).itertuples():
            growth = f"{r.wow_growth_pct:+.0f}%" if pd.notnull(r.wow_growth_pct) else "n/a"
            lines.append(f"| {r.category_name} | {r.issue_pct*100:.1f}% | {r.severity_score:.1f} | {growth} |\n")

    lines.append("\n## Improving Metrics\n")
    if improving.empty:
        lines.append("_None with enough volume to trust this week._\n")
    else:
        for r in improving.itertuples():
            lines.append(f"- {r.category_name}: {r.wow_growth_pct:+.0f}% week-over-week\n")

    lines.append("\n## Declining Metrics\n")
    if declining.empty:
        lines.append("_None with enough volume to trust this week._\n")
    else:
        for r in declining.itertuples():
            lines.append(f"- {r.category_name}: {r.wow_growth_pct:+.0f}% week-over-week\n")

    lines.append("\n## Alerts & Recommendations\n")
    if alerts_df.empty:
        lines.append("_No open alerts._\n")
    else:
        for a in alerts_df.itertuples():
            lines.append(f"### [{a.severity.upper()}] {a.recommendation_title or a.metric_name}\n")
            lines.append(f"{a.root_cause_summary or ''}\n\n")
            if a.suggested_fix:
                lines.append(f"**Suggested fix:** {a.suggested_fix}\n\n")
                lines.append(f"**Investigate:** {a.recommended_investigation}\n\n")

    lines.append("## Open Questions\n")
    for q in narrative["open_questions"]:
        lines.append(f"- {q}\n")

    lines.append("\n## Next Actions\n")
    for act in narrative["next_actions"]:
        lines.append(f"- {act}\n")

    return "".join(lines)


def html_from_markdown(md: str) -> str:
    """Shared by main() here and src/automation/run_pipeline.py, so the HTML
    (and therefore the PDF rendered from it) is identical regardless of which
    entrypoint generated the report."""
    return (
        "<html><head><meta charset='utf-8'><title>Weekly Product Report</title>"
        "<style>"
        "body{font-family: Arial, Helvetica, sans-serif; margin: 2em; color:#222;}"
        "h1{font-size:20px;} h2{font-size:16px; border-bottom:1px solid #ccc; padding-bottom:4px;}"
        "table{border-collapse: collapse; width:100%; margin: 1em 0;}"
        "th,td{border:1px solid #ccc; padding:6px 8px; text-align:left; font-size:12px;}"
        "th{background:#f0f0f0;}"
        "blockquote{color:#555; border-left:3px solid #ccc; margin:0.5em 0; padding-left:1em;}"
        "</style></head><body>"
        f"{markdown2.markdown(md, extras=['tables'])}</body></html>"
    )


def render_pdf(html_content: str, out_path) -> None:
    """Pure-Python HTML->PDF (xhtml2pdf) — no external binary/system dependency,
    which matters because this needs to run unattended on a scheduled task."""
    from xhtml2pdf import pisa

    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(html_content, dest=f)
    if result.err:
        raise RuntimeError(f"PDF generation failed with {result.err} error(s) for {out_path}.")


def main():
    parser = argparse.ArgumentParser(description="Generate the weekly product report.")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    out_dir = REPORTS_DIR if args.out_dir is None else __import__("pathlib").Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md = generate_report()
    stamp = date.today().isoformat()
    md_path = out_dir / f"weekly_report_{stamp}.md"
    html_path = out_dir / f"weekly_report_{stamp}.html"
    pdf_path = out_dir / f"weekly_report_{stamp}.pdf"

    md_path.write_text(md, encoding="utf-8")
    html_content = html_from_markdown(md)
    html_path.write_text(html_content, encoding="utf-8")
    render_pdf(html_content, pdf_path)

    print(f"Wrote {md_path}")
    print(f"Wrote {html_path}")
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
