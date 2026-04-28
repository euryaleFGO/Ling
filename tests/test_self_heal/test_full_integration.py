"""Integration tests for the self-healing system."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from backend.llm.self_heal import (
    EventBus,
    Event,
    HealthMonitor,
    ErrorHandler,
    BackupManager,
    RateLimiter,
    EmergencyStop,
    LogWatchCheck,
    PerformanceCheck,
    RetryStrategy,
    NotifyUserStrategy,
)


class TestFullIntegration:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.bus = EventBus()
        self.backup = BackupManager(backup_dir=self.tmpdir)
        self.rate_limiter = RateLimiter(max_per_window=10, window_seconds=60)
        self.emergency_stop = EmergencyStop()
        self.handler = ErrorHandler(
            self.bus, self.backup, self.rate_limiter, self.emergency_stop
        )
        self.handler.add_strategy(NotifyUserStrategy())

    def test_event_bus_to_error_handler_flow(self):
        """Event emitted -> ErrorHandler processes it."""
        events_received = []
        self.bus.on("fix_failed", lambda e: events_received.append(e))

        event = Event(
            type="tool_error",
            severity="low",
            source="test",
            data={"error": "test error"},
        )
        result = self.handler.handle(event)

        assert result.success is False
        assert len(events_received) == 1

    def test_emergency_stop_blocks_all_fixes(self):
        """Emergency stop prevents any fix attempts."""
        self.emergency_stop.stop()
        event = Event(type="tool_error", severity="low", source="test", data={})
        result = self.handler.handle(event)
        assert result.success is False

    def test_rate_limiter_prevents_flood(self):
        """Rate limiter blocks excessive fix attempts."""
        for _ in range(10):
            self.handler.handle(
                Event(type="tool_error", severity="low", source="flood_test", data={})
            )
        result = self.handler.handle(
            Event(type="tool_error", severity="low", source="flood_test", data={})
        )
        assert result.success is False
        assert "Rate limit" in result.message

    def test_performance_check_detects_degradation(self):
        """PerformanceCheck detects high error rate."""
        pc = PerformanceCheck(error_rate_threshold=0.3)
        for _ in range(7):
            pc.record(False)
        for _ in range(3):
            pc.record(True)

        result = pc.run()
        assert result.is_unhealthy is True
        assert result.event_type == "high_error_rate"

    def test_backup_and_rollback_cycle(self):
        """Full backup -> modify -> rollback cycle."""
        test_file = Path(self.tmpdir) / "test.txt"
        test_file.write_text("original")

        snapshot = self.backup.create_snapshot(
            file_paths=[str(test_file)], reason="test"
        )
        test_file.write_text("modified")
        assert test_file.read_text() == "modified"

        self.backup.rollback(snapshot)
        assert test_file.read_text() == "original"

    def test_event_bus_wildcard_dispatch(self):
        """Wildcard listeners receive all events."""
        # Use a fresh EventBus to avoid interference from the ErrorHandler
        # wildcard listener set up in setup_method.
        bus = EventBus()
        all_events = []
        bus.on("*", lambda e: all_events.append(e.type))

        bus.emit(Event(type="alpha", severity="low", source="test", data={}))
        bus.emit(Event(type="beta", severity="high", source="test", data={}))

        assert all_events == ["alpha", "beta"]

    def test_handler_wildcard_processes_emitted_events(self):
        """Events emitted on the bus are auto-processed by ErrorHandler."""
        fix_failed_events = []
        self.bus.on("fix_failed", lambda e: fix_failed_events.append(e))

        # Emit a tool_error event directly on the bus.
        # The ErrorHandler is registered as a wildcard listener, so it
        # should pick it up and run through the strategy chain.
        self.bus.emit(
            Event(type="tool_error", severity="low", source="bus_test", data={})
        )

        # NotifyUserStrategy always fails -> fix_failed emitted
        assert len(fix_failed_events) == 1
        assert fix_failed_events[0].data["original_event"] == "tool_error"

    def test_emergency_stop_reset_allows_fixes(self):
        """After resetting emergency stop, fixes are allowed again."""
        self.emergency_stop.stop()
        event = Event(type="tool_error", severity="low", source="test", data={})
        result = self.handler.handle(event)
        assert result.success is False

        self.emergency_stop.reset()
        events_received = []
        self.bus.on("fix_failed", lambda e: events_received.append(e))

        result = self.handler.handle(event)
        assert result.success is False  # NotifyUserStrategy always fails
        assert len(events_received) == 1  # But it went through the strategy chain

    def test_rate_limiter_separate_buckets(self):
        """Different event types have independent rate limits."""
        for _ in range(10):
            self.handler.handle(
                Event(type="type_a", severity="low", source="test", data={})
            )
        # type_a is now rate-limited, but type_b should be fine
        result = self.handler.handle(
            Event(type="type_b", severity="low", source="test", data={})
        )
        # NotifyUserStrategy always fails, but it's not a rate limit error
        assert "Rate limit" not in result.message

    def test_multiple_strategies_chain(self):
        """Multiple strategies are tried in order until one succeeds."""
        bus = EventBus()
        backup = BackupManager(backup_dir=tempfile.mkdtemp())
        handler = ErrorHandler(bus, backup)

        call_order = []

        class StrategyA(NotifyUserStrategy):
            def fix(self, event):
                call_order.append("A")
                return super().fix(event)

        class StrategyB(NotifyUserStrategy):
            def fix(self, event):
                call_order.append("B")
                return super().fix(event)

        handler.add_strategy(StrategyA())
        handler.add_strategy(StrategyB())

        event = Event(type="test", severity="low", source="test", data={})
        handler.handle(event)

        # Both should be tried since NotifyUserStrategy always returns False
        assert call_order == ["A", "B"]

    def test_fix_applied_event_emitted(self):
        """When a strategy succeeds, fix_applied is emitted on the bus."""
        from backend.llm.self_heal.strategies import FixStrategy, FixResult

        bus = EventBus()
        handler = ErrorHandler(bus)

        class AlwaysSucceed(FixStrategy):
            def can_handle(self, event):
                return True

            def fix(self, event):
                return FixResult(success=True, message="fixed!")

        handler.add_strategy(AlwaysSucceed())

        fix_applied = []
        bus.on("fix_applied", lambda e: fix_applied.append(e))

        event = Event(type="test", severity="low", source="test", data={})
        result = handler.handle(event)

        assert result.success is True
        assert len(fix_applied) == 1
        assert fix_applied[0].data["strategy"] == "AlwaysSucceed"

    def test_health_monitor_emits_events_on_failure(self):
        """HealthMonitor emits events when checks detect problems."""
        from backend.llm.self_heal.checks import CheckResult, HealthCheck

        class FailingCheck(HealthCheck):
            @property
            def name(self):
                return "failing_check"

            @property
            def interval(self):
                return 0.01

            def run(self):
                return CheckResult(
                    is_unhealthy=True,
                    event_type="test_failure",
                    severity="low",
                    data={"detail": "something broke"},
                )

        bus = EventBus()
        monitor = HealthMonitor(bus)
        monitor.register_check(FailingCheck())

        events = []
        bus.on("test_failure", lambda e: events.append(e))

        monitor.start()
        import time
        time.sleep(0.1)
        monitor.stop()

        assert len(events) >= 1
        assert events[0].type == "test_failure"

    def test_retry_strategy_success(self):
        """RetryStrategy succeeds when retry_fn eventually works."""
        bus = EventBus()
        handler = ErrorHandler(bus)

        attempts = []

        def flaky_fn():
            attempts.append(True)
            return len(attempts) >= 2  # Succeeds on 2nd attempt

        retry = RetryStrategy(max_retries=3, base_delay=0.01)
        retry.set_retry_fn(flaky_fn)
        handler.add_strategy(retry)

        event = Event(type="test", severity="low", source="test", data={})
        result = handler.handle(event)

        assert result.success is True
        assert len(attempts) == 2

    def test_log_watch_check_initial_healthy(self):
        """LogWatchCheck starts healthy when no log files exist."""
        check = LogWatchCheck(log_dir=self.tmpdir)
        result = check.run()
        assert result.is_unhealthy is False
