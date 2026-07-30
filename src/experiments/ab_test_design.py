"""Generates a structured A/B test proposal from a Recommendation row.

Numbers that matter (baseline rate, sample size, duration) are computed
statistically, not written by the LLM — the LLM's job is the narrative
framing (hypothesis, target users, guardrails, rollout plan) built ON TOP of
those pre-computed numbers, fed into its prompt so it can't invent
inconsistent figures.

Honest limitation, stated rather than papered over: this platform's data
source is Play Store reviews, which gives review volume, not the app's true
daily active user / order count. Duration-to-reach-sample-size therefore
uses an explicit, documented proxy assumption (REVIEW_TO_DAU_MULTIPLIER)
rather than fabricating a real DAU figure — in a production deployment this
would instead query the actual experimentation platform's eligible-user
count for the target segment.
"""
import json

from src.common.db import ENGINE, init_db, session_scope
from src.common.llm_client import call_structured
from src.common.models import Experiment, IssueTrend, Recommendation, WeeklyMetric
from src.experiments.sample_size import sample_size_two_proportions

# Smallest relative reduction in the issue/negative-rate considered worth
# shipping a fix for — smaller effects are hard to act on even if real.
DEFAULT_MDE_PCT_RELATIVE = 20.0

# Documented proxy: industry rule-of-thumb is roughly 0.5-1 review per 100
# daily active users for a consumer app. 100x is a conservative midpoint
# stand-in for "we don't have real DAU here" — replace with a real
# analytics-warehouse query (e.g. daily unique order-placing users) in
# production.
REVIEW_TO_DAU_MULTIPLIER = 100

EXPERIMENT_TOOL = {
    "name": "experiment_design",
    "description": "Narrative fields for an A/B test proposal; numeric fields are supplied separately.",
    "input_schema": {
        "type": "object",
        "properties": {
            "hypothesis": {"type": "string", "description": "If [change], then [metric] will [effect], because [reasoning]."},
            "primary_metric": {"type": "string"},
            "secondary_metrics": {"type": "array", "items": {"type": "string"}},
            "guardrail_metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Metrics that must NOT regress even if the primary metric improves.",
            },
            "target_users": {"type": "string", "description": "The eligible segment for this experiment."},
            "success_criteria": {"type": "string"},
            "expected_risks": {"type": "string"},
            "rollout_plan": {"type": "string", "description": "e.g. 5% -> 25% -> 50% -> 100%, with gates."},
        },
        "required": [
            "hypothesis",
            "primary_metric",
            "secondary_metrics",
            "guardrail_metrics",
            "target_users",
            "success_criteria",
            "expected_risks",
            "rollout_plan",
        ],
    },
}


def _get_baseline_rate(recommendation: Recommendation) -> float:
    with session_scope() as session:
        if recommendation.category_id:
            latest = (
                session.query(IssueTrend)
                .filter(IssueTrend.category_id == recommendation.category_id)
                .order_by(IssueTrend.week_start_date.desc())
                .first()
            )
            if latest:
                return max(latest.issue_pct, 0.01)
        latest_week = session.query(WeeklyMetric).order_by(WeeklyMetric.week_start_date.desc()).first()
        return max(latest_week.negative_review_ratio, 0.01) if latest_week else 0.10


def _estimate_duration_days(sample_size_per_variant: int) -> int:
    with session_scope() as session:
        latest_week = session.query(WeeklyMetric).order_by(WeeklyMetric.week_start_date.desc()).first()
        reviews_per_day = latest_week.reviews_per_day if latest_week else 50
    assumed_daily_eligible_users = max(reviews_per_day * REVIEW_TO_DAU_MULTIPLIER, 1)
    total_needed = sample_size_per_variant * 2  # both variants
    return max(int(round(total_needed / assumed_daily_eligible_users)), 7)  # never propose <1 week


def build_experiment(recommendation_id: int, mde_pct_relative: float = DEFAULT_MDE_PCT_RELATIVE) -> dict:
    init_db()
    with session_scope() as session:
        recommendation = session.get(Recommendation, recommendation_id)
        if recommendation is None:
            raise ValueError(f"Recommendation {recommendation_id} not found.")
        rec_snapshot = {
            "title": recommendation.title,
            "customer_impact": recommendation.customer_impact,
            "business_impact": recommendation.business_impact,
            "suggested_fix": recommendation.suggested_fix,
        }

    baseline_rate = _get_baseline_rate(recommendation)
    sizing = sample_size_two_proportions(baseline_rate, mde_pct_relative)
    duration_days = _estimate_duration_days(sizing["sample_size_per_variant"])

    prompt = (
        f"Recommendation: {rec_snapshot['title']}\n"
        f"Customer impact: {rec_snapshot['customer_impact']}\n"
        f"Business impact: {rec_snapshot['business_impact']}\n"
        f"Suggested fix to test: {rec_snapshot['suggested_fix']}\n\n"
        f"Pre-computed experiment sizing (do not change these numbers, just design around them):\n"
        f"- Baseline rate: {sizing['baseline_rate']*100:.1f}%\n"
        f"- Target rate if successful: {sizing['target_rate']*100:.1f}% "
        f"({mde_pct_relative:.0f}% relative reduction)\n"
        f"- Sample size per variant: {sizing['sample_size_per_variant']}\n"
        f"- Estimated duration: {duration_days} days\n\n"
        "Design a rigorous A/B test proposal for this fix."
    )

    narrative = call_structured(
        user_message=prompt,
        json_schema=EXPERIMENT_TOOL["input_schema"],
        tool_name=EXPERIMENT_TOOL["name"],
    )

    with session_scope() as session:
        experiment = Experiment(
            recommendation_id=recommendation_id,
            hypothesis=narrative["hypothesis"],
            primary_metric=narrative["primary_metric"],
            secondary_metrics=json.dumps(narrative["secondary_metrics"]),
            guardrail_metrics=json.dumps(narrative["guardrail_metrics"]),
            target_users=narrative["target_users"],
            baseline_rate=sizing["baseline_rate"],
            mde_pct=mde_pct_relative,
            sample_size_per_variant=sizing["sample_size_per_variant"],
            power=sizing["power"],
            significance_level=sizing["alpha"],
            duration_days=duration_days,
            success_criteria=narrative["success_criteria"],
            expected_risks=narrative["expected_risks"],
            rollout_plan=narrative["rollout_plan"],
        )
        session.add(experiment)
        session.flush()
        experiment_id = experiment.experiment_id

    return {"experiment_id": experiment_id, **sizing, "duration_days": duration_days}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate an A/B test proposal from a recommendation.")
    parser.add_argument("recommendation_id", type=int)
    parser.add_argument("--mde", type=float, default=DEFAULT_MDE_PCT_RELATIVE)
    args = parser.parse_args()

    result = build_experiment(args.recommendation_id, args.mde)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
