"""Validation harness for the LLM classifier.

Two steps, run separately because the middle step is manual:
  1. `sample`  -> writes docs/validation_sample.csv with N random classified
     reviews and the model's labels, plus empty human_* columns to fill in.
  2. (You manually open the CSV and fill in human_primary_category /
     human_sentiment / human_severity for each row.)
  3. `score`   -> reads the filled-in CSV and produces precision/recall/F1
     per class plus a confusion matrix, written to docs/validation_report.md.
"""
import argparse
import random

import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from src.common.config import ROOT_DIR
from src.common.db import ENGINE

DOCS_DIR = ROOT_DIR / "docs"
SAMPLE_PATH = DOCS_DIR / "validation_sample.csv"
REPORT_PATH = DOCS_DIR / "validation_report.md"


def sample(n: int, seed: int = 42):
    query = """
        SELECT
            r.review_id, r.content_clean, r.rating,
            pc.name AS model_primary_category,
            sc.name AS model_secondary_category,
            rc.sentiment AS model_sentiment,
            rc.severity AS model_severity,
            rc.urgency AS model_urgency,
            rc.confidence_score AS model_confidence
        FROM review_classifications rc
        JOIN reviews r ON r.review_id = rc.review_id
        JOIN categories pc ON pc.category_id = rc.primary_category_id
        LEFT JOIN categories sc ON sc.category_id = rc.secondary_category_id
    """
    df = pd.read_sql(query, ENGINE)
    if df.empty:
        raise RuntimeError("No classified reviews found. Run classify_reviews.py first.")

    random.seed(seed)
    n = min(n, len(df))
    sampled = df.sample(n=n, random_state=seed).reset_index(drop=True)

    for col in ("human_primary_category", "human_sentiment", "human_severity", "notes"):
        sampled[col] = ""

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    sampled.to_csv(SAMPLE_PATH, index=False)
    print(f"Wrote {len(sampled)} rows to {SAMPLE_PATH}")
    print("Fill in human_primary_category, human_sentiment, human_severity, then run: score")


def score():
    if not SAMPLE_PATH.exists():
        raise RuntimeError(f"{SAMPLE_PATH} not found. Run: sample first.")

    df = pd.read_csv(SAMPLE_PATH)
    df = df.dropna(subset=["human_primary_category", "human_sentiment"])
    df = df[(df["human_primary_category"].str.strip() != "") & (df["human_sentiment"].str.strip() != "")]

    if df.empty:
        raise RuntimeError(
            f"{SAMPLE_PATH} has no filled-in human labels yet. "
            "Open it, fill human_primary_category / human_sentiment / human_severity, and re-run."
        )

    lines = [f"# Classification Validation Report\n", f"Sample size scored: {len(df)}\n"]

    for label_col, model_col, title in [
        ("human_primary_category", "model_primary_category", "Primary Category"),
        ("human_sentiment", "model_sentiment", "Sentiment"),
    ]:
        y_true = df[label_col]
        y_pred = df[model_col]
        report = classification_report(y_true, y_pred, zero_division=0)
        lines.append(f"## {title}\n\n```\n{report}\n```\n")

    y_true = df["human_primary_category"]
    y_pred = df["model_primary_category"]
    labels = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=labels, columns=labels)
    cm_path = DOCS_DIR / "confusion_matrix.csv"
    cm_df.to_csv(cm_path)
    lines.append(f"## Confusion Matrix (Primary Category)\n\nSaved to `{cm_path.name}`.\n")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {cm_path}")


def main():
    parser = argparse.ArgumentParser(description="Validate the LLM classifier against human labels.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sample_p = sub.add_parser("sample", help="Write a random sample for manual labeling.")
    sample_p.add_argument("--n", type=int, default=200)

    sub.add_parser("score", help="Score the filled-in sample.")

    args = parser.parse_args()
    if args.cmd == "sample":
        sample(args.n)
    elif args.cmd == "score":
        score()


if __name__ == "__main__":
    main()
