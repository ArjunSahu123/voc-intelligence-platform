"""Sample size calculation for a two-proportion A/B test — real statistics,
not an LLM guess.

Standard two-sample z-test for proportions power analysis:

    n = (z_(alpha/2) + z_beta)^2 * (p1(1-p1) + p2(1-p2)) / (p2 - p1)^2

where p1 is the baseline rate and p2 is the target rate after applying the
minimum detectable effect (MDE), expressed as a RELATIVE reduction (e.g.
mde_pct=20 on a 10% negative-review baseline targets 8%). Relative framing
is used because "the issue rate should drop by X%" is how a PM naturally
states a goal, versus an absolute percentage-point target that doesn't
scale with the baseline.

alpha=0.05 (95% significance) and power=0.80 (80% power, beta=0.20) are the
conventional industry defaults for a standard product experiment; both are
named constants below and overridable by the caller for larger/riskier
experiments that warrant tighter bounds.
"""
from scipy.stats import norm

DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.80


def sample_size_two_proportions(
    baseline_rate: float,
    mde_pct_relative: float,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> dict:
    if not (0 < baseline_rate < 1):
        raise ValueError("baseline_rate must be strictly between 0 and 1.")

    target_rate = baseline_rate * (1 - mde_pct_relative / 100.0)
    target_rate = max(target_rate, 1e-6)

    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)

    p1, p2 = baseline_rate, target_rate
    numerator = (z_alpha + z_beta) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2))
    denominator = (p2 - p1) ** 2
    n_per_variant = numerator / denominator

    return {
        "baseline_rate": round(p1, 4),
        "target_rate": round(p2, 4),
        "mde_pct_relative": mde_pct_relative,
        "alpha": alpha,
        "power": power,
        "sample_size_per_variant": int(round(n_per_variant)) + 1,
    }
