"""Cleans raw scraped reviews into an analysis-ready table.

Rebuilds the full processed dataset from all raw JSONL files on every run.
This is deliberately not incremental: raw files are already deduplicated by
reviewId at scrape time (see src/ingestion/scrape_reviews.py), so re-cleaning
everything is cheap (tens of thousands of rows, sub-second) and avoids a
second, harder-to-audit incremental-merge path for what is a pure function
of the raw data.
"""
import json
import re

import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect

from src.common.config import DATA_RAW_DIR, DATA_PROCESSED_DIR

DetectorFactory.seed = 42  # langdetect is otherwise non-deterministic

URL_RE = re.compile(r"https?://\S+|www\.\S+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)
WHITESPACE_RE = re.compile(r"\s+")


def clean_text(raw: str) -> str:
    if not isinstance(raw, str):
        return ""
    text = URL_RE.sub(" ", raw)
    text = EMAIL_RE.sub(" ", text)
    text = EMOJI_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def detect_language(text: str) -> str:
    if not text or len(text) < 3:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def load_raw_reviews() -> pd.DataFrame:
    records = []
    for path in sorted(DATA_RAW_DIR.glob("reviews_raw_*.jsonl")):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def build_processed_dataset() -> pd.DataFrame:
    df = load_raw_reviews()
    if df.empty:
        return df

    df = df.drop_duplicates(subset=["reviewId"])

    # Missing values: no review text or no rating means the row is useless
    # for both classification and metrics, so those rows are dropped rather
    # than imputed (a fabricated rating/text would silently corrupt every
    # downstream metric).
    df = df.dropna(subset=["content", "score"])
    df = df[df["content"].str.strip() != ""]

    df["reviewCreatedVersion"] = df["reviewCreatedVersion"].fillna("unknown")
    df["replyContent"] = df["replyContent"].fillna("")

    df["content_clean"] = df["content"].apply(clean_text)
    df = df[df["content_clean"].str.len() > 0]
    df["language"] = df["content_clean"].apply(detect_language)

    df["review_date"] = pd.to_datetime(df["at"], utc=True, errors="coerce")
    df["replied_at"] = pd.to_datetime(df["repliedAt"], utc=True, errors="coerce")
    df = df.dropna(subset=["review_date"])

    out = pd.DataFrame(
        {
            "review_id": df["reviewId"],
            "user_name": df.get("userName", "unknown"),
            "content_raw": df["content"],
            "content_clean": df["content_clean"],
            "rating": df["score"].astype(int),
            "review_date": df["review_date"],
            "app_version": df["reviewCreatedVersion"],
            "thumbs_up_count": df.get("thumbsUpCount", 0).fillna(0).astype(int),
            "language": df["language"],
            "is_english": df["language"] == "en",
            "reply_content": df["replyContent"],
            "replied_at": df["replied_at"],
        }
    )
    out = out.sort_values("review_date").reset_index(drop=True)
    return out


def main():
    processed = build_processed_dataset()
    out_path = DATA_PROCESSED_DIR / "reviews_processed.csv"
    processed.to_csv(out_path, index=False)
    print(
        f"Processed {len(processed)} reviews "
        f"({processed['is_english'].sum()} English) -> {out_path}"
    )


if __name__ == "__main__":
    main()
