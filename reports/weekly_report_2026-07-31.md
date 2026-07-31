# Weekly Product Report — Week of 2026-07-17
_Note: 2 more recent week(s) starting 2026-07-23, 2026-07-24 are excluded from this report's headline — Google Play's review-indexing lag means the most recent few days always look artificially sparse at scrape time. They'll be included once review volume for those weeks catches up in a later run._
## Executive Summary
For the week of July 17, 2026, performance remained largely flat with a slight health score regression from 78.2 to 78.0 across 4,276 reviews and a stable 4.00 average rating. General Feedback overwhelmingly dominates the issue volume at 75.7%, signaling potential vagueness in our categorization or a pervasive, non-specific user dissatisfaction trend. Operational friction points like Delivery Time (6.1%), Delivery Accuracy (4.5%), and Customer Support (4.4%) continue to create drag, while 10 open alerts require immediate triage to prevent further health score erosion.
## Top Findings
- **4276 reviews** this week, average rating **4.00/5**
- **Product Health Score: 78.0/100** (down from 78.2 last week)
- **80** critical-severity issues, **10** crash mentions
## Biggest Issues
| Category | Issue % | Severity Score | WoW Growth |
|---|---|---|---|
| General Feedback | 75.7% | 80.0 | +0% |
| Delivery Accuracy | 4.5% | 17.3 | -1% |
| Customer Support | 4.4% | 15.8 | -2% |
| Delivery Time | 6.1% | 12.3 | -1% |
| Order Cancellation | 1.0% | 4.3 | +4% |
| Payment | 1.5% | 3.9 | -8% |
| Refund | 0.7% | 3.7 | +5% |
| Coupons & Offers | 2.0% | 2.6 | +5% |

## Improving Metrics
- Login / Signup: -10% week-over-week
- Payment: -8% week-over-week
- Customer Support: -2% week-over-week
- Discovery / Restaurant Search: -1% week-over-week
- Delivery Time: -1% week-over-week
- Delivery Accuracy: -1% week-over-week

## Declining Metrics
- Subscription (Zomato Gold/Pro): +19% week-over-week
- Notifications: +17% week-over-week
- Coupons & Offers: +5% week-over-week
- Refund: +5% week-over-week
- App Crash: +5% week-over-week
- Checkout: +4% week-over-week
- Order Cancellation: +4% week-over-week
- Performance / Slowness: +3% week-over-week
- Ordering: +2% week-over-week
- General Feedback: +0% week-over-week

## Alerts & Recommendations
### [WARNING] Fix Zomato Gold Delivery Fee Discrepancies and Distance Radius Calculation
Customers are expressing widespread frustration regarding the Zomato Gold membership program, specifically citing unexpected delivery charges, inflated distances to disqualify free delivery perks, and hidden fees. Many users feel misled, alleging that the membership offers little to no actual savings compared to non-member accounts.

**Suggested fix:** Recalibrate the map distance algorithm to use straight-line or verified road-network paths for Gold benefit eligibility, and implement a transparent UI breakdown at checkout showing why a delivery fee was applied.

**Investigate:** Audit recent commits to the map routing/distance calculation service and review checkout transaction logs to identify orders where Gold members were incorrectly billed delivery fees within the standard free radius.

### [WARNING] Performance Degradation, Tracking Failures, and Gboard Input Bugs
Customers are experiencing severe performance degradation, slow app speeds, and UI/usability issues. Multiple users specifically complain about order tracking failures, app lag, and text input bugs when trying to write feedback.

**Suggested fix:** Roll back or patch the latest release to fix UI rendering bottlenecks, optimize order tracking websocket/polling synchronization, and resolve the third-party keyboard focus bug.

**Investigate:** Inspect recent frontend rendering code for memory leaks, review order status API polling intervals, and test Gboard compatibility inside text-area components.

### [WARNING] Investigate Critical App Crashes, Login Failures, and Payment Glitches
Customers are experiencing widespread app failure, including complete inability to log in, installation and download blocks, and general freezing or crashing. Additionally, specific functional glitches such as missing UPI payment options, group ordering redirect loops to the Play Store, and financial loss without refunds are driving severe user frustration.

**Suggested fix:** Roll back the unstable build immediately if stability cannot be hotfixed, deploy a patch fixing the deep link intent handling for group ordering, restore missing UPI payment gateway integrations in the checkout UI, and establish an expedited refund queue for affected transactions.

**Investigate:** Inspect crashlytics and error logs for the latest build deployment to identify the root cause of startup crashes, review recent changes to deep linking and intent configurations, and audit the checkout frontend for missing UPI UI components.

### [WARNING] Refund Failures and Disabled Support Channels Driving Churn
Customers are experiencing extreme frustration over denied refunds, delayed orders, and missing food items, compounded by poor support channels. Multiple users explicitly state they are deleting the app and switching to competitors like Swiggy due to perceived unfairness and scams regarding cancellations.

**Suggested fix:** Re-enable inbound customer support calling for cancellation/refund disputes, and implement a grace period for auto-refunds on pre-fulfillment cancellations.

**Investigate:** Audit recent automated cancellation and refund rules in the payment gateway integration, and check support telephony logs for disabled call routing paths.

### [WARNING] Prevent Unauthorized Delivery Partner Order Cancellations and False Excuse Claims
Customers are experiencing widespread frustration regarding sudden, unauthorized order cancellations by delivery partners and support staff. Key issues include late-night order failures, dishonest cancellation excuses (such as fake accident claims), and problematic cancellation fees and refund processes.

**Suggested fix:** Implement strict geofencing and app-based validation requiring delivery agents to submit photographic proof or GPS validation before a cancellation reason can be logged, and automate full refunds plus compensation waivers for orders cancelled by agents without customer consent.

**Investigate:** Audit delivery partner cancellation logs for the 00:00 to 05:00 time window to identify specific driver IDs, zones, and frequency of 'vehicle accident' or 'road blocked' excuse usage.

### [CRITICAL] Fix Prepaid Delivery Fraud and Implement OTP Verification
Customers are experiencing severe issues with order fulfillment, specifically involving delivery partners marking prepaid orders as 'delivered' without actually delivering them or stealing the food. Additionally, users report receiving completely wrong items, missing food, and encountering unhelpful customer support chatbots that fail to resolve grievances or issue appropriate refunds.

**Suggested fix:** Implement a mandatory 4-digit OTP generated on the user's app that must be entered by the delivery partner to close prepaid orders, combined with an immediate bot-bypass routing rule to human agents for missing delivery claims.

**Investigate:** Analyze delivery partner telemetry (GPS timestamps vs. marked delivery locations) and isolate specific hub IDs or courier cohorts with high rates of 'delivered early' anomalies on prepaid orders.

### [CRITICAL] Fix Deceptive ETAs and Two-Hour Delivery Delays During Peak Hours
The critical anomaly is driven by severe delivery delays, inaccurate estimated time of arrivals (ETAs), and unhelpful customer support. Multiple customers report waiting over two hours for food that often arrives cold or is never delivered at all, leading to high frustration and churn towards competitors like Swiggy.

**Suggested fix:** Implement a dynamic post-payment ETA buffer algorithm that accurately reflects restaurant kitchen queues and courier shortages, and allow free customer cancellations without penalty if the actual delivery time exceeds the initial pre-checkout ETA by more than 15 minutes.

**Investigate:** Audit the pre-checkout ETA machine learning model to compare predicted preparation and transit times against actual historical peak-hour delivery times.

### [WARNING] Resolve COD Blocking, Unexpected Fees, and Wallet Debit Failures
Customers are experiencing widespread frustration regarding sudden unavailability of Cash on Delivery (COD), unexpected or excessive fees, and critical payment failures including deducted money for failed wallet top-ups or unfulfilled orders. Additionally, users report poor or unresponsive customer service when trying to resolve these financial grievances.

**Suggested fix:** Roll back erroneous risk-scoring flags to restore COD for eligible users, implement an automated reconciliation script to instantly refund or credit failed wallet top-ups and unfulfilled orders, and deploy a transparent fee breakdown tooltip at checkout.

**Investigate:** Audit the automated risk-scoring algorithm for false-positive COD blocks, review recent payment gateway webhook logs for timeout errors during wallet top-ups, and verify recent updates to the fee calculation service.

### [WARNING] Introduce upfront fee transparency and breakdown on the menu page
Customers are expressing extreme frustration over unexpectedly high additional costs, including taxes, delivery fees, platform fees, and surge charges that significantly inflate the final bill compared to base item prices. Furthermore, several reviews highlight a lack of transparency regarding fee breakdowns before reaching the final checkout stage, with some users even experiencing sudden price increases right at the payment step.

**Suggested fix:** Redesign the cart and menu pages to include an interactive 'Estimated Total' accordion that displays taxes, delivery, and platform fees upfront before the user reaches the payment step.

**Investigate:** Audit the checkout funnel analytics to pinpoint the exact drop-off rate between the cart view and the final payment confirmation screen, and review latency issues in fee calculation APIs.

### [WARNING] Fix Menu Price Discrepancies and Address-Routing Bugs in Ordering
The customer reviews highlight two major issues driving the anomaly: significant discrepancies between menu prices displayed on the app versus actual restaurant prices or final billing, and location-routing errors where the app incorrectly selects saved office addresses instead of home addresses. Additionally, a few users noted friction with app navigation and customer support.

**Suggested fix:** Implement a real-time price validation check against restaurant-side catalog updates prior to cart locking, and add a mandatory pre-checkout confirmation modal displaying the explicit delivery address with a visual map pin when multiple addresses are saved.

**Investigate:** Audit the restaurant catalog synchronization pipeline for price mismatches and analyze the address-selection state machine on the checkout screen to see when and why the default overrides the user's manual selection.

## Open Questions
- Why is 'General Feedback' accounting for over 75% of issue categories, and are we failing to properly tag specific user pain points?
- What specific delivery logistics bottlenecks are driving the 6.1% Delivery Time and 4.5% Delivery Accuracy complaints this week?
- Which specific subsystems or regions are triggering the 10 currently open alerts?

## Next Actions
- Audit a randomized sample of 'General Feedback' reviews to reclassify ambiguous entries into actionable product or operational categories.
- Investigate and resolve the 10 open alerts prioritized by potential impact on customer churn and health score.
- Collaborate with the logistics and customer support leads to address root causes behind the Delivery Time (6.1%) and Support (4.4%) spikes.
