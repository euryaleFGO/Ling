import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class Event:
    """An event emitted by health checks or error handlers."""
    type: str
    severity: str  # low, medium, high, critical
    source: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    handled: bool = False


class EventBus:
    """Thread-safe event bus for dispatching events to handlers."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def on(self, event_type: str, handler: Callable) -> None:
        """Register a handler for an event type. Use '*' for all events."""
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """Unregister a handler."""
        with self._lock:
            if event_type in self._handlers:
                self._handlers[event_type] = [
                    h for h in self._handlers[event_type] if h != handler
                ]

    def emit(self, event: Event) -> None:
        """Dispatch event to all matching handlers (thread-safe)."""
        with self._lock:
            handlers = list(self._handlers.get(event.type, []))
            handlers += list(self._handlers.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass  # Handler errors must not crash the bus
