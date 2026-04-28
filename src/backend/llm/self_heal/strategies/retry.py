"""RetryStrategy — retry with exponential backoff."""

import logging
import time
from typing import Callable, Optional

from ..event_bus import Event
from .base_strategy import FixStrategy, FixResult

logger = logging.getLogger(__name__)


class RetryStrategy(FixStrategy):
    """Retry a failed operation with exponential backoff.

    Usage::

        strategy = RetryStrategy()
        strategy.set_retry_fn(my_flaky_function)
        result = strategy.fix(event)

    The retry function is called with no arguments.  If it returns a
    truthy value the fix is considered successful.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._retry_fn: Optional[Callable] = None

    def set_retry_fn(self, fn: Callable) -> None:
        """Set the function to be retried on failure."""
        self._retry_fn = fn

    def can_handle(self, event: Event) -> bool:
        """Retry strategy can handle any event that has a retryable flag
        or any transient error (severity low/medium)."""
        if event.data.get("retryable", False):
            return True
        return event.severity in ("low", "medium")

    def fix(self, event: Event) -> FixResult:
        """Attempt the retry with exponential backoff."""
        if self._retry_fn is None:
            return FixResult(success=False, message="No retry function configured")

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                result = self._retry_fn()
                if result:
                    logger.info("Retry succeeded on attempt %d", attempt)
                    return FixResult(
                        success=True,
                        message=f"Retry succeeded on attempt {attempt}",
                        data={"attempts": attempt},
                    )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Retry attempt %d/%d failed: %s",
                    attempt, self._max_retries, exc,
                )

            if attempt < self._max_retries:
                delay = min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)
                time.sleep(delay)

        return FixResult(
            success=False,
            message=f"All {self._max_retries} retries failed",
            data={"attempts": self._max_retries, "last_error": str(last_error)},
        )
