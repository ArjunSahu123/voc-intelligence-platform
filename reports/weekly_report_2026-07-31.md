# Weekly Product Report — Week of 2026-07-16
_Note: 1 more recent week(s) starting 2026-07-23 are excluded from this report's headline — Google Play's review-indexing lag means the most recent few days always look artificially sparse at scrape time. They'll be included once review volume for those weeks catches up in a later run._
## Executive Summary
Automated narrative unavailable this run (no LLM access) — see the tables below for the underlying numbers.
## Top Findings
- **4951 reviews** this week, average rating **4.00/5**
- **Product Health Score: 78.2/100** (up from 74.9 last week)
- **91** critical-severity issues, **11** crash mentions
## Biggest Issues
| Category | Issue % | Severity Score | WoW Growth |
|---|---|---|---|
| General Feedback | 75.6% | 80.3 | -0% |
| Delivery Accuracy | 4.6% | 17.2 | -10% |
| Customer Support | 4.5% | 15.9 | -28% |
| Delivery Time | 6.2% | 12.3 | -9% |
| Payment | 1.6% | 4.6 | +42% |
| Order Cancellation | 1.0% | 4.1 | -41% |
| Refund | 0.7% | 3.4 | -71% |
| Coupons & Offers | 1.9% | 2.5 | +70% |

## Improving Metrics
- Refund: -71% week-over-week
- Order Cancellation: -41% week-over-week
- Customer Support: -28% week-over-week
- Delivery Accuracy: -10% week-over-week
- Delivery Time: -9% week-over-week
- General Feedback: -0% week-over-week

## Declining Metrics
- Coupons & Offers: +70% week-over-week
- Payment: +42% week-over-week

## Alerts & Recommendations
### [WARNING] Confirm and communicate refund SLA; stop silent coupon substitution
Refund complaints (down 71% week-over-week) describe customer support verbally committing to a refund — for missing items, a cancelled order, or an undelivered order — that then doesn't materialize, or is silently substituted with a coupon/replacement product instead of cash. Several reviews use the word 'fraud' or 'scam', indicating this reads as a trust violation, not a service delay.

**Suggested fix:** Make refund method (cash/original payment method vs. coupon) an explicit customer choice at the point support agrees to refund, and add a visible refund-status tracker in-app so customers aren't relying on a verbal promise with no follow-up visibility.

**Investigate:** Confirm actual refund processing time distribution (median and p90) against what customer support tells customers verbally, and check what fraction of 'refunds' are currently auto-converted to coupon/credit rather than cash without explicit customer opt-in.

### [WARNING] Waive cancellation fees for platform-initiated cancellations
Order Cancellation complaints (down 41% week-over-week, but still a real cluster) center on customers being charged the FULL order amount as a cancellation fee even when the cancellation was not their fault — most commonly, no delivery partner was assigned within a reasonable window (a pattern reviewers associate with orders placed after 9pm), or the restaurant was delayed, and Zomato auto-cancels the order but still applies a fee as if the customer had cancelled voluntarily.

**Suggested fix:** Auto-waive the cancellation fee when the cancellation reason is system-initiated (no delivery partner assigned, restaurant-side delay past SLA); separately, send a proactive in-app notification when an order is at risk of auto-cancellation instead of letting it happen silently.

**Investigate:** Pull the cancellation reason code (already logged internally) split by customer-initiated vs. system-initiated, and check whether the fee-charging logic currently reads that field before applying a fee.

### [WARNING] Address perceived coupon deception from marked-up menu pricing
Coupon complaints center on a perceived 'fake discount': customers report that in-app menu prices are marked up above the restaurant's actual/dine-in prices, so applying a coupon still leaves the final total higher than ordering directly — making the discount feel illusory. A smaller cluster reports coupons/cashback simply failing to apply. Sentiment on this category is notably bifurcated (many reviews praise the offers), so the complaint is concentrated among price-comparison-aware customers, not universal.

**Suggested fix:** If markup is confirmed: pilot a 'verified price parity' badge on a subset of high-volume restaurants where in-app price is confirmed to match dine-in price, and measure whether coupon-related complaints differ for that subset vs. control. If the technical cashback failure is the bigger driver, prioritize the fix plus an explicit in-app error message when a coupon fails to apply.

**Investigate:** Sample 20-30 restaurants and compare in-app menu price for 3-5 common items against the restaurant's own dine-in price to quantify how widespread the markup actually is; separately, pull coupon-application failure rate from payment logs to size the technical-failure cluster.

### [WARNING] Surface total price and COD eligibility earlier in checkout
Payment complaints split into two distinct clusters: (1) fee-transparency complaints, where customers are frustrated that packaging, delivery, and platform fees stack on top of the listed item price only at final checkout, turning a ₹346 order into ₹475; and (2) COD availability/payment-failure complaints, where Cash on Delivery is inconsistently offered (available on a customer's first order, missing on their next), pushing users toward prepaid checkout that sometimes fails after the amount has already been deducted, leaving them with no food and no visible resolution path.

**Suggested fix:** Two-part, low-risk UI change (no fee restructuring, no COD policy change): (1) show a running 'estimated total incl. fees' line as soon as the first item is added to cart, not only at final checkout; (2) show a COD-availability badge on the restaurant page before item selection, so unavailability is known upfront rather than discovered at payment.

**Investigate:** Pull order-level data (outside review text) for the last 2 weeks: (1) % of orders where COD was available on a customer's prior order but not their next order from the same restaurant, (2) failed-payment-but-charged incident rate and average resolution time, (3) average total fee stack as a % of item subtotal, segmented by order value.

## Open Questions
- Set an LLM provider API key (`ANTHROPIC_API_KEY` or `GEMINI_API_KEY`) to generate a narrative summary.

## Next Actions
- Review the Biggest Issues and Alerts sections directly.
