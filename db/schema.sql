-- Voice of Customer Intelligence Platform — canonical schema (PostgreSQL DDL).
--
-- The running system in this repo executes on SQLite via SQLAlchemy
-- (src/common/models.py) so the project has zero external dependencies to
-- demo locally. This file is the schema as it would be deployed in
-- production on PostgreSQL — every type and constraint here matches the
-- SQLAlchemy models 1:1, so "swap to Postgres" is a connection-string change,
-- not a redesign.

CREATE TABLE reviews (
    review_id           TEXT PRIMARY KEY,
    user_name           TEXT,
    content_raw         TEXT NOT NULL,
    content_clean       TEXT NOT NULL,
    rating              SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_date         TIMESTAMPTZ NOT NULL,
    app_version         TEXT,
    thumbs_up_count     INTEGER DEFAULT 0,
    language            TEXT,
    is_english          BOOLEAN,
    reply_content       TEXT,
    replied_at          TIMESTAMPTZ,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reviews_review_date ON reviews (review_date);
CREATE INDEX idx_reviews_app_version ON reviews (app_version);
CREATE INDEX idx_reviews_rating ON reviews (rating);

-- Fixed product-journey taxonomy. Kept in its own table (rather than a free
-- text column on reviews) so trend/heatmap queries can GROUP BY a stable
-- surrogate key even if a category's display name is later edited.
CREATE TABLE categories (
    category_id     SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    journey_stage   TEXT NOT NULL,   -- Discovery | Ordering | Payment | Fulfillment | Post-Order | Platform | Account | Other
    description     TEXT
);

-- Current classification for a review. One row per review (re-classifying
-- overwrites in place); classification_logs below is the append-only
-- run-level audit trail.
CREATE TABLE review_classifications (
    classification_id      SERIAL PRIMARY KEY,
    review_id               TEXT NOT NULL UNIQUE REFERENCES reviews(review_id),
    primary_category_id     INTEGER NOT NULL REFERENCES categories(category_id),
    secondary_category_id   INTEGER REFERENCES categories(category_id),
    sentiment                TEXT NOT NULL CHECK (sentiment IN ('positive', 'neutral', 'negative')),
    severity                 TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    urgency                  TEXT NOT NULL CHECK (urgency IN ('low', 'medium', 'high')),
    confidence_score         REAL NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    model_used               TEXT NOT NULL,
    prompt_version           TEXT NOT NULL,
    classified_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_llm_response         JSONB
);
CREATE INDEX idx_classifications_primary_category ON review_classifications (primary_category_id);

-- Append-only audit log of each classification batch run (not per-review).
CREATE TABLE classification_logs (
    log_id              SERIAL PRIMARY KEY,
    run_started_at       TIMESTAMPTZ NOT NULL,
    run_completed_at     TIMESTAMPTZ,
    reviews_attempted    INTEGER DEFAULT 0,
    reviews_succeeded    INTEGER DEFAULT 0,
    reviews_failed       INTEGER DEFAULT 0,
    model_used           TEXT,
    prompt_version       TEXT,
    notes                TEXT
);

CREATE TABLE weekly_metrics (
    metric_id               SERIAL PRIMARY KEY,
    week_start_date          DATE NOT NULL UNIQUE,
    week_end_date            DATE NOT NULL,
    total_reviews            INTEGER NOT NULL,
    avg_rating               REAL NOT NULL,
    negative_review_ratio    REAL NOT NULL,
    reviews_per_day          REAL NOT NULL,
    crash_mentions           INTEGER DEFAULT 0,
    critical_issue_count     INTEGER DEFAULT 0,
    product_health_score     REAL,
    computed_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE issue_trends (
    trend_id            SERIAL PRIMARY KEY,
    week_start_date      DATE NOT NULL,
    category_id          INTEGER NOT NULL REFERENCES categories(category_id),
    issue_count          INTEGER NOT NULL,
    issue_pct            REAL NOT NULL,   -- issue_count / total_reviews that week
    severity_score       REAL NOT NULL,   -- severity-weighted count, see metrics/health_score.py
    wow_growth_pct        REAL,           -- week-over-week % change
    z_score               REAL,           -- vs trailing rolling mean/std, see anomaly/detect_anomalies.py
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (week_start_date, category_id)
);
CREATE INDEX idx_issue_trends_week ON issue_trends (week_start_date);

CREATE TABLE recommendations (
    recommendation_id           SERIAL PRIMARY KEY,
    alert_id                     INTEGER,  -- FK added below after alerts exists
    category_id                  INTEGER REFERENCES categories(category_id),
    title                        TEXT NOT NULL,
    probable_causes              TEXT,
    customer_impact              TEXT,
    business_impact              TEXT,
    recommended_investigation    TEXT,
    suggested_fix                TEXT,
    metrics_to_monitor           TEXT,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
    alert_id                SERIAL PRIMARY KEY,
    detected_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    week_start_date           DATE NOT NULL,
    metric_name               TEXT NOT NULL,   -- e.g. 'issue_pct:Payment', 'avg_rating'
    category_id               INTEGER REFERENCES categories(category_id),
    severity                  TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    z_score                   REAL,
    baseline_value            REAL,
    current_value             REAL,
    root_cause_summary        TEXT,
    representative_quotes     JSONB,
    status                    TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved')),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_alerts_week ON alerts (week_start_date);
CREATE INDEX idx_alerts_status ON alerts (status);

ALTER TABLE recommendations ADD CONSTRAINT fk_recommendations_alert
    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id);

CREATE TABLE experiments (
    experiment_id                SERIAL PRIMARY KEY,
    recommendation_id            INTEGER REFERENCES recommendations(recommendation_id),
    hypothesis                   TEXT NOT NULL,
    primary_metric                TEXT NOT NULL,
    secondary_metrics             JSONB,
    guardrail_metrics             JSONB,
    target_users                  TEXT,
    baseline_rate                 REAL,
    mde_pct                       REAL,   -- minimum detectable effect, %
    sample_size_per_variant       INTEGER,
    power                          REAL,
    significance_level             REAL,
    duration_days                  INTEGER,
    success_criteria               TEXT,
    expected_risks                 TEXT,
    rollout_plan                   TEXT,
    created_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Precomputed JSON payloads the dashboard/API read instead of recomputing
-- aggregations on every page load.
CREATE TABLE dashboard_cache (
    cache_key       TEXT PRIMARY KEY,
    payload_json    JSONB NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
