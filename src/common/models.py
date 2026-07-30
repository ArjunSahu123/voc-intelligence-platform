"""SQLAlchemy ORM models — the single source of truth for the schema.

Runs against SQLite by default (see db.py) for zero-install local development,
but every column type used here (String, Integer, Float, Boolean, DateTime,
Date, Text) is a standard SQLAlchemy generic type that maps cleanly onto
PostgreSQL. Pointing DB_PATH/DB_URL at a Postgres connection string is the
only change needed to run this same schema on Postgres — see db/schema.sql
for the hand-documented canonical DDL used in production.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class Review(Base):
    __tablename__ = "reviews"

    review_id = Column(String, primary_key=True)
    user_name = Column(String)
    content_raw = Column(Text, nullable=False)
    content_clean = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False, index=True)
    review_date = Column(DateTime, nullable=False, index=True)
    app_version = Column(String, index=True)
    thumbs_up_count = Column(Integer, default=0)
    language = Column(String)
    is_english = Column(Boolean)
    reply_content = Column(Text)
    replied_at = Column(DateTime)
    ingested_at = Column(DateTime, default=utcnow)

    classifications = relationship("ReviewClassification", back_populates="review")


class Category(Base):
    __tablename__ = "categories"

    category_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    journey_stage = Column(String, nullable=False)
    description = Column(Text)


class ReviewClassification(Base):
    """The current classification for a review (one row per review)."""

    __tablename__ = "review_classifications"

    classification_id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(String, ForeignKey("reviews.review_id"), nullable=False, unique=True, index=True)
    primary_category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=False, index=True)
    secondary_category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    sentiment = Column(String, nullable=False)  # positive | neutral | negative
    severity = Column(String, nullable=False)  # low | medium | high | critical
    urgency = Column(String, nullable=False)  # low | medium | high
    confidence_score = Column(Float, nullable=False)
    model_used = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    classified_at = Column(DateTime, default=utcnow)
    raw_llm_response = Column(Text)

    review = relationship("Review", back_populates="classifications")
    primary_category = relationship("Category", foreign_keys=[primary_category_id])
    secondary_category = relationship("Category", foreign_keys=[secondary_category_id])


class ClassificationRunLog(Base):
    """Run-level audit log for classification batches (not per-review)."""

    __tablename__ = "classification_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    run_started_at = Column(DateTime, nullable=False)
    run_completed_at = Column(DateTime)
    reviews_attempted = Column(Integer, default=0)
    reviews_succeeded = Column(Integer, default=0)
    reviews_failed = Column(Integer, default=0)
    model_used = Column(String)
    prompt_version = Column(String)
    notes = Column(Text)


class WeeklyMetric(Base):
    __tablename__ = "weekly_metrics"
    __table_args__ = (UniqueConstraint("week_start_date", name="uq_weekly_metrics_week"),)

    metric_id = Column(Integer, primary_key=True, autoincrement=True)
    week_start_date = Column(Date, nullable=False, index=True)
    week_end_date = Column(Date, nullable=False)
    total_reviews = Column(Integer, nullable=False)
    avg_rating = Column(Float, nullable=False)
    negative_review_ratio = Column(Float, nullable=False)
    reviews_per_day = Column(Float, nullable=False)
    crash_mentions = Column(Integer, default=0)
    critical_issue_count = Column(Integer, default=0)
    product_health_score = Column(Float)
    computed_at = Column(DateTime, default=utcnow)


class IssueTrend(Base):
    __tablename__ = "issue_trends"
    __table_args__ = (UniqueConstraint("week_start_date", "category_id", name="uq_issue_trend_week_category"),)

    trend_id = Column(Integer, primary_key=True, autoincrement=True)
    week_start_date = Column(Date, nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=False, index=True)
    issue_count = Column(Integer, nullable=False)
    issue_pct = Column(Float, nullable=False)
    severity_score = Column(Float, nullable=False)
    wow_growth_pct = Column(Float)
    z_score = Column(Float)
    computed_at = Column(DateTime, default=utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"

    recommendation_id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.alert_id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    title = Column(String, nullable=False)
    probable_causes = Column(Text)
    customer_impact = Column(Text)
    business_impact = Column(Text)
    recommended_investigation = Column(Text)
    suggested_fix = Column(Text)
    metrics_to_monitor = Column(Text)
    created_at = Column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    detected_at = Column(DateTime, default=utcnow, index=True)
    week_start_date = Column(Date, nullable=False, index=True)
    metric_name = Column(String, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    severity = Column(String, nullable=False)  # info | warning | critical
    z_score = Column(Float)
    baseline_value = Column(Float)
    current_value = Column(Float)
    root_cause_summary = Column(Text)
    representative_quotes = Column(Text)  # JSON-encoded list[str]
    status = Column(String, default="open")  # open | acknowledged | resolved
    created_at = Column(DateTime, default=utcnow)


class Experiment(Base):
    __tablename__ = "experiments"

    experiment_id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.recommendation_id"), nullable=True)
    hypothesis = Column(Text, nullable=False)
    primary_metric = Column(String, nullable=False)
    secondary_metrics = Column(Text)  # JSON-encoded list[str]
    guardrail_metrics = Column(Text)  # JSON-encoded list[str]
    target_users = Column(String)
    baseline_rate = Column(Float)
    mde_pct = Column(Float)
    sample_size_per_variant = Column(Integer)
    power = Column(Float)
    significance_level = Column(Float)
    duration_days = Column(Integer)
    success_criteria = Column(Text)
    expected_risks = Column(Text)
    rollout_plan = Column(Text)
    created_at = Column(DateTime, default=utcnow)


class DashboardCache(Base):
    __tablename__ = "dashboard_cache"

    cache_key = Column(String, primary_key=True)
    payload_json = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=utcnow)
