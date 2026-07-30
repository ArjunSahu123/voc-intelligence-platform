"""Loads data/processed/reviews_processed.csv into the reviews table.

Idempotent upsert: existing review_ids are updated (a review's thumbs-up
count or reply can change after the fact), new ones are inserted. Safe to
re-run after every cleaning pass without creating duplicates.
"""
import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.common.config import DATA_PROCESSED_DIR
from src.common.db import ENGINE, init_db
from src.common.models import Review


def load_reviews() -> int:
    csv_path = DATA_PROCESSED_DIR / "reviews_processed.csv"
    df = pd.read_csv(csv_path, parse_dates=["review_date", "replied_at"])

    df["thumbs_up_count"] = df["thumbs_up_count"].fillna(0).astype(int)
    df["user_name"] = df["user_name"].fillna("unknown")
    df["reply_content"] = df["reply_content"].fillna("")
    df["is_english"] = df["is_english"].astype(bool)

    # Built row-by-row rather than via df.to_dict(): any attempt to store
    # converted Python datetimes back into a DataFrame column gets silently
    # re-inferred to datetime64 by pandas, turning `None` back into `NaT`
    # (which SQLAlchemy/SQLite cannot bind). Working from raw dicts sidesteps
    # that dtype inference entirely.
    def to_py_dt(value):
        return value.to_pydatetime() if pd.notnull(value) else None

    records = []
    for row in df.to_dict(orient="records"):
        row["review_date"] = to_py_dt(row["review_date"])
        row["replied_at"] = to_py_dt(row["replied_at"])
        records.append(row)

    if not records:
        return 0

    with ENGINE.begin() as conn:
        for i in range(0, len(records), 500):
            batch = records[i : i + 500]
            stmt = sqlite_insert(Review.__table__).values(batch)
            update_cols = {
                c.name: stmt.excluded[c.name]
                for c in Review.__table__.columns
                if c.name != "review_id"
            }
            stmt = stmt.on_conflict_do_update(index_elements=["review_id"], set_=update_cols)
            conn.execute(stmt)

    return len(records)


def main():
    init_db()
    count = load_reviews()
    print(f"Loaded/updated {count} reviews into the database.")


if __name__ == "__main__":
    main()
