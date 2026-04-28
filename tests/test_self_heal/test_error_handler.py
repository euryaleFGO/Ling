"""Tests for ErrorHandler and FixStrategy chain."""

import os
import sys
import pytest

# Ensure src is on the path so we can import the package under test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.backend.llm.self_heal.event_bus import Event, EventBus
from src.backend.llm.self_heal.emergency_stop import EmergencyStop, EmergencyStopError
from src.backend.llm.self_heal.rate_limiter import RateLimiter
from src.backend.llm.self_heal.error_handler import ErrorHandler
from src.backend.llm.self_heal.strategies.base_strategy import FixStrategy, FixResult


# ---------------------------------------------------------------------------
# Helper strategies for testing
# ---------------------------------------------------------------------------

class SuccessStrategy(FixStrategy):
    """A strategy that always succeeds."""

    def can_handle(self, event: Event) -> bool:
        return True

    def fix(self, event: Event) -> FixResult:
        return FixResult(success=True, message="fixed by SuccessStrategy")


class FailStrategy(FixStrategy):
    """A strategy that always fails."""

    def can_handle(self, event: Event) -> bool:
        return True

    def fix(self, event: Event) -> FixResult:
        return FixResult(success=False, message="FailStrategy could not fix")


class CanHandleStrategy(FixStrategy):
    """A strategy that only handles 'service_error' events."""

    def __init__(self, target_type: str = "service_error"):
        self._target_type = target_type

    def can_handle(self, event: Event) -> bool:
        return event.type == self._target_type

    def fix(self, event: Event) -> FixResult:
        return FixResult(success=True, message="handled")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStrategyChainFirstSuccess:
    """When the first strategy succeeds, subsequent strategies should not run."""

    def test_first_strategy_succeeds_no_fallback(self):
        bus = EventBus()
        handler = ErrorHandler(event_bus=bus)

        s1_called = []
        s2_called = []

        class S1(FixStrategy):
            def can_handle(self, ev):
                return True

            def fix(self, ev):
                s1_called.append(True)
                return FixResult(success=True, message="s1 ok")

        class S2(FixStrategy):
            def can_handle(self, ev):
                return True

            def fix(self, ev):
                s2_called.append(True)
                return FixResult(success=True, message="s2 ok")

        handler.add_strategy(S1())
        handler.add_strategy(S2())

        event = Event(type="test", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is True
        assert result.message == "s1 ok"
        assert len(s1_called) == 1
        assert len(s2_called) == 0  # s2 should NOT have run

    def test_fix_succeeds_emits_fix_applied(self):
        bus = EventBus()
        handler = ErrorHandler(event_bus=bus)
        handler.add_strategy(SuccessStrategy())

        events_received = []
        bus.on("fix_applied", lambda e: events_received.append(e))

        event = Event(type="test", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is True
        assert len(events_received) == 1
        assert events_received[0].data["strategy"] == "SuccessStrategy"


class TestStrategyChainFallback:
    """When the first strategy fails, the next one should be tried."""

    def test_first_fails_second_succeeds(self):
        bus = EventBus()
        handler = ErrorHandler(event_bus=bus)

        handler.add_strategy(FailStrategy())
        handler.add_strategy(SuccessStrategy())

        event = Event(type="test", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is True
        assert result.message == "fixed by SuccessStrategy"

    def test_chain_stops_at_first_success(self):
        bus = EventBus()
        handler = ErrorHandler(event_bus=bus)

        s3_called = []

        handler.add_strategy(FailStrategy())
        handler.add_strategy(SuccessStrategy())

        class S3(FixStrategy):
            def can_handle(self, ev):
                return True

            def fix(self, ev):
                s3_called.append(True)
                return FixResult(success=True, message="s3")

        handler.add_strategy(S3())

        event = Event(type="test", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is True
        assert result.message == "fixed by SuccessStrategy"
        assert len(s3_called) == 0

    def test_skips_cannot_handle(self):
        bus = EventBus()
        handler = ErrorHandler(event_bus=bus)

        # Only handles "other_type"
        handler.add_strategy(CanHandleStrategy(target_type="other_type"))
        # Handles everything
        handler.add_strategy(SuccessStrategy())

        event = Event(type="service_error", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is True
        assert result.message == "fixed by SuccessStrategy"


class TestEmergencyStopBlocks:
    """EmergencyStop should block all repair attempts."""

    def test_emergency_stop_returns_failure(self):
        bus = EventBus()
        es = EmergencyStop()
        es.stop()
        handler = ErrorHandler(event_bus=bus, emergency_stop=es)
        handler.add_strategy(SuccessStrategy())

        event = Event(type="test", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is False
        assert "emergency" in result.message.lower()

    def test_emergency_stop_not_active_allows_handle(self):
        bus = EventBus()
        es = EmergencyStop()  # Not stopped
        handler = ErrorHandler(event_bus=bus, emergency_stop=es)
        handler.add_strategy(SuccessStrategy())

        event = Event(type="test", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is True


class TestRateLimiterBlocks:
    """RateLimiter should block when limit is exceeded."""

    def test_rate_limit_blocks(self):
        bus = EventBus()
        rl = RateLimiter(max_per_window=1, window_seconds=300)
        handler = ErrorHandler(event_bus=bus, rate_limiter=rl)
        handler.add_strategy(SuccessStrategy())

        event = Event(type="test", severity="high", source="unit", data={})

        # First call should succeed
        r1 = handler.handle(event)
        assert r1.success is True

        # Second call should be rate-limited
        r2 = handler.handle(event)
        assert r2.success is False
        assert "rate" in r2.message.lower()


class TestAllStrategiesFail:
    """When all strategies fail, fix_failed should be emitted."""

    def test_all_fail_emits_fix_failed(self):
        bus = EventBus()
        handler = ErrorHandler(event_bus=bus)

        handler.add_strategy(FailStrategy())
        handler.add_strategy(FailStrategy())

        fix_failed_events = []
        bus.on("fix_failed", lambda e: fix_failed_events.append(e))

        event = Event(type="test", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is False
        assert len(fix_failed_events) == 1
        assert fix_failed_events[0].data["tried_strategies"] == 2


class TestNoStrategies:
    """With no strategies, handle should return failure."""

    def test_no_strategies_returns_failure(self):
        bus = EventBus()
        handler = ErrorHandler(event_bus=bus)

        event = Event(type="test", severity="high", source="unit", data={})
        result = handler.handle(event)

        assert result.success is False
        assert "all strategies failed" in result.message.lower()


class TestBackupBeforeFix:
    """ErrorHandler should create a backup snapshot before attempting a fix."""

    def test_backup_created_before_fix(self):
        bus = EventBus()
        backup_manager = None  # Will use a mock

        class MockBackupManager:
            def __init__(self):
                self.snapshots = []

            def create_snapshot(self, file_paths, reason=""):
                snap = {"file_paths": file_paths, "reason": reason}
                self.snapshots.append(snap)
                return snap

            def rollback(self, snapshot):
                self._rolled_back = snapshot
                return True

        mock_bm = MockBackupManager()
        handler = ErrorHandler(event_bus=bus, backup_manager=mock_bm)
        handler.add_strategy(SuccessStrategy())

        event = Event(type="test", severity="high", source="unit", data={
            "config_files": ["config.yaml"]
        })
        handler.handle(event)

        assert len(mock_bm.snapshots) == 1
        assert mock_bm.snapshots[0]["reason"] == "pre-fix backup"


class TestErrorHandlerRegistration:
    """ErrorHandler should register as wildcard handler on event_bus."""

    def test_registers_as_wildcard(self):
        bus = EventBus()
        handler = ErrorHandler(event_bus=bus)

        # The handler should have registered itself
        assert "*" in bus._handlers
        assert handler._handle_event in bus._handlers["*"]


class TestFixResult:
    """FixResult dataclass basics."""

    def test_default_values(self):
        fr = FixResult(success=True)
        assert fr.success is True
        assert fr.message == ""
        assert fr.data == {}

    def test_custom_values(self):
        fr = FixResult(success=False, message="oops", data={"k": "v"})
        assert fr.success is False
        assert fr.message == "oops"
        assert fr.data == {"k": "v"}
