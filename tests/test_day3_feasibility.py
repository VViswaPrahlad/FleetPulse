import numpy as np
import pytest
from src.quality.fuel_feasibility import window_support


def test_constant_fuel_integrates_observed_endpoints():
    times = np.arange(181) * 1000
    result = window_support(times, np.full(181, 6.0), input_valid=np.ones(181, bool))
    assert result["target_windows"] == 121
    assert result["paired_windows"] == 61
    assert result["nonoverlap_pairs"] == 1
    assert result["labels"] == pytest.approx(np.full(61, 0.1))


def test_missing_fuel_row_breaks_every_crossing_pair():
    values = np.ones(181)
    values[90] = np.nan
    result = window_support(np.arange(181)*1000, values)
    assert result["paired_windows"] == 0
    assert result["target_windows"] == 60
    assert result["segments"] == 2


def test_gap_threshold_and_exact_boundaries():
    times = np.delete(np.arange(181)*1000, 90)
    assert window_support(times, np.ones(180), 1000)["paired_windows"] == 0
    assert window_support(times, np.ones(180), 2000)["paired_windows"] == 60
    assert window_support(np.arange(181)*1000+500, np.ones(181))["paired_windows"] == 0


def test_future_speed_is_not_used_to_filter_past_input():
    valid = np.ones(181, bool)
    valid[90] = False
    assert window_support(np.arange(181)*1000, np.ones(181), input_valid=valid)["paired_windows"] == 30


def test_zero_is_valid_and_negative_fuel_is_not():
    times = np.arange(181)*1000
    result = window_support(times, np.zeros(181))
    assert result["paired_windows"] == 61
    assert np.all(result["labels"] == 0)
    values = np.ones(181)
    values[90] = -1
    assert window_support(times, values)["paired_windows"] == 0


def test_signed_battery_current_remains_observed():
    result = window_support(np.arange(181)*1000, np.full(181,-6.0), nonnegative=False)
    assert result["paired_windows"] == 61
    assert result["labels"] == pytest.approx(np.full(61,-0.1))


def test_duplicate_timestamps_break_continuity():
    times = np.insert(np.arange(181)*1000,90,90000)
    assert window_support(times,np.ones(182))["paired_windows"] == 0


def test_short_or_empty_trip_has_no_training_windows():
    assert window_support([],[])["paired_windows"] == 0
    assert window_support(np.arange(60)*1000,np.ones(60))["target_windows"] == 0
