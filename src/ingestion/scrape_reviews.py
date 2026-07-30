"""Incremental Google Play Store review ingestion.

Design notes (why it works this way):
- Play Store's review API has no "reviews since date X" filter, only pagination
  sorted by newest-first. So incrementality is implemented by pagination + a
  seen-ID index: on a scheduled run we stop as soon as we hit a reviewId we
  already have on disk, because everything after that point in a NEWEST-sorted
  feed is guaranteed to already be stored.
- On the very first (backfill) run there is nothing to stop early on, so we
  keep paginating until either `--target` reviews are collected or the API
  runs out of continuation pages.
- Raw API responses are appended as JSON Lines, one file per run, so raw data
  is never mutated after being written (append-only audit trail) and no
  review is ever downloaded twice into processed data.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone

from google_play_scraper import Sort, reviews

from src.common.config import DATA_RAW_DIR, APP_PACKAGE, COUNTRY, LANG

STATE_FILE = DATA_RAW_DIR / "_scrape_state.json"
BATCH_SIZE = 200
SLEEP_BETWEEN_BATCHES_SEC = 1.5
MAX_BATCHES_SAFETY = 200  # hard stop so a runaway loop can never hang the pipeline


def _load_seen_ids() -> set:
    seen = set()
    for path in DATA_RAW_DIR.glob("reviews_raw_*.jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["reviewId"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return seen


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_run_utc": None, "total_reviews_stored": 0, "runs": []}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def scrape(app_id: str, country: str, lang: str, target: int, incremental: bool) -> dict:
    seen_ids = _load_seen_ids()
    starting_seen_count = len(seen_ids)
    new_reviews = []
    continuation_token = None
    batches = 0
    hit_known_review = False

    while len(new_reviews) < target and batches < MAX_BATCHES_SAFETY:
        batch, continuation_token = reviews(
            app_id,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=BATCH_SIZE,
            continuation_token=continuation_token,
        )
        batches += 1
        if not batch:
            break

        for r in batch:
            if r["reviewId"] in seen_ids:
                if incremental:
                    hit_known_review = True
                    break
                continue
            seen_ids.add(r["reviewId"])
            new_reviews.append(r)

        if hit_known_review:
            break
        if continuation_token is None:
            break
        time.sleep(SLEEP_BETWEEN_BATCHES_SEC)

    if new_reviews:
        run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = DATA_RAW_DIR / f"reviews_raw_{run_ts}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for r in new_reviews:
                f.write(json.dumps(r, default=str) + "\n")
    else:
        out_path = None

    state = _load_state()
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    state["total_reviews_stored"] = starting_seen_count + len(new_reviews)
    state["runs"].append(
        {
            "timestamp_utc": state["last_run_utc"],
            "mode": "incremental" if incremental else "backfill",
            "new_reviews": len(new_reviews),
            "batches_fetched": batches,
            "output_file": str(out_path) if out_path else None,
        }
    )
    _save_state(state)

    return {
        "new_reviews": len(new_reviews),
        "total_reviews_stored": state["total_reviews_stored"],
        "output_file": str(out_path) if out_path else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Scrape Play Store reviews incrementally.")
    parser.add_argument("--target", type=int, default=5000, help="Reviews to collect this run (backfill mode).")
    parser.add_argument("--incremental", action="store_true", help="Stop at the first already-seen review.")
    parser.add_argument("--app-id", default=APP_PACKAGE)
    parser.add_argument("--country", default=COUNTRY)
    parser.add_argument("--lang", default=LANG)
    args = parser.parse_args()

    result = scrape(args.app_id, args.country, args.lang, args.target, args.incremental)
    print(json.dumps(result, indent=2))
    if result["new_reviews"] == 0 and not args.incremental:
        sys.exit(1)


if __name__ == "__main__":
    main()
