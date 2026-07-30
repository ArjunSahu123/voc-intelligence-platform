"""Integration tests against a throwaway SQLite file (never the real db/voc.db)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.common.db import TAXONOMY
from src.common.models import Base, Category, Review


@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return engine


def test_schema_creates_all_expected_tables(db_engine):
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "reviews",
        "categories",
        "review_classifications",
        "classification_logs",
        "weekly_metrics",
        "issue_trends",
        "recommendations",
        "alerts",
        "experiments",
        "dashboard_cache",
    }
    assert expected.issubset(table_names)


def test_taxonomy_seeding_is_unique(db_engine):
    Session = sessionmaker(bind=db_engine)
    with Session() as session:
        for name, stage in TAXONOMY.items():
            session.add(Category(name=name, journey_stage=stage))
        session.commit()

        count = session.query(Category).count()
        assert count == len(TAXONOMY)


def test_category_name_uniqueness_enforced(db_engine):
    Session = sessionmaker(bind=db_engine)
    with Session() as session:
        session.add(Category(name="App Crash", journey_stage="Platform"))
        session.commit()

        session.add(Category(name="App Crash", journey_stage="Platform"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_review_upsert_is_idempotent(db_engine):
    review = {
        "review_id": "abc123",
        "user_name": "test_user",
        "content_raw": "Great app",
        "content_clean": "Great app",
        "rating": 5,
        "review_date": datetime.now(timezone.utc),
        "app_version": "1.0.0",
        "thumbs_up_count": 1,
        "language": "en",
        "is_english": True,
        "reply_content": "",
        "replied_at": None,
    }
    with db_engine.begin() as conn:
        conn.execute(sqlite_insert(Review.__table__).values(review))

    updated = {**review, "thumbs_up_count": 99}
    with db_engine.begin() as conn:
        stmt = sqlite_insert(Review.__table__).values(updated)
        update_cols = {c.name: stmt.excluded[c.name] for c in Review.__table__.columns if c.name != "review_id"}
        stmt = stmt.on_conflict_do_update(index_elements=["review_id"], set_=update_cols)
        conn.execute(stmt)

    Session = sessionmaker(bind=db_engine)
    with Session() as session:
        rows = session.query(Review).all()
        assert len(rows) == 1
        assert rows[0].thumbs_up_count == 99
