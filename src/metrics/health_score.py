"""Product Health Score — a single weekly number a PM can watch on a dashboard.

Four weighted components, chosen to mirror how a PM actually triages a
week (in order of what they'd look at first):

  40% Ratings        — the number every stakeholder outside the team already
                        sees on the Play Store listing. Highest weight because
                        it is the metric leadership reacts to regardless of
                        what the internal data says.
  30% Critical Issues — % of classified reviews rated "critical" severity
                        (money lost, fraud, total app failure). Weighted
                        second-highest because these are the issues with
                        direct revenue/trust/legal exposure, even if they're
                        a small fraction of total volume.
  20% Trend           — is the negative-review ratio improving or worsening
                        week over week. Lower weight than the two above
                        because it's a second derivative (rate of change),
                        useful for direction but not a substitute for the
                        absolute level they already capture.
  10% Crash Reports   — % of classified reviews mentioning app crashes /
                        performance failures. Lowest weight only because it's
                        the narrowest single category; a crash spike still
                        shows up in Critical Issues too if severe.

These weights and thresholds are named constants below, not magic numbers
buried in formulas — change them here if the business wants to re-prioritize
(e.g. a fintech feature would probably weight Critical Issues higher than
Ratings).
"""

RATING_WEIGHT = 0.40
CRITICAL_WEIGHT = 0.30
TREND_WEIGHT = 0.20
CRASH_WEIGHT = 0.10

# "100% unhealthy" reference points for ratio-based components. These are
# judgment calls, documented rather than hidden: at 5% of a week's classified
# reviews being critical-severity, the critical-issue sub-score bottoms out
# at 0; anything at or above that ratio is treated as equally bad (there is
# no meaningful difference between "10% of reviews are critical" and "20%"
# from a health-scoring standpoint — both mean the score should already be at
# its floor).
CRITICAL_RATIO_FLOOR = 0.05
CRASH_RATIO_FLOOR = 0.03
# A negative-ratio regression of this size or more (in percentage points,
# e.g. 0.05 = 5pp worse than last week) sends the trend sub-score to 0.
TREND_REGRESSION_FLOOR_PP = 0.05


def _ratio_to_score(ratio: float, floor: float) -> float:
    """Linearly maps a bad-outcome ratio to a 0-100 health score (100=none, 0=at/above floor)."""
    if floor <= 0:
        return 100.0
    return max(0.0, 100.0 * (1 - min(ratio / floor, 1.0)))


def rating_subscore(avg_rating: float) -> float:
    """Maps the 1-5 star average onto 0-100."""
    return max(0.0, min(100.0, (avg_rating - 1.0) / 4.0 * 100.0))


def critical_subscore(critical_issue_count: int, total_classified: int) -> float:
    if total_classified == 0:
        return 100.0
    return _ratio_to_score(critical_issue_count / total_classified, CRITICAL_RATIO_FLOOR)


def crash_subscore(crash_mentions: int, total_classified: int) -> float:
    if total_classified == 0:
        return 100.0
    return _ratio_to_score(crash_mentions / total_classified, CRASH_RATIO_FLOOR)


def trend_subscore(negative_ratio_this_week: float, negative_ratio_last_week: float | None) -> float:
    """100 if flat or improved vs last week; decays to 0 as the regression approaches the floor.

    No prior week (first week of data) is treated as neutral (100) — there is
    nothing to regress against yet.
    """
    if negative_ratio_last_week is None:
        return 100.0
    regression_pp = negative_ratio_this_week - negative_ratio_last_week
    if regression_pp <= 0:
        return 100.0
    return max(0.0, 100.0 * (1 - min(regression_pp / TREND_REGRESSION_FLOOR_PP, 1.0)))


def compute_health_score(
    avg_rating: float,
    critical_issue_count: int,
    crash_mentions: int,
    total_classified: int,
    negative_ratio_this_week: float,
    negative_ratio_last_week: float | None,
) -> dict:
    r = rating_subscore(avg_rating)
    c = critical_subscore(critical_issue_count, total_classified)
    t = trend_subscore(negative_ratio_this_week, negative_ratio_last_week)
    x = crash_subscore(crash_mentions, total_classified)

    overall = RATING_WEIGHT * r + CRITICAL_WEIGHT * c + TREND_WEIGHT * t + CRASH_WEIGHT * x

    return {
        "overall": round(overall, 1),
        "rating_subscore": round(r, 1),
        "critical_subscore": round(c, 1),
        "trend_subscore": round(t, 1),
        "crash_subscore": round(x, 1),
    }
