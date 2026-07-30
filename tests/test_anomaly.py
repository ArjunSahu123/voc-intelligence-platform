import pandas as pd

from src.anomaly.detect_anomalies import _expanding_z_scores


def test_z_score_none_for_first_two_weeks():
    series = pd.Series([0.10, 0.11, 0.30])
    z = _expanding_z_scores(series)
    assert pd.isna(z.iloc[0])  # no prior weeks at all
    assert pd.isna(z.iloc[1])  # only 1 prior week, std undefined


def test_z_score_flags_a_real_spike():
    # Stable ~0.10 for 4 weeks, then a jump to 0.40
    series = pd.Series([0.10, 0.11, 0.09, 0.10, 0.40])
    z = _expanding_z_scores(series)
    assert z.iloc[-1] > 2.0


def test_z_score_zero_variance_is_nan_not_inf():
    series = pd.Series([0.10, 0.10, 0.10, 0.10])
    z = _expanding_z_scores(series)
    assert pd.isna(z.iloc[-1])  # zero prior std must not divide-by-zero into inf


def test_z_score_flat_series_after_variance_is_near_zero():
    series = pd.Series([0.10, 0.12, 0.08, 0.10])
    z = _expanding_z_scores(series)
    assert abs(z.iloc[-1]) < 1.0
