"""ErrorHandler — orchestrates strategy chain for self-healing."""

import logging
from typing import List, Optional

from .event_bus import Event, EventBus
from .backup_manager import BackupManager
from .rate_limiter import RateLimiter
from .emergency_stop import EmergencyStop, EmergencyStopError
from .strategies.base_strategy import FixStrategy, FixResult

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Orchestrates a chain of :class:`FixStrategy` instances to handle errors.

    On construction the handler registers itself as a ``"*"`` wildcard
    listener on the provided :class:`EventBus`, so every event emitted
    on the bus will be passed through the strategy chain automatically.

    Processing order:
    1. Check emergency stop — abort immediately if active.
    2. Check rate limiter — abort if the operation is rate-limited.
    3. Create a backup snapshot (if config files are referenced).
    4. Iterate through strategies in order; the first one that both
       ``can_handle`` and ``fix`` succeeds wins.
    5. If the fix fails and a snapshot was created, attempt rollback.
    6. If all strategies fail, emit ``fix_failed``.
    """

    # Event types emitted by the handler itself — never re-process
    _INTERNAL_EVENT_TYPES = {"fix_applied", "fix_failed"}

    def __init__(
        self,
        event_bus: EventBus,
        backup_manager: Optional[BackupManager] = None,
        rate_limiter: Optional[RateLimiter] = None,
        emergency_stop: Optional[EmergencyStop] = None,
    ):
        self._event_bus = event_bus
        self._backup_manager = backup_manager
        self._rate_limiter = rate_limiter
        self._emergency_stop = emergency_stop
        self._strategies: List[FixStrategy] = []

        # Register as wildcard handler
        self._event_bus.on("*", self._handle_event)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_strategy(self, strategy: FixStrategy) -> None:
        """Append a strategy to the end of the chain."""
        self._strategies.append(strategy)

    def handle(self, event: Event) -> FixResult:
        """Run the strategy chain against *event*.

        Returns the first successful :class:`FixResult`, or a failure
        result if no strategy could resolve the issue.
        """
        # 1. Emergency stop
        if self._emergency_stop is not None:
            if self._emergency_stop.is_stopped:
                logger.warning("Emergency stop active — aborting repair for %s", event.type)
                return FixResult(
                    success=False,
                    message="Emergency stop active — all automatic repairs halted",
                )

        # 2. Rate limiter
        if self._rate_limiter is not None:
            if not self._rate_limiter.allow(event.type):
                logger.warning("Rate limit exceeded for event type '%s'", event.type)
                return FixResult(
                    success=False,
                    message=f"Rate limit exceeded for '{event.type}'",
                )

        # 3. Backup (if config files referenced)
        snapshot = None
        config_files = event.data.get("config_files")
        if config_files and self._backup_manager is not None:
            try:
                snapshot = self._backup_manager.create_snapshot(
                    file_paths=config_files,
                    reason="pre-fix backup",
                )
                logger.info("Created pre-fix backup snapshot %s", snapshot.id)
            except Exception as exc:
                logger.warning("Failed to create backup snapshot: %s", exc)

        # 4. Try each strategy in order
        tried = 0
        for strategy in self._strategies:
            if not strategy.can_handle(event):
                continue
            tried += 1
            try:
                result = strategy.fix(event)
                if result.success:
                    self._event_bus.emit(Event(
                        type="fix_applied",
                        severity=event.severity,
                        source=type(strategy).__name__,
                        data={
                            "original_event": event.type,
                            "strategy": type(strategy).__name__,
                            "message": result.message,
                        },
                    ))
                    return result
            except Exception as exc:
                logger.warning(
                    "Strategy %s raised exception: %s",
                    type(strategy).__name__, exc,
                )

        # 5. Rollback on failure (if a snapshot was made)
        if snapshot is not None and self._backup_manager is not None:
            try:
                self._backup_manager.rollback(snapshot)
                logger.info("Rolled back to snapshot %s after failed fix", snapshot.id)
            except Exception as exc:
                logger.error("Rollback failed: %s", exc)

        # 6. All strategies failed
        self._event_bus.emit(Event(
            type="fix_failed",
            severity=event.severity,
            source="ErrorHandler",
            data={
                "original_event": event.type,
                "tried_strategies": tried,
                "total_strategies": len(self._strategies),
            },
        ))
        return FixResult(
            success=False,
            message=f"All strategies failed ({tried} tried)",
            data={"tried": tried, "total": len(self._strategies)},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_event(self, event: Event) -> None:
        """Wildcard handler registered on the EventBus."""
        if event.handled:
            return
        if event.type in self._INTERNAL_EVENT_TYPES:
            return
        event.handled = True
        self.handle(event)
