# Weekly Product Report — Week of 2026-07-30
## Executive Summary
Health score dropped sharply to 73.3/100 this week (down from 78.0) across 550 reviews, with an average rating of 3.83. General Feedback dominates the issue categories at 67.1%, signaling widespread, non-specific user dissatisfaction or confusion. Customer Support and Delivery Time tied as the second-largest specific pain points at 8.5% each, accompanied by 10 active open alerts requiring immediate triage.
## Top Findings
- **550 reviews** this week, average rating **3.83/5**
- **Product Health Score: 73.3/100** (down from 78.0 last week)
- **10** critical-severity issues, **0** crash mentions
## Biggest Issues
| Category | Issue % | Severity Score | WoW Growth |
|---|---|---|---|
| General Feedback | 67.1% | 70.1 | +34% |
| Customer Support | 8.5% | 33.2 | +93% |
| Delivery Accuracy | 5.5% | 23.2 | -73% |
| Delivery Time | 8.5% | 20.2 | +39% |
| Refund | 0.8% | 5.0 | -92% |
| Discovery / Restaurant Search | 2.7% | 3.7 | +86% |
| Payment | 1.2% | 3.7 | -15% |
| Coupons & Offers | 2.2% | 3.2 | +11% |

## Improving Metrics
- Ordering: -94% week-over-week
- Refund: -92% week-over-week
- Delivery Accuracy: -73% week-over-week
- Payment: -15% week-over-week

## Declining Metrics
- Customer Support: +93% week-over-week
- Discovery / Restaurant Search: +86% week-over-week
- Delivery Time: +39% week-over-week
- General Feedback: +34% week-over-week
- Coupons & Offers: +11% week-over-week
- Checkout: +7% week-over-week

## Alerts & Recommendations
### [CRITICAL] Fix Critical Customer Support Breakdown Caused by Unresponsive AI Chatbot
The critical spike in negative reviews is overwhelmingly driven by a complete breakdown in customer support and complaint resolution. Customers across multiple languages and use cases report being trapped by unresponsive AI chatbots, unable to reach human agents, and left with zero recourse or refunds for damaged food, missing items, financial waste, or account issues.

**Suggested fix:** Implement a mandatory, frictionless one-tap 'Escalate to Human Agent' button within the chat interface for unresolved issue types (e.g., missing items, refund denials) and disable auto-closing scripts on active dispute tickets.

**Investigate:** Audit chatbot intent-failure logs to identify the exact conversation turns where users are trapped or chats are forcibly closed without resolution.

### [CRITICAL] Mitigate Delivery Partner Shortages, ETA Inaccuracies, and Extortion
The critical anomaly is driven by severe delivery delays, order cancellations, and unethical behavior by delivery partners (such as demanding extra charges). Customers report that delivery times are drastically underestimated at checkout and that a shortage of delivery partners causes long wait times and cold food.

**Suggested fix:** Implement strict hard caps on multi-order batching during peak hours, deploy an in-app reporting toggle to immediately flag and deactivate delivery partners demanding extra charges, and recalibrate checkout ETA algorithms to account for real-time rider supply constraints.

**Investigate:** Audit order dispatch logs to identify zones experiencing high rates of order bundling, extreme rider assignment delays, and repeat offender delivery partner IDs associated with extortion complaints.

### [WARNING] Address Online Pricing Discrepancies and High Item Costs in Restaurant Search
The reviews reveal a dominant customer concern regarding high pricing and expensive items, with multiple users explicitly complaining about inflated online rates compared to venue prices. Additionally, there are complaints about limited city availability and a lack of popular restaurants on the platform.

**Suggested fix:** Implement a mandatory venue-pricing verification SLA, display a clear 'venue-verified price' badge, and add a quick-report flag for pricing discrepancies on restaurant listing pages.

**Investigate:** Audit pricing synchronization pipelines between partner venues and the online database to identify where markup or stale data occurs.

### [WARNING] Inflated Menu Prices and Delivery Markups Causing Customer Churn
The dominant theme driving the anomaly is customer dissatisfaction regarding high menu prices on the platform compared to dine-in or real restaurant prices, exacerbated by additional delivery charges. Multiple users explicitly complained that items are overly expensive and marked up significantly on Zomato.

**Suggested fix:** Introduce a transparent price comparison UI tag (e.g. 'Dine-in price vs. Delivery price') and partner with top merchants to subsidize item markups or bundle delivery fees for orders above a specific threshold.

**Investigate:** Audit a random sample of top-performing restaurants in Discovery to quantify the exact markup delta between POS/dine-in menus and Zomato listings, segmented by cuisine and city.

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

## Open Questions
- What specific sub-topics are driving the 67.1% spike in General Feedback?
- Why did Customer Support (8.5%) and Delivery Time (8.5%) surge simultaneously this week?
- What specific incidents triggered the 10 open alerts and the 4.7-point drop in health score?

## Next Actions
- Triage and resolve the 10 open alerts within 24 hours to prevent further health score degradation.
- Perform a qualitative text analysis on the General Feedback category to isolate actionable product bugs or UX friction points.
- Review support ticket queues and delivery logistics logs to identify bottlenecks causing the concurrent spikes in support load and delivery delays.
