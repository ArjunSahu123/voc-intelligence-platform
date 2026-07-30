# System Design Document

## 1. Architecture Overview

The platform is a batch pipeline, not a real-time system — reviews arrive in weekly cadences, not a
stream requiring sub-second processing, so there is no message queue or streaming layer. Every stage
is a plain Python module with a `main()` entrypoint, individually runnable and independently testable,
chained together by `src/automation/run_pipeline.py`. The database (SQLite locally, Postgres-ready
schema for production) is the single integration point between stages — no stage passes state to the
next via in-memory objects or temp files that the dashboard/API can't also see.

```
Play Store  --(scrape)-->  raw JSONL (append-only, immutable)
                              |
                          (clean)
                              v
                        processed CSV
                              |
                          (load, upsert)
                              v
                        SQLite / Postgres  <---- FastAPI, Streamlit, weekly_report all read from here
                              |
                    (classify via Claude)
                              v
                     review_classifications
                              |
                     (compute weekly metrics)
                              v
                  weekly_metrics, issue_trends
                              |
                    (z-score anomaly detection)
                              v
                     anomalies (in-memory list)
                              |
              (root-cause + recommend via Claude)
                              v
                       alerts, recommendations
                              |
                    (power-analysis sizing)
                              v
                          experiments
```

## 2. Key Design Decisions

**Why SQLite locally with a hand-written Postgres DDL, instead of just using Postgres?**
Zero-install local development matters for a portfolio project a hiring manager will actually try to
run. Every SQLAlchemy model uses generic column types (String, Integer, Float, Boolean, DateTime,
Date, Text) that map identically onto Postgres — `db/schema.sql` is the same schema hand-documented in
Postgres DDL with the reasoning for every index and constraint, so the "production path" is fully
specified even though the demo runs on SQLite.

**Why batch classification calls (10 reviews/call) instead of one call per review?**
API latency and cost both scale roughly linearly with call count more than with token count for short
texts like reviews. At review-taxonomy-classification token sizes, a batch of 10 costs barely more per
call than a batch of 1, so batching is a ~10x cost/latency reduction with no accuracy tradeoff (each
review is still classified independently within the batch, referenced by index).

**Why an expanding window for anomaly baselines instead of a fixed trailing window?**
A fixed N-week trailing window is the textbook-correct choice once a product has deep history, because
it adapts to slow drift/seasonality. But a new deployment (or this demo, capped at ~2 weeks of Play
Store history) has almost no history at all — a fixed 4-week window would refuse to compute a baseline
for the first month of operation. An expanding window (mean/std of *all* prior weeks) is the right
choice for a system's early life; the code comments explicitly flag switching to a trailing window as
future work once 12+ weeks of real history accumulate.

**Why separate root-cause analysis from recommendation generation into two LLM calls?**
Root cause is evidence retrieval and summarization — "what do the affected reviews actually say."
Recommendation is product judgment layered on top of that evidence — "so what, and what should we do."
Keeping them as separate calls (rather than one combined prompt) means either can be re-run
independently: e.g., re-prompting for a different recommendation framing (cost-focused vs.
retention-focused) without re-summarizing the same batch of reviews, or auditing whether a bad
recommendation traces back to bad evidence or bad reasoning on top of good evidence.

**Why compute sample size with scipy, not ask Claude for a number?**
Anything with a single mathematically correct answer should never be an LLM's job — an LLM can narrate
around a number, but should not be the source of the number itself. `src/experiments/sample_size.py`
implements the standard two-proportion power-analysis formula directly; the LLM call in
`ab_test_design.py` is fed the already-computed baseline rate, target rate, sample size, and duration
as fixed context and only writes the qualitative fields (hypothesis, target segment, guardrails,
rollout plan) around them.

**Why does `run_pipeline.py` continue after a step fails instead of aborting?**
A classification-API rate limit or transient network failure on step 4 (LLM classification) shouldn't
prevent steps 5-8 (metrics/anomaly/report) from running against whatever *was* successfully classified
in prior runs — a partial weekly report from stale-but-real classifications is more useful to a PM than
no report at all. Each step is wrapped individually and the run's exit code only reflects true failures
(non-zero if anything failed), so a cron/CI wrapper can still alert on real problems.

## 3. Scalability

At the current single-app, weekly-cadence scale (thousands of reviews/week), SQLite + a Python batch
job is more than sufficient — there is no reason to run a distributed job scheduler for this volume.
The scaling path, in order of when each becomes necessary:

1. **Postgres over SQLite** — first bottleneck is concurrent writers (dashboard reads + a live pipeline
   write), which SQLite tolerates poorly. `db/schema.sql` is already the target schema.
2. **Async/parallel LLM calls** — classification currently runs batches sequentially with a small sleep
   between them; at 10-50x current review volume, running batches concurrently (with a semaphore to
   respect rate limits) is the next lever before anything architectural changes.
3. **Multiple ingestion sources** — the ingestion layer is a single adapter
   (`src/ingestion/scrape_reviews.py`) writing a common raw-review JSONL shape; adding a second source
   (App Store, internal support tickets) means writing a second adapter that emits the same shape, not
   redesigning downstream stages.
4. **A real job scheduler** (Airflow/Dagster/Prefect) only becomes worth the operational overhead once
   there are multiple apps/sources running on independent schedules with cross-job dependencies — for a
   single weekly `run_pipeline.py` cron entry, that complexity isn't earned yet.

## 4. Tradeoffs Made Explicitly

- **Denominator choice for issue_pct**: computed against reviews *classified* that week, not all
  reviews scraped that week — using total-scraped would silently understate every issue percentage
  whenever classification hasn't caught up to ingestion (see `src/metrics/compute_metrics.py`).
- **Duration estimate for experiments uses a documented proxy** (`REVIEW_TO_DAU_MULTIPLIER` in
  `ab_test_design.py`) because Play Store reviews give review volume, not true DAU/order volume. A
  production deployment would replace this with a real query against the experimentation platform's
  eligible-user count — flagged in code rather than presented as a real number.
- **Report narrative degrades gracefully without an LLM key** — the weekly report and alert pipeline
  are designed to still produce useful (if less narratively polished) output when `ANTHROPIC_API_KEY`
  is unset or a call fails, rather than blocking the entire weekly run on LLM availability.

## 5. Monitoring & Failure Recovery

- `classification_logs` is an append-only audit trail of every classification batch run (attempted /
  succeeded / failed counts, model + prompt version used) — a regression in classification quality
  after a prompt change is traceable to the exact run and prompt_version.
- `alerts.status` (open/acknowledged/resolved) gives alerts a lifecycle rather than being fire-and-forget
  — `generate_alerts.py` also skips re-creating an alert for a metric/week pair that's already open, so
  re-running the pipeline mid-week doesn't spam duplicate alerts.
- `run_pipeline.py`'s per-step try/except plus final non-zero exit code on any failure is the hook point
  for external monitoring (a cron wrapper that pages on non-zero exit, or a CI job that fails the build).
- Recovery from a bad classification prompt version: `review_classifications` has one row per review
  (overwritten on re-classification), so re-running the classifier with a fixed prompt against the same
  reviews is idempotent — no manual cleanup needed before re-running.

## 6. What Would Change for a Real Production Deployment

- Swap SQLite -> Postgres, add connection pooling and a read replica for the dashboard/API.
- Move `run_pipeline.py` from a single cron entry to a scheduler with per-step retries and alerting.
- Add an internal-tickets or App Store ingestion adapter as the second proof point for
  "product-agnostic."
- Populate `dashboard_cache` (table already modeled) so the API/dashboard don't recompute aggregations
  on every request once traffic grows past a handful of internal users.
