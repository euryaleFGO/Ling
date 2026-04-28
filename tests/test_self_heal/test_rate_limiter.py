"""Tests for RateLimiter."""

import time
import threading

from src.backend.llm.self_heal.rate_limiter import RateLimiter


def test_allows_within_limit():
    """Should allow calls up to the max limit."""
    rl = RateLimiter(max_per_window=3, window_seconds=10)
    assert rl.allow("search") is True
    assert rl.allow("search") is True
    assert rl.allow("search") is True


def test_blocks_over_limit():
    """Should block calls once the limit is reached."""
    rl = RateLimiter(max_per_window=2, window_seconds=10)
    assert rl.allow("repair") is True
    assert rl.allow("repair") is True
    assert rl.allow("repair") is False


def test_different_strategies_independent():
    """Different operation names should have independent counters."""
    rl = RateLimiter(max_per_window=1, window_seconds=10)
    assert rl.allow("strategy_a") is True
    assert rl.allow("strategy_b") is True
    assert rl.allow("strategy_a") is False
    assert rl.allow("strategy_b") is False


def test_window_expiry():
    """Old timestamps should be pruned after the window expires."""
    rl = RateLimiter(max_per_window=1, window_seconds=0.1)
    assert rl.allow("retry") is True
    assert rl.allow("retry") is False
    time.sleep(0.15)
    assert rl.allow("retry") is True


def test_reset():
    """Reset should clear the counter for a given operation."""
    rl = RateLimiter(max_per_window=1, window_seconds=10)
    assert rl.allow("deploy") is True
    assert rl.allow("deploy") is False
    rl.reset("deploy")
    assert rl.allow("deploy") is True


def test_thread_safety():
    """Multiple threads calling allow should respect the global limit."""
    rl = RateLimiter(max_per_window=5, window_seconds=10)
    results = []

    def worker():
        results.append(rl.allow("concurrent"))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed = sum(1 for r in results if r is True)
    assert allowed == 5
