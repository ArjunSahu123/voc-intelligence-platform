"""Engine/session management + the fixed product-journey taxonomy seed."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.common.config import DB_PATH
from src.common.models import Base, Category

ENGINE = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=ENGINE)

# name -> journey_stage. This is the fixed taxonomy every classification call
# must pick from (see src/classification/prompts.py) — kept here, not in the
# prompt file, so the DB and the LLM prompt can never drift out of sync.
TAXONOMY = {
    "Discovery / Restaurant Search": "Discovery",
    "Ordering": "Ordering",
    "Checkout": "Ordering",
    "Payment": "Payment",
    "Coupons & Offers": "Payment",
    "Delivery Time": "Fulfillment",
    "Delivery Accuracy": "Fulfillment",
    "Order Cancellation": "Fulfillment",
    "Refund": "Post-Order",
    "Customer Support": "Post-Order",
    "App Crash": "Platform",
    "Performance / Slowness": "Platform",
    "Notifications": "Platform",
    "Login / Signup": "Account",
    "Profile / Account Management": "Account",
    "Subscription (Zomato Gold/Pro)": "Account",
    "General Feedback": "Other",
}


def init_db():
    Base.metadata.create_all(ENGINE)
    seed_taxonomy()


def seed_taxonomy():
    with session_scope() as session:
        existing = {c.name for c in session.query(Category).all()}
        for name, stage in TAXONOMY.items():
            if name not in existing:
                session.add(Category(name=name, journey_stage=stage))


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
