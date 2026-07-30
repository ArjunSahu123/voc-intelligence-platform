"""One-off backfill: root cause + recommendation + one flagship A/B test
proposal for the 4 real anomalies detect_anomalies() surfaces this week
(Payment, Coupons & Offers, Order Cancellation, Refund).

Why this script exists: the normal path (src/alerts/generate_alerts.py)
calls Gemini for root-cause synthesis and recommendation generation. The
free-tier daily quota was exhausted during development. Rather than leave
the Alerts/Experiments pages empty, or fake an API call, this script
inserts real Alert/Recommendation/Experiment rows written directly from
the actual review evidence (queried below, same reviews an LLM call would
have seen) -- i.e. the analysis a human analyst would produce, done
directly instead of round-tripped through a second API call. Sample size
for the experiment is still computed via the real power-analysis formula
(src/experiments/sample_size.py), not guessed.

This is a backfill for THIS week's specific findings, not a template --
once LLM quota is available, src/alerts/generate_alerts.py is the correct
ongoing path and will skip weeks that already have an alert (see
generate_alerts._already_alerted).
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.db import init_db, session_scope
from src.common.models import Alert, Category, Experiment, Recommendation
from src.experiments.sample_size import sample_size_two_proportions

WEEK = date(2026, 7, 16)

FINDINGS = [
    {
        "category": "Payment",
        "metric_name": "issue_pct:Payment",
        "z_score": None,
        "wow_growth_pct": 41.6,
        "current_value": 0.016,
        "severity": "warning",
        "root_cause_summary": (
            "Payment complaints split into two distinct clusters: (1) fee-transparency complaints, "
            "where customers are frustrated that packaging, delivery, and platform fees stack on top of "
            "the listed item price only at final checkout, turning a ₹346 order into ₹475; and (2) COD "
            "availability/payment-failure complaints, where Cash on Delivery is inconsistently offered "
            "(available on a customer's first order, missing on their next), pushing users toward "
            "prepaid checkout that sometimes fails after the amount has already been deducted, leaving "
            "them with no food and no visible resolution path."
        ),
        "representative_quotes": [
            "the upcharge is ridiculous: making all items more expensive in app and then adding "
            "packaging, delivery and platform fee on top",
            "it is so expensive my order was 346 but it turned to be 475 not valid",
            "so deducting money but still showing payment failed when it's your app fault is somehow ok right",
            "when my Frist order has successfull but second order has seen to cash on delivery not "
            "unavailable am very hungry",
        ],
        "recommendation": {
            "title": "Surface total price and COD eligibility earlier in checkout",
            "customer_impact": (
                "Customers currently discover the true order total (after packaging/delivery/platform "
                "fees) and their payment-method options only at the final checkout step, after they've "
                "already selected items and started to commit — a late, unpleasant surprise that reads "
                "as deceptive pricing, and in the worst cases, a failed payment with no food and no clear "
                "resolution."
            ),
            "business_impact": (
                "Erodes trust in exactly the category (Payment) most tied to completed-transaction "
                "revenue; a customer whose money is deducted with no order delivered is a chargeback-risk "
                "and support-cost driver, not just a bad review."
            ),
            "recommended_investigation": (
                "Pull order-level data (outside review text) for the last 2 weeks: (1) % of orders where "
                "COD was available on a customer's prior order but not their next order from the same "
                "restaurant, (2) failed-payment-but-charged incident rate and average resolution time, "
                "(3) average total fee stack as a % of item subtotal, segmented by order value."
            ),
            "suggested_fix": (
                "Two-part, low-risk UI change (no fee restructuring, no COD policy change): (1) show a "
                "running 'estimated total incl. fees' line as soon as the first item is added to cart, "
                "not only at final checkout; (2) show a COD-availability badge on the restaurant page "
                "before item selection, so unavailability is known upfront rather than discovered at payment."
            ),
            "metrics_to_monitor": [
                "Payment category issue_pct",
                "Cart abandonment rate at checkout step",
                "Failed-payment-but-charged incident rate",
                "COD order share vs. prepaid order share",
            ],
        },
    },
    {
        "category": "Coupons & Offers",
        "metric_name": "issue_pct:Coupons & Offers",
        "z_score": None,
        "wow_growth_pct": 69.9,
        "current_value": 0.0192,
        "severity": "warning",
        "root_cause_summary": (
            "Coupon complaints center on a perceived 'fake discount': customers report that in-app menu "
            "prices are marked up above the restaurant's actual/dine-in prices, so applying a coupon "
            "still leaves the final total higher than ordering directly — making the discount feel "
            "illusory. A smaller cluster reports coupons/cashback simply failing to apply. Sentiment on "
            "this category is notably bifurcated (many reviews praise the offers), so the complaint is "
            "concentrated among price-comparison-aware customers, not universal."
        ),
        "representative_quotes": [
            "For some restaurants online menu rate is much higher than actual menu. In such case "
            "ordering food directly from restaurant is way cheaper than Zomato. After applying coupon "
            "of 100Rs off, still final amount higher",
            "Zomato tricks customers with the offers. There are never any real discounts.",
            "paytam cashback order not working fake coupon",
        ],
        "recommendation": {
            "title": "Address perceived coupon deception from marked-up menu pricing",
            "customer_impact": (
                "Price-comparison-aware customers feel actively misled — they believe they're getting a "
                "discount but end up paying more than ordering directly, a stronger negative reaction "
                "than a simple 'no discount available' complaint."
            ),
            "business_impact": (
                "This is a trust/brand-integrity risk, not just a pricing complaint — 'tricks customers' "
                "in a public review is reputationally worse than 'expensive,' and it specifically "
                "undermines the ROI of running coupons at all if customers don't believe the savings "
                "are real."
            ),
            "recommended_investigation": (
                "Sample 20-30 restaurants and compare in-app menu price for 3-5 common items against "
                "the restaurant's own dine-in price to quantify how widespread the markup actually is; "
                "separately, pull coupon-application failure rate from payment logs to size the "
                "technical-failure cluster."
            ),
            "suggested_fix": (
                "If markup is confirmed: pilot a 'verified price parity' badge on a subset of high-volume "
                "restaurants where in-app price is confirmed to match dine-in price, and measure whether "
                "coupon-related complaints differ for that subset vs. control. If the technical cashback "
                "failure is the bigger driver, prioritize the fix plus an explicit in-app error message "
                "when a coupon fails to apply."
            ),
            "metrics_to_monitor": [
                "Coupons & Offers category issue_pct",
                "Coupon redemption success rate",
                "Repeat-order rate for customers who used a coupon in their prior order",
            ],
        },
    },
    {
        "category": "Order Cancellation",
        "metric_name": "issue_pct:Order Cancellation",
        "z_score": None,
        "wow_growth_pct": -41.4,
        "current_value": 0.0099,
        "severity": "warning",
        "root_cause_summary": (
            "Order Cancellation complaints (down 41% week-over-week, but still a real cluster) center on "
            "customers being charged the FULL order amount as a cancellation fee even when the "
            "cancellation was not their fault — most commonly, no delivery partner was assigned within a "
            "reasonable window (a pattern reviewers associate with orders placed after 9pm), or the "
            "restaurant was delayed, and Zomato auto-cancels the order but still applies a fee as if the "
            "customer had cancelled voluntarily."
        ),
        "representative_quotes": [
            "you guys charge the full amount of the order as a cancellation fee.. WOW... PATHETIC "
            "SERVICE... I'm a gold member and you guys didn't even bother to call",
            "Don't order after 9 pm 99percent do not assign delivery partner and just waste our time and money",
            "once I order a food but when I try to cancel it took entire amount of charge such a "
            "ridiculous app",
        ],
        "recommendation": {
            "title": "Waive cancellation fees for platform-initiated cancellations",
            "customer_impact": (
                "Customers who did nothing wrong (no delivery partner available, or restaurant delay) "
                "are charged as if they cancelled by choice — this reads as unfair, which is why the "
                "complaint language here is markedly angrier than in other categories."
            ),
            "business_impact": (
                "Directly damages loyalty-tier customers' trust (the highest-engagement complaint in "
                "this category is from a Gold member), and every voluntary auto-cancellation-with-fee "
                "incident is a near-guaranteed 1-star review and support contact — both costing more "
                "than the fee revenue itself."
            ),
            "recommended_investigation": (
                "Pull the cancellation reason code (already logged internally) split by customer-"
                "initiated vs. system-initiated, and check whether the fee-charging logic currently "
                "reads that field before applying a fee."
            ),
            "suggested_fix": (
                "Auto-waive the cancellation fee when the cancellation reason is system-initiated (no "
                "delivery partner assigned, restaurant-side delay past SLA); separately, send a proactive "
                "in-app notification when an order is at risk of auto-cancellation instead of letting it "
                "happen silently."
            ),
            "metrics_to_monitor": [
                "Order Cancellation category issue_pct",
                "System-initiated cancellation rate",
                "Fee-waiver-eligible cancellation volume (to size the revenue tradeoff before shipping)",
            ],
        },
    },
    {
        "category": "Refund",
        "metric_name": "issue_pct:Refund",
        "z_score": None,
        "wow_growth_pct": -71.2,
        "current_value": 0.0065,
        "severity": "warning",
        "root_cause_summary": (
            "Refund complaints (down 71% week-over-week) describe customer support verbally committing "
            "to a refund — for missing items, a cancelled order, or an undelivered order — that then "
            "doesn't materialize, or is silently substituted with a coupon/replacement product instead "
            "of cash. Several reviews use the word 'fraud' or 'scam', indicating this reads as a trust "
            "violation, not a service delay."
        ),
        "representative_quotes": [
            "The don't refund the amount after their customer care says that they will.",
            "they don't refund your money, after order get canceled. They are running a scam.",
            "koi issue hone y time p ye refund nhi krte, coupon dete h ya koi dusra product bhijvate h "
            "par refund nhi krte",
        ],
        "recommendation": {
            "title": "Confirm and communicate refund SLA; stop silent coupon substitution",
            "customer_impact": (
                "Customers promised a cash refund who instead silently receive a coupon (or nothing, "
                "within their observation window) feel deceived twice — once by the original service "
                "failure, again by an unmet support promise."
            ),
            "business_impact": (
                "'Fraud'/'scam' language is disproportionately damaging to brand trust relative to the "
                "small dollar amounts typically involved in individual refunds — a cheap problem to fix "
                "relative to the reputational cost of not fixing it."
            ),
            "recommended_investigation": (
                "Confirm actual refund processing time distribution (median and p90) against what "
                "customer support tells customers verbally, and check what fraction of 'refunds' are "
                "currently auto-converted to coupon/credit rather than cash without explicit customer opt-in."
            ),
            "suggested_fix": (
                "Make refund method (cash/original payment method vs. coupon) an explicit customer "
                "choice at the point support agrees to refund, and add a visible refund-status tracker "
                "in-app so customers aren't relying on a verbal promise with no follow-up visibility."
            ),
            "metrics_to_monitor": [
                "Refund category issue_pct",
                "Refund SLA adherence (promised vs. actual processing time)",
                "% of refunds auto-substituted with coupon/credit vs. cash",
            ],
        },
    },
]

# Flagship experiment: Payment, the highest-stakes finding (revenue + trust,
# clearest evidence, two independently actionable root causes).
PAYMENT_EXPERIMENT = {
    "hypothesis": (
        "If we show a running fee-inclusive estimated total starting when the first item is added to "
        "cart (rather than only at final checkout), and display a Cash-on-Delivery availability badge "
        "on the restaurant page before item selection, then the Payment category's negative review rate "
        "will decrease, because the two dominant complaint drivers — surprise fee stacking and payment-"
        "method mismatch — are surfaced at the point of decision instead of after the customer has "
        "already committed to an order."
    ),
    "primary_metric": "Payment category issue_pct (weekly, severity-weighted)",
    "secondary_metrics": [
        "Cart abandonment rate at checkout",
        "Failed-payment-but-charged incident rate",
        "Customer support contacts tagged 'payment' per 1,000 orders",
    ],
    "guardrail_metrics": [
        "Overall order completion rate (must not drop)",
        "Average order value (must not drop more than 2% — fee transparency could itself suppress ordering)",
        "Cart/restaurant page load latency (must not regress from added UI elements)",
    ],
    "target_users": (
        "All customers viewing a restaurant page or cart in the test market, randomized at the session "
        "level (not user level, to avoid one user seeing inconsistent experiences across sessions during the test)."
    ),
    "success_criteria": (
        "Payment category issue_pct decreases by at least 20% relative to control within the test "
        "window, with no guardrail metric regressing beyond its stated threshold."
    ),
    "expected_risks": (
        "Showing the full fee-inclusive total earlier in the funnel could suppress order-initiation if "
        "customers weren't previously registering the fee stack at all — i.e. transparency could reduce "
        "orders even as it improves sentiment. The order-completion and AOV guardrails exist specifically "
        "to catch this tradeoff before declaring the experiment a pure win."
    ),
    "rollout_plan": (
        "5% of sessions -> 25% -> 50% -> 100%, with a minimum 1-week hold at each stage so a full weekly "
        "review cycle accumulates before advancing, and an automatic rollback trigger if the "
        "order-completion guardrail drops more than 3% at any stage."
    ),
}
MDE_PCT_RELATIVE = 20.0


def main():
    init_db()

    with session_scope() as session:
        category_ids = {c.name: c.category_id for c in session.query(Category).all()}

        for finding in FINDINGS:
            cat_id = category_ids[finding["category"]]

            existing = (
                session.query(Alert)
                .filter(Alert.metric_name == finding["metric_name"], Alert.week_start_date == WEEK)
                .first()
            )
            if existing:
                print(f"Skipping {finding['category']} — alert already exists for this week.")
                continue

            alert = Alert(
                week_start_date=WEEK,
                metric_name=finding["metric_name"],
                category_id=cat_id,
                severity=finding["severity"],
                z_score=finding["z_score"],
                current_value=finding["current_value"],
                root_cause_summary=finding["root_cause_summary"],
                representative_quotes=json.dumps(finding["representative_quotes"]),
                status="open",
            )
            session.add(alert)
            session.flush()

            rec = finding["recommendation"]
            recommendation = Recommendation(
                alert_id=alert.alert_id,
                category_id=cat_id,
                title=rec["title"],
                customer_impact=rec["customer_impact"],
                business_impact=rec["business_impact"],
                recommended_investigation=rec["recommended_investigation"],
                suggested_fix=rec["suggested_fix"],
                metrics_to_monitor="; ".join(rec["metrics_to_monitor"]),
            )
            session.add(recommendation)
            session.flush()

            print(f"Inserted alert + recommendation for {finding['category']} (alert_id={alert.alert_id}, recommendation_id={recommendation.recommendation_id})")

            if finding["category"] == "Payment":
                payment_recommendation_id = recommendation.recommendation_id

        # Flagship experiment for the Payment recommendation, real power-analysis sizing.
        existing_exp = session.query(Experiment).filter(Experiment.recommendation_id == payment_recommendation_id).first()
        if existing_exp:
            print("Skipping experiment — one already exists for the Payment recommendation.")
        else:
            baseline_rate = 0.016  # Payment issue_pct, week of 2026-07-16
            sizing = sample_size_two_proportions(baseline_rate, MDE_PCT_RELATIVE)
            reviews_per_day = 707.29  # from weekly_metrics for this week
            assumed_daily_eligible_users = max(reviews_per_day * 100, 1)  # REVIEW_TO_DAU_MULTIPLIER, see ab_test_design.py
            duration_days = max(int(round((sizing["sample_size_per_variant"] * 2) / assumed_daily_eligible_users)), 7)

            experiment = Experiment(
                recommendation_id=payment_recommendation_id,
                hypothesis=PAYMENT_EXPERIMENT["hypothesis"],
                primary_metric=PAYMENT_EXPERIMENT["primary_metric"],
                secondary_metrics=json.dumps(PAYMENT_EXPERIMENT["secondary_metrics"]),
                guardrail_metrics=json.dumps(PAYMENT_EXPERIMENT["guardrail_metrics"]),
                target_users=PAYMENT_EXPERIMENT["target_users"],
                baseline_rate=sizing["baseline_rate"],
                mde_pct=MDE_PCT_RELATIVE,
                sample_size_per_variant=sizing["sample_size_per_variant"],
                power=sizing["power"],
                significance_level=sizing["alpha"],
                duration_days=duration_days,
                success_criteria=PAYMENT_EXPERIMENT["success_criteria"],
                expected_risks=PAYMENT_EXPERIMENT["expected_risks"],
                rollout_plan=PAYMENT_EXPERIMENT["rollout_plan"],
            )
            session.add(experiment)
            session.flush()
            print(f"Inserted experiment (experiment_id={experiment.experiment_id}) for Payment recommendation.")


if __name__ == "__main__":
    main()
