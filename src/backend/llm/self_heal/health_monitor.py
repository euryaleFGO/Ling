"""Background daemon that runs registered health checks periodically."""

import logging
import threading
import time
from typing import Dict, List, Optional

from .checks.base_check import HealthCheck, CheckResult
from .event_bus import Event, EventBus

logger = logging.getLogger("self_heal")

# Consecutive-error thresholds for severity escalation
_MEDIUM_THRESHOLD = 5
_HIGH_THRESHOLD = 10


class HealthMonitor:
    """Runs health checks in a background thread and emits events on failures."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._checks: List[HealthCheck] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._error_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_check(self, check: HealthCheck) -> None:
        """Add a health check to be monitored."""
        self._checks.append(check)

    def start(self) -> None:
        """Start the background monitoring thread (idempotent)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="health-monitor",
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the monitor to stop and wait for the thread to finish."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Main loop executed by the background thread."""
        while self._running:
            for check in self._checks:
                try:
                    result: CheckResult = check.run()
                    if result.is_unhealthy:
                        count = self._error_counts.get(check.name, 0) + 1
                        self._error_counts[check.name] = count
                        severity = result.severity
                        if count >= _HIGH_THRESHOLD:
                            severity = "high"
                        elif count >= _MEDIUM_THRESHOLD:
                            severity = "medium"
                        self._event_bus.emit(
                            Event(
                                type=result.event_type,
                                severity=severity,
                                source=check.name,
                                data={**result.data, "error_count": count},
                            )
                        )
                    else:
                        # Reset consecutive error count on healthy result
                        self._error_counts.pop(check.name, None)
                except Exception as exc:
                    logger.error(
                        "Health check %s failed with exception: %s",
                        check.name,
                        exc,
                    )
                time.sleep(check.interval)
            time.sleep(0.1)
