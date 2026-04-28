"""Tests for EmergencyStop."""

import pytest

from src.backend.llm.self_heal.emergency_stop import EmergencyStop, EmergencyStopError


def test_not_stopped_by_default():
    """EmergencyStop should not be active when first created."""
    es = EmergencyStop()
    assert es.is_stopped is False


def test_stop_raises_error():
    """After stop(), check() should raise EmergencyStopError."""
    es = EmergencyStop()
    es.stop()
    with pytest.raises(EmergencyStopError, match="Emergency stop active"):
        es.check()


def test_reset_allows_check():
    """After reset(), check() should not raise."""
    es = EmergencyStop()
    es.stop()
    es.reset()
    assert es.is_stopped is False
    es.check()  # Should not raise


def test_is_stopped_property():
    """is_stopped should reflect the current state accurately."""
    es = EmergencyStop()
    assert es.is_stopped is False
    es.stop()
    assert es.is_stopped is True
    es.reset()
    assert es.is_stopped is False
