"""Emergency stop – global kill switch for all automatic repairs."""

import threading


class EmergencyStopError(Exception):
    """Raised when emergency stop is triggered."""
    pass


class EmergencyStop:
    """Global kill switch to halt all automatic repairs.

    When activated via :meth:`stop`, any call to :meth:`check` will
    raise :class:`EmergencyStopError`, which the self-healing
    orchestrator can catch to abort all pending actions.
    """

    def __init__(self):
        self._stopped = threading.Event()

    @property
    def is_stopped(self) -> bool:
        return self._stopped.is_set()

    def check(self) -> None:
        """Raise EmergencyStopError if the stop has been activated."""
        if self._stopped.is_set():
            raise EmergencyStopError("Emergency stop active: all automatic repairs halted")

    def stop(self) -> None:
        """Activate the emergency stop."""
        self._stopped.set()

    def reset(self) -> None:
        """De-activate the emergency stop."""
        self._stopped.clear()
