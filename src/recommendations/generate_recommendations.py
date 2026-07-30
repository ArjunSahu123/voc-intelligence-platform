"""Turns root-cause evidence into a product-thinking recommendation.

Follows the chain the brief specifies explicitly:
  issue -> probable causes -> customer impact -> business impact
  -> recommended investigation -> suggested fix -> metrics to monitor

This is a separate LLM call from root_cause_analysis.py on purpose: root
cause is evidence retrieval + summarization (what happened), recommendation
is product judgment on top of that evidence (so what, and what do we do) —
keeping them separate means either can be re-run/re-prompted independently
(e.g. re-running recommendations with a different product priority framing
without re-summarizing the same reviews).
"""
from src.common.llm_client import call_structured

RECOMMENDATION_TOOL = {
    "name": "product_recommendation",
    "description": "A structured, product-thinking recommendation for a PM.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short (<12 words) title naming the issue."},
            "customer_impact": {"type": "string", "description": "Who is affected and how, in concrete terms."},
            "business_impact": {"type": "string", "description": "Effect on retention, GMV, support cost, trust, etc."},
            "recommended_investigation": {"type": "string", "description": "What the team should look into first."},
            "suggested_fix": {"type": "string", "description": "A concrete, scoped fix direction (not vague platitudes)."},
            "metrics_to_monitor": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 specific metrics to watch to confirm the fix worked.",
            },
        },
        "required": [
            "title",
            "customer_impact",
            "business_impact",
            "recommended_investigation",
            "suggested_fix",
            "metrics_to_monitor",
        ],
    },
}


def generate_recommendation(anomaly: dict, root_cause: dict, category_name: str | None) -> dict | None:
    context = (
        f"Anomaly: {anomaly['type']} in category '{category_name or 'overall ratings'}', "
        f"week of {anomaly['week_start_date']}, severity={anomaly['severity']}, z-score={anomaly['z_score']}.\n\n"
        f"Root cause theme: {root_cause['theme_summary']}\n"
        f"Representative quotes: {root_cause['representative_quotes']}\n"
        f"Estimated impact: {root_cause['estimated_impact']}\n"
        f"Probable causes already identified: {root_cause['probable_causes']}\n\n"
        "Give a concrete, actionable recommendation for a Product Manager. "
        "Be specific — avoid generic advice like 'improve UX' or 'monitor closely' without specifics."
    )

    return call_structured(
        user_message=context,
        json_schema=RECOMMENDATION_TOOL["input_schema"],
        tool_name=RECOMMENDATION_TOOL["name"],
    )
