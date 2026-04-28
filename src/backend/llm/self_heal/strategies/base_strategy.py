"""Base strategy abstract class and FixResult dataclass."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict

from ..event_bus import Event


@dataclass
class FixResult:
    """Result returned by a fix strategy."""
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


class FixStrategy(ABC):
    """Abstract base class for all self-healing fix strategies.

    Subclasses must implement:
    - can_handle(event): return True if this strategy can attempt the fix
    - fix(event): attempt the fix and return a FixResult
    """

    @abstractmethod
    def can_handle(self, event: Event) -> bool:
        """Return True if this strategy can handle the given event."""
        pass

    @abstractmethod
    def fix(self, event: Event) -> FixResult:
        """Attempt to fix the issue described by the event.

        Returns a FixResult indicating success or failure.
        """
        pass
