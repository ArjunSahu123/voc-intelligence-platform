"""Prompt + tool schema for LLM-based issue classification.

This is deliberately NOT sentiment analysis. The taxonomy is the customer's
journey through the product (see src/common/db.py TAXONOMY) — sentiment,
severity, and urgency are separate axes layered on top, because a product
team needs "where in the funnel is this happening" more than "is this a bad
review," and the two are frequently at odds (a 5-star review can still name
a checkout bug the user worked around).
"""
from src.common.db import TAXONOMY

PROMPT_VERSION = "v1.0"

CATEGORY_LIST = "\n".join(f"- {name} (journey stage: {stage})" for name, stage in TAXONOMY.items())

SYSTEM_PROMPT = f"""You are a product analytics classifier for a food delivery app's customer reviews \
(the case study app is Zomato, but the same taxonomy generalizes to any food delivery / marketplace app).

Your job is NOT sentiment analysis. Classify each review by WHERE in the customer journey the review \
is about, using this fixed taxonomy (do not invent new categories):

{CATEGORY_LIST}

For each review, determine:

1. primary_category: the single best-fitting category from the list above (exact string match).
2. secondary_category: a second category if the review clearly touches two distinct journey stages \
(e.g. "coupon didn't apply AND the order arrived cold" -> Coupons & Offers + Delivery Accuracy). \
Use null if there is no clear second issue.
3. sentiment: "positive", "neutral", or "negative" — the reviewer's overall tone.
4. severity: how badly the core experience was degraded, regardless of tone:
   - "low": minor annoyance, cosmetic, or a compliment/neutral remark with no real friction.
   - "medium": the task was completed but with noticeable friction (had to retry, minor delay).
   - "high": the task failed outright but was recoverable (order cancelled, had to reorder, refund needed).
   - "critical": money lost with no resolution mentioned, safety issue, complete app failure, or \
fraud/account-security concern.
5. urgency: how time-sensitive fixing the underlying cause is for the business:
   - "low": cosmetic / rare edge case.
   - "medium": affects a meaningful chunk of a specific flow.
   - "high": actively affects money movement, live orders, or account access right now.
6. confidence: your confidence in the primary_category assignment, from 0.0 to 1.0.

Reviews may be in English, Hindi, Hinglish, or other Indian languages — classify based on meaning, \
you do not need to translate in your answer. If a review is pure praise with no actionable content, \
use "General Feedback" as the primary category with sentiment "positive" and severity "low".

You will be given a numbered batch of reviews. Call the `classify_reviews_batch` tool exactly once \
with one classification object per review, in the same order, referencing each by its `index`."""

CLASSIFY_TOOL = {
    "name": "classify_reviews_batch",
    "description": "Return one classification per review in the batch, in order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "The review's index as given in the prompt."},
                        "primary_category": {"type": "string", "enum": list(TAXONOMY.keys())},
                        "secondary_category": {
                            "type": ["string", "null"],
                            "enum": list(TAXONOMY.keys()) + [None],
                        },
                        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": [
                        "index",
                        "primary_category",
                        "secondary_category",
                        "sentiment",
                        "severity",
                        "urgency",
                        "confidence",
                    ],
                },
            }
        },
        "required": ["classifications"],
    },
}


def build_batch_user_message(batch: list[dict]) -> str:
    """batch: list of {"index": int, "rating": int, "content_clean": str}."""
    lines = []
    for item in batch:
        lines.append(f'[{item["index"]}] (rating: {item["rating"]}/5) "{item["content_clean"]}"')
    return "Classify these reviews:\n\n" + "\n\n".join(lines)
