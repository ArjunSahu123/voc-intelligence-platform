import pytest

from src.metrics.health_score import (
    compute_health_score,
    crash_subscore,
    critical_subscore,
    rating_subscore,
    trend_subscore,
)


def test_rating_subscore_boundaries():
    assert rating_subscore(1.0) == 0.0
    assert rating_subscore(5.0) == 100.0
    assert rating_subscore(3.0) == 50.0


def test_rating_subscore_clamps_out_of_range():
    assert rating_subscore(0.0) == 0.0
    assert rating_subscore(6.0) == 100.0


def test_critical_subscore_no_classified_reviews_is_neutral():
    assert critical_subscore(0, 0) == 100.0


def test_critical_subscore_at_floor_is_zero():
    # 5% critical ratio is the documented floor -> score bottoms out at 0
    assert critical_subscore(critical_issue_count=5, total_classified=100) == 0.0


def test_critical_subscore_above_floor_stays_at_zero():
    assert critical_subscore(critical_issue_count=50, total_classified=100) == 0.0


def test_crash_subscore_below_floor_is_partial():
    score = crash_subscore(crash_mentions=1, total_classified=100)  # 1% vs 3% floor
    assert 0 < score < 100


def test_trend_subscore_no_prior_week_is_neutral():
    assert trend_subscore(0.30, None) == 100.0


def test_trend_subscore_improvement_is_full_score():
    assert trend_subscore(0.10, 0.20) == 100.0


def test_trend_subscore_regression_at_floor_is_zero():
    assert trend_subscore(0.25, 0.20) == pytest.approx(0.0, abs=1e-9)  # 5pp regression == documented floor


def test_trend_subscore_partial_regression():
    score = trend_subscore(0.225, 0.20)  # 2.5pp regression, half of the 5pp floor
    assert 40 < score < 60


def test_compute_health_score_weights_sum_to_full_scale():
    healthy = compute_health_score(
        avg_rating=5.0,
        critical_issue_count=0,
        crash_mentions=0,
        total_classified=100,
        negative_ratio_this_week=0.0,
        negative_ratio_last_week=0.0,
    )
    assert healthy["overall"] == 100.0


def test_compute_health_score_worst_case_is_zero():
    unhealthy = compute_health_score(
        avg_rating=1.0,
        critical_issue_count=50,
        crash_mentions=50,
        total_classified=100,
        negative_ratio_this_week=0.5,
        negative_ratio_last_week=0.1,
    )
    assert unhealthy["overall"] == 0.0
