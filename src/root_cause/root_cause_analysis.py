"""Root cause analysis: turns a statistical anomaly into evidence.

Given an anomaly (a category+week issue spike, or a rating drop) detected by
src/anomaly/detect_anomalies.py, this pulls the actual affected reviews and
asks Claude to summarize themes and extract verbatim representative quotes —
the evidence a PM would need to trust the alert enough to act on it, rather
than a bare "issue_pct went up" number.
"""
import pandas as pd

from src.common.db import ENGINE
from src.common.llm_client import call_structured

MAX_REVIEWS_FOR_ANALYSIS = 20

ROOT_CAUSE_TOOL = {
    "name": "root_cause_findings",
    "description": "Structured root-cause findings from a batch of affected customer reviews.",
    "input_schema": {
        "type": "object",
        "properties": {
            "theme_summary": {
                "type": "string",
                "description": "2-3 sentence summary of the dominant theme(s) in these reviews.",
            },
            "representative_quotes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 short verbatim quotes (or close paraphrases if non-English) that best illustrate the issue.",
            },
            "estimated_impact": {
                "type": "string",
                "description": "One sentence estimating who/how many are affected, based only on the given evidence.",
            },
            "probable_causes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 plausible underlying causes a product/eng team should investigate.",
            },
        },
        "required": ["theme_summary", "representative_quotes", "estimated_impact", "probable_causes"],
    },
}


def fetch_affected_reviews(anomaly: dict) -> pd.DataFrame:
    week_start = anomaly["week_start_date"]
    week_end = pd.Timestamp(week_start) + pd.Timedelta(days=7)

    if anomaly["type"] == "issue_spike":
        query = """
            SELECT r.content_clean, r.rating, r.thumbs_up_count
            FROM reviews r
            JOIN review_classifications rc ON rc.review_id = r.review_id
            WHERE rc.primary_category_id = :category_id
              AND r.review_date >= :week_start AND r.review_date < :week_end
            ORDER BY r.thumbs_up_count DESC
            LIMIT :limit
        """
        params = {
            "category_id": anomaly["category_id"],
            "week_start": str(week_start),
            "week_end": str(week_end.date()),
            "limit": MAX_REVIEWS_FOR_ANALYSIS,
        }
    else:  # rating_drop
        query = """
            SELECT content_clean, rating, thumbs_up_count
            FROM reviews
            WHERE rating <= 2 AND review_date >= :week_start AND review_date < :week_end
            ORDER BY thumbs_up_count DESC
            LIMIT :limit
        """
        params = {"week_start": str(week_start), "week_end": str(week_end.date()), "limit": MAX_REVIEWS_FOR_ANALYSIS}

    return pd.read_sql(query, ENGINE, params=params)


def analyze_root_cause(anomaly: dict) -> dict | None:
    reviews = fetch_affected_reviews(anomaly)
    if reviews.empty:
        return None

    review_text = "\n\n".join(
        f'(rating {r.rating}/5) "{r.content_clean[:400]}"' for r in reviews.itertuples()
    )
    prompt = (
        f"These are customer reviews behind a detected anomaly (type={anomaly['type']}, "
        f"severity={anomaly['severity']}, z-score={anomaly['z_score']}):\n\n{review_text}\n\n"
        "Analyze based only on this evidence."
    )

    findings = call_structured(
        user_message=prompt,
        json_schema=ROOT_CAUSE_TOOL["input_schema"],
        tool_name=ROOT_CAUSE_TOOL["name"],
    )
    findings["reviews_analyzed"] = len(reviews)
    return findings
