"""Batches unclassified reviews to the configured LLM for product-journey
classification (see src/common/llm_client.py for the Anthropic/Gemini
provider switch).

Batches BATCH_SIZE reviews per API call (not one call per review) — this is
the main cost lever: for a review corpus in the thousands, per-review calls
would be both slower and far more expensive than batching, and the model
tracks reviews reliably by index within a batch of this size.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone

from src.common.config import ACTIVE_LLM_MODEL
from src.common.db import init_db, session_scope
from src.common.llm_client import call_structured
from src.common.models import Category, ClassificationRunLog, Review, ReviewClassification
from src.classification.prompts import CLASSIFY_TOOL, PROMPT_VERSION, SYSTEM_PROMPT, build_batch_user_message

BATCH_SIZE = 10
MAX_TOKENS = 4096


def _fetch_unclassified_reviews(session, limit: int) -> list[dict]:
    classified_ids = {row[0] for row in session.query(ReviewClassification.review_id).all()}
    query = session.query(Review).order_by(Review.review_date.desc())
    reviews = []
    for review in query:
        if review.review_id in classified_ids:
            continue
        reviews.append(
            {
                "review_id": review.review_id,
                "rating": review.rating,
                "content_clean": review.content_clean[:1000],  # cap tokens per review
            }
        )
        if len(reviews) >= limit:
            break
    return reviews


def _call_llm(user_message: str) -> dict:
    return call_structured(
        user_message=user_message,
        json_schema=CLASSIFY_TOOL["input_schema"],
        tool_name=CLASSIFY_TOOL["name"],
        system_prompt=SYSTEM_PROMPT,
        max_tokens=MAX_TOKENS,
    )


def classify_reviews(limit: int, batch_size: int = BATCH_SIZE) -> dict:
    init_db()

    with session_scope() as session:
        category_ids = {c.name: c.category_id for c in session.query(Category).all()}
        pending = _fetch_unclassified_reviews(session, limit)

    if not pending:
        return {"attempted": 0, "succeeded": 0, "failed": 0}

    run_started = datetime.now(timezone.utc)
    succeeded, failed = 0, 0

    for i in range(0, len(pending), batch_size):
        chunk = pending[i : i + batch_size]
        indexed = [{"index": j, **r} for j, r in enumerate(chunk)]
        user_message = build_batch_user_message(indexed)

        try:
            result = _call_llm(user_message)
            classifications = {c["index"]: c for c in result["classifications"]}
        except Exception as exc:  # noqa: BLE001 - log and continue with next batch
            print(f"  batch {i // batch_size} failed: {exc}", file=sys.stderr)
            failed += len(chunk)
            continue

        with session_scope() as session:
            for j, review in enumerate(chunk):
                c = classifications.get(j)
                if c is None:
                    failed += 1
                    continue
                primary_id = category_ids.get(c["primary_category"])
                secondary_id = category_ids.get(c["secondary_category"]) if c.get("secondary_category") else None
                if primary_id is None:
                    failed += 1
                    continue

                session.merge(
                    ReviewClassification(
                        review_id=review["review_id"],
                        primary_category_id=primary_id,
                        secondary_category_id=secondary_id,
                        sentiment=c["sentiment"],
                        severity=c["severity"],
                        urgency=c["urgency"],
                        confidence_score=float(c["confidence"]),
                        model_used=ACTIVE_LLM_MODEL,
                        prompt_version=PROMPT_VERSION,
                        raw_llm_response=json.dumps(c),
                    )
                )
                succeeded += 1

        time.sleep(0.3)  # stay well under rate limits between batches

    with session_scope() as session:
        session.add(
            ClassificationRunLog(
                run_started_at=run_started,
                run_completed_at=datetime.now(timezone.utc),
                reviews_attempted=len(pending),
                reviews_succeeded=succeeded,
                reviews_failed=failed,
                model_used=ACTIVE_LLM_MODEL,
                prompt_version=PROMPT_VERSION,
            )
        )

    return {"attempted": len(pending), "succeeded": succeeded, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description="Classify unclassified reviews via Claude.")
    parser.add_argument("--limit", type=int, default=500, help="Max reviews to classify this run.")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    result = classify_reviews(args.limit, args.batch_size)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
