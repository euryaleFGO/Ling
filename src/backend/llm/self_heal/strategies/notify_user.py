"""NotifyUserStrategy — last-resort user notification."""

import logging
from typing import Callable, Optional

from ..event_bus import Event
from .base_strategy import FixStrategy, FixResult

logger = logging.getLogger(__name__)


class NotifyUserStrategy(FixStrategy):
    """Last-resort strategy that notifies the user about an unresolvable error.

    This strategy always returns ``FixResult(success=False)`` because
    it cannot actually fix anything — it only reports the problem.

    A custom notifier callable can be supplied (e.g. to send a
    desktop notification or Slack message).  By default it prints to
    the log.
    """

    def __init__(self, notifier: Optional[Callable[[str], None]] = None):
        self._notifier = notifier or self._default_notifier

    @staticmethod
    def _default_notifier(message: str) -> None:
        logger.warning("NOTIFY USER: %s", message)
        print(f"[NOTIFY] {message}")

    def can_handle(self, event: Event) -> bool:
        """Always can handle — this is the fallback of last resort."""
        return True

    def fix(self, event: Event) -> FixResult:
        """Notify the user. Always returns success=False."""
        message = (
            f"Unresolved error [{event.severity}] from {event.source}: "
            f"{event.type} — manual intervention may be required. "
            f"Details: {event.data}"
        )
        try:
            self._notifier(message)
        except Exception as exc:
            logger.error("Failed to send user notification: %s", exc)

        return FixResult(
            success=False,
            message=f"User notified: {event.type}",
            data={"notification_sent": True},
        )
