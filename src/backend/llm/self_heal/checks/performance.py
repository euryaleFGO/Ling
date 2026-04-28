"""Performance check – monitors rolling error rate."""

from collections import deque
from typing import Dict

from .base_check import CheckResult, HealthCheck


class PerformanceCheck(HealthCheck):
    """Track a sliding window of success/failure outcomes and flag high error rates.

    External callers should invoke :meth:`record` after each operation to
    report whether it succeeded.
    """

    def __init__(
        self,
        window_size: int = 100,
        error_rate_threshold: float = 0.3,
    ) -> None:
        self._window_size = window_size
        self._error_rate_threshold = error_rate_threshold
        # Circular buffer of booleans: True = success, False = failure.
        self._results: deque = deque(maxlen=window_size)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def record(self, success: bool) -> None:
        """Record the outcome of a single operation.

        Parameters
        ----------
        success:
            ``True`` if the operation completed without error, ``False`` otherwise.
        """
        self._results.append(success)

    # ------------------------------------------------------------------
    # HealthCheck interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "performance"

    @property
    def interval(self) -> float:
        return 10.0

    def run(self) -> CheckResult:
        total = len(self._results)
        if total == 0:
            return CheckResult(
                is_unhealthy=False,
                event_type="high_error_rate",
                severity="low",
                data={"total": 0, "errors": 0, "error_rate": 0.0},
            )

        errors = sum(1 for s in self._results if not s)
        error_rate = errors / total

        if error_rate >= self._error_rate_threshold:
            return CheckResult(
                is_unhealthy=True,
                event_type="high_error_rate",
                severity="medium",
                data={
                    "total": total,
                    "errors": errors,
                    "error_rate": round(error_rate, 4),
                    "threshold": self._error_rate_threshold,
                },
            )

        return CheckResult(
            is_unhealthy=False,
            event_type="high_error_rate",
            severity="low",
            data={
                "total": total,
                "errors": errors,
                "error_rate": round(error_rate, 4),
            },
        )
