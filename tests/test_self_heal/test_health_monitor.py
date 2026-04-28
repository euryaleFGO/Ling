"""Tests for HealthMonitor and HealthCheck ABC."""

import os
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

# Ensure src is on the path so we can import the package under test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.backend.llm.self_heal.checks.base_check import CheckResult, HealthCheck
from src.backend.llm.self_heal.event_bus import EventBus
from src.backend.llm.self_heal.health_monitor import HealthMonitor


# ---------------------------------------------------------------------------
# FakeCheck — a concrete, controllable HealthCheck for testing
# ---------------------------------------------------------------------------

class FakeCheck(HealthCheck):
    """Deterministic health check used in tests."""

    def __init__(self, unhealthy: bool = False, name: str = "fake_check", interval: float = 0.1):
        self._unhealthy = unhealthy
        self._name = name
        self._interval = interval
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def interval(self) -> float:
        return self._interval

    def run(self) -> CheckResult:
        self.call_count += 1
        return CheckResult(
            is_unhealthy=self._unhealthy,
            event_type="tool_error",
            severity="low",
            data={"test": True},
        )


# ---------------------------------------------------------------------------
# CheckResult dataclass
# ---------------------------------------------------------------------------

class TestCheckResult:
    def test_creation(self):
        r = CheckResult(is_unhealthy=True, event_type="err", severity="high", data={"k": 1})
        assert r.is_unhealthy is True
        assert r.event_type == "err"
        assert r.severity == "high"
        assert r.data == {"k": 1}

    def test_healthy_result(self):
        r = CheckResult(is_unhealthy=False, event_type="", severity="", data={})
        assert r.is_unhealthy is False


# ---------------------------------------------------------------------------
# HealthCheck ABC enforcement
# ---------------------------------------------------------------------------

class TestHealthCheckABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            HealthCheck()  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        check = FakeCheck(unhealthy=False)
        result = check.run()
        assert isinstance(result, CheckResult)


# ---------------------------------------------------------------------------
# HealthMonitor
# ---------------------------------------------------------------------------

class TestHealthMonitor:
    def test_register_check(self):
        bus = EventBus()
        monitor = HealthMonitor(bus)
        check = FakeCheck()
        monitor.register_check(check)
        assert len(monitor._checks) == 1
        assert monitor._checks[0] is check

    def test_register_multiple_checks(self):
        bus = EventBus()
        monitor = HealthMonitor(bus)
        c1 = FakeCheck(name="a")
        c2 = FakeCheck(name="b")
        monitor.register_check(c1)
        monitor.register_check(c2)
        assert len(monitor._checks) == 2

    def test_healthy_check_no_event(self):
        """A healthy check should not emit any events."""
        bus = EventBus()
        monitor = HealthMonitor(bus)
        events = []
        bus.on("*", lambda e: events.append(e))

        monitor.register_check(FakeCheck(unhealthy=False))
        monitor.start()
        time.sleep(0.5)
        monitor.stop()

        assert events == [], "Healthy check should not emit events"

    def test_detects_unhealthy(self):
        """An unhealthy check should trigger an event on the bus."""
        bus = EventBus()
        monitor = HealthMonitor(bus)
        events = []
        bus.on("tool_error", lambda e: events.append(e))

        monitor.register_check(FakeCheck(unhealthy=True, interval=0.05))
        monitor.start()
        time.sleep(0.5)
        monitor.stop()

        assert len(events) >= 1, "Unhealthy check should emit at least one event"
        first = events[0]
        assert first.type == "tool_error"
        assert first.severity == "low"
        assert first.source == "fake_check"
        assert first.data["test"] is True
        assert first.data["error_count"] >= 1

    def test_severity_escalation(self):
        """Consecutive failures should escalate severity."""
        bus = EventBus()
        monitor = HealthMonitor(bus)
        events = []
        bus.on("tool_error", lambda e: events.append(e))

        monitor.register_check(FakeCheck(unhealthy=True, interval=0.01))
        monitor.start()
        # Wait long enough for >= 5 consecutive errors
        time.sleep(1.0)
        monitor.stop()

        severities = [e.severity for e in events]
        # After 5+ failures severity should be at least "medium"
        assert "medium" in severities or "high" in severities, (
            f"Expected severity escalation, got {severities}"
        )

    def test_stop_halts_monitoring(self):
        """After stop(), no more events should be emitted."""
        bus = EventBus()
        monitor = HealthMonitor(bus)
        events = []
        bus.on("tool_error", lambda e: events.append(e))

        monitor.register_check(FakeCheck(unhealthy=True, interval=0.02))
        monitor.start()
        time.sleep(0.3)
        count_before_stop = len(events)
        monitor.stop()
        time.sleep(0.3)
        count_after_stop = len(events)

        assert count_before_stop >= 1, "Should have emitted events before stop"
        assert count_after_stop == count_before_stop, (
            f"No new events after stop: before={count_before_stop}, after={count_after_stop}"
        )

    def test_start_is_idempotent(self):
        """Calling start() twice should not create a second thread."""
        bus = EventBus()
        monitor = HealthMonitor(bus)
        monitor.start()
        first_thread = monitor._thread
        monitor.start()
        assert monitor._thread is first_thread
        monitor.stop()

    def test_check_exception_is_handled(self):
        """A check that raises should not crash the monitor."""
        class BrokenCheck(HealthCheck):
            @property
            def name(self):
                return "broken"

            @property
            def interval(self):
                return 0.05

            def run(self):
                raise RuntimeError("boom")

        bus = EventBus()
        monitor = HealthMonitor(bus)
        monitor.register_check(BrokenCheck())
        monitor.start()
        time.sleep(0.3)
        # Should not have crashed — monitor is still running
        assert monitor._running is True
        monitor.stop()

    def test_error_count_reset_on_recovery(self):
        """After a healthy result the error count should reset."""
        class FlappingCheck(HealthCheck):
            def __init__(self):
                self.call_count = 0

            @property
            def name(self):
                return "flap"

            @property
            def interval(self):
                return 0.02

            def run(self):
                self.call_count += 1
                # Unhealthy for first 3 calls, then healthy
                return CheckResult(
                    is_unhealthy=self.call_count <= 3,
                    event_type="tool_error",
                    severity="low",
                    data={},
                )

        bus = EventBus()
        monitor = HealthMonitor(bus)
        events = []
        bus.on("tool_error", lambda e: events.append(e))

        check = FlappingCheck()
        monitor.register_check(check)
        monitor.start()
        time.sleep(0.5)
        monitor.stop()

        # Should have emitted events (first 3 calls unhealthy)
        assert len(events) >= 3
        # Error count should have been reset — no escalation to "high"
        severities = [e.severity for e in events]
        assert "high" not in severities, (
            f"Error count should reset after recovery, got {severities}"
        )
