import os
import sys
import threading

import pytest

# Ensure src is on the path so we can import the package under test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.backend.llm.self_heal.event_bus import Event, EventBus


# ---------- Event creation ----------

class TestEventCreation:
    def test_event_creation(self):
        e = Event(type="test", severity="low", source="unit", data={"key": "value"})
        assert e.type == "test"
        assert e.severity == "low"
        assert e.source == "unit"
        assert e.data == {"key": "value"}
        assert isinstance(e.timestamp, float)
        assert e.handled is False

    def test_event_default_handled(self):
        e = Event(type="x", severity="low", source="s", data={})
        assert e.handled is False


# ---------- EventBus basics ----------

class TestEventBus:
    def test_register_and_emit(self):
        bus = EventBus()
        received = []
        bus.on("ping", lambda e: received.append(e))
        evt = Event(type="ping", severity="low", source="t", data={})
        bus.emit(evt)
        assert len(received) == 1
        assert received[0] is evt

    def test_multiple_handlers(self):
        bus = EventBus()
        results = {"a": 0, "b": 0}
        bus.on("ev", lambda e: results.__setitem__("a", results["a"] + 1))
        bus.on("ev", lambda e: results.__setitem__("b", results["b"] + 1))
        bus.emit(Event(type="ev", severity="low", source="t", data={}))
        assert results["a"] == 1
        assert results["b"] == 1

    def test_wildcard_handler(self):
        bus = EventBus()
        received = []
        bus.on("*", lambda e: received.append(e.type))
        bus.emit(Event(type="foo", severity="low", source="t", data={}))
        bus.emit(Event(type="bar", severity="high", source="t", data={}))
        assert received == ["foo", "bar"]

    def test_handler_exception_does_not_crash(self):
        bus = EventBus()

        def bad_handler(_e):
            raise RuntimeError("boom")

        bus.on("err", bad_handler)
        # Should not raise
        bus.emit(Event(type="err", severity="low", source="t", data={}))

    def test_thread_safety(self):
        bus = EventBus()
        counter = {"n": 0}
        lock = threading.Lock()

        def inc(_e):
            with lock:
                counter["n"] += 1

        bus.on("concurrent", inc)

        threads = [
            threading.Thread(
                target=lambda: bus.emit(
                    Event(type="concurrent", severity="low", source="t", data={})
                )
            )
            for _ in range(100)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter["n"] == 100
