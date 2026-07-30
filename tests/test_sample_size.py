import pytest

from src.experiments.sample_size import sample_size_two_proportions


def test_sample_size_matches_known_reference_value():
    # Standard two-proportion power calc, alpha=0.05, power=0.8:
    # baseline 20% -> target 16% (20% relative reduction) needs ~1443-1450/arm
    # (cross-checked against Evan Miller's / statsmodels-equivalent calculators).
    result = sample_size_two_proportions(0.20, 20.0)
    assert 1400 <= result["sample_size_per_variant"] <= 1500


def test_larger_effect_needs_fewer_samples():
    small_effect = sample_size_two_proportions(0.20, 10.0)
    large_effect = sample_size_two_proportions(0.20, 40.0)
    assert large_effect["sample_size_per_variant"] < small_effect["sample_size_per_variant"]


def test_lower_baseline_rate_needs_more_samples_for_same_relative_effect():
    common = sample_size_two_proportions(0.20, 20.0)
    rare = sample_size_two_proportions(0.02, 20.0)
    assert rare["sample_size_per_variant"] > common["sample_size_per_variant"]


def test_invalid_baseline_rate_raises():
    with pytest.raises(ValueError):
        sample_size_two_proportions(0.0, 20.0)
    with pytest.raises(ValueError):
        sample_size_two_proportions(1.0, 20.0)


def test_higher_power_needs_more_samples():
    low_power = sample_size_two_proportions(0.20, 20.0, power=0.7)
    high_power = sample_size_two_proportions(0.20, 20.0, power=0.95)
    assert high_power["sample_size_per_variant"] > low_power["sample_size_per_variant"]
