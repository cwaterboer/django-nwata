#!/usr/bin/env python3
"""
Test script for context monitoring in nwata_min.py
Verifies ContextSignals, ContextMonitor, and context data flow
"""

import json
from datetime import datetime, timezone, timedelta
import threading

# Inline the classes to test without PyQt5 dependency
class ContextSignals:
    """Aggregates context signals for a single window log."""
    def __init__(self):
        self.typing_count = 0        # Number of typing events
        self.scroll_count = 0        # Number of scroll events
        self.shortcut_count = 0      # Number of shortcuts in this window
        self.total_idle_ms = 0       # Cumulative idle time (ms)
        self.max_idle_ms = 0         # Longest single idle pause (ms)
        self.last_activity_time = None  # Timestamp of last typing/scroll
    
    def record_typing(self, now):
        """Record a typing event."""
        if self.last_activity_time:
            idle = (now - self.last_activity_time).total_seconds() * 1000
            self.total_idle_ms += idle
            self.max_idle_ms = max(self.max_idle_ms, idle)
        self.typing_count += 1
        self.last_activity_time = now
    
    def record_scroll(self, now):
        """Record a scroll event."""
        if self.last_activity_time:
            idle = (now - self.last_activity_time).total_seconds() * 1000
            self.total_idle_ms += idle
            self.max_idle_ms = max(self.max_idle_ms, idle)
        self.scroll_count += 1
        self.last_activity_time = now
    
    def record_shortcut(self):
        """Record a shortcut in current window."""
        self.shortcut_count += 1
    
    def finalize(self, window_duration_s):
        """Finalize context data and compute derived metrics."""
        context = {
            "typing_count": self.typing_count,
            "scroll_count": self.scroll_count,
            "shortcut_count": self.shortcut_count,
            "total_idle_ms": int(self.total_idle_ms),
            "max_idle_ms": int(self.max_idle_ms),
            "window_duration_s": window_duration_s,
        }
        
        # Derived: typing rate per minute
        if window_duration_s > 0:
            context["typing_rate_per_min"] = round(
                (self.typing_count / (window_duration_s / 60)), 2
            )
            context["scroll_rate_per_min"] = round(
                (self.scroll_count / (window_duration_s / 60)), 2
            )
        else:
            context["typing_rate_per_min"] = 0
            context["scroll_rate_per_min"] = 0
        
        return context


class ContextMonitor:
    """Tracks keyboard, scroll, and other signal events for aggregation per window."""
    def __init__(self):
        self.current_signals = ContextSignals()
        self.lock = threading.Lock()
    
    def record_typing(self):
        """Called when a keyboard/typing event is detected."""
        with self.lock:
            self.current_signals.record_typing(datetime.now(timezone.utc))
    
    def record_scroll(self):
        """Called when a scroll event is detected."""
        with self.lock:
            self.current_signals.record_scroll(datetime.now(timezone.utc))
    
    def record_shortcut(self):
        """Called when a keyboard shortcut is detected in current window."""
        with self.lock:
            self.current_signals.record_shortcut()
    
    def finalize_and_reset(self, window_duration_s):
        """Finalize current window's context, reset for next window."""
        with self.lock:
            context = self.current_signals.finalize(window_duration_s)
            self.current_signals = ContextSignals()
        return context


# Tests
def test_context_signals():
    """Test ContextSignals aggregation"""
    print("\n=== TEST 1: ContextSignals ===")
    
    signals = ContextSignals()
    now = datetime.now(timezone.utc)
    
    # Simulate activity
    signals.record_typing(now)
    signals.record_typing(now + timedelta(seconds=1))
    signals.record_typing(now + timedelta(seconds=3))  # 2s idle
    signals.record_scroll(now + timedelta(seconds=4))
    signals.record_scroll(now + timedelta(seconds=5))
    signals.record_shortcut()
    signals.record_shortcut()
    
    # Finalize after 10 seconds
    context = signals.finalize(10)
    
    print(f"Typing count: {context['typing_count']}")
    print(f"Scroll count: {context['scroll_count']}")
    print(f"Shortcut count: {context['shortcut_count']}")
    print(f"Total idle (ms): {context['total_idle_ms']}")
    print(f"Max idle (ms): {context['max_idle_ms']}")
    print(f"Window duration (s): {context['window_duration_s']}")
    print(f"Typing rate (per min): {context['typing_rate_per_min']}")
    print(f"Scroll rate (per min): {context['scroll_rate_per_min']}")
    
    assert context['typing_count'] == 3, "Expected 3 typing events"
    assert context['scroll_count'] == 2, "Expected 2 scroll events"
    assert context['shortcut_count'] == 2, "Expected 2 shortcuts"
    assert context['total_idle_ms'] == 2000, "Expected ~2000ms idle"
    assert context['typing_rate_per_min'] == 18.0, "Expected 18 typing/min"
    print("✓ ContextSignals test passed\n")


def test_context_monitor():
    """Test ContextMonitor aggregation and reset"""
    print("=== TEST 2: ContextMonitor ===")
    
    monitor = ContextMonitor()
    
    # Record multiple signals
    monitor.record_typing()
    monitor.record_typing()
    monitor.record_scroll()
    monitor.record_shortcut()
    monitor.record_shortcut()
    monitor.record_shortcut()
    
    # Finalize
    context = monitor.finalize_and_reset(5)
    
    print(f"Typing count: {context['typing_count']}")
    print(f"Scroll count: {context['scroll_count']}")
    print(f"Shortcut count: {context['shortcut_count']}")
    
    assert context['typing_count'] == 2, "Expected 2 typing events"
    assert context['scroll_count'] == 1, "Expected 1 scroll event"
    assert context['shortcut_count'] == 3, "Expected 3 shortcuts"
    
    # After reset, new signals should not be in old context
    monitor.record_typing()
    context2 = monitor.finalize_and_reset(5)
    
    assert context2['typing_count'] == 1, "Expected 1 typing in new window"
    assert context2['scroll_count'] == 0, "Expected 0 scrolls in new window"
    print("✓ ContextMonitor test passed\n")


def test_context_json_serialization():
    """Test that context data can be JSON serialized"""
    print("=== TEST 3: JSON Serialization ===")
    
    signals = ContextSignals()
    now = datetime.now(timezone.utc)
    
    for i in range(5):
        signals.record_typing(now + timedelta(seconds=i))
    
    context = signals.finalize(10)
    
    # Should be JSON serializable
    json_str = json.dumps(context)
    print(f"JSON context: {json_str}")
    
    # Should deserialize cleanly
    recovered = json.loads(json_str)
    assert recovered['typing_count'] == 5
    print("✓ JSON serialization test passed\n")


def test_window_context_flow():
    """Simulate a 2-window flow"""
    print("=== TEST 4: Multi-Window Flow ===")
    
    monitor = ContextMonitor()
    
    # Window 1: Editor (lots of typing)
    print("Window 1: Editor")
    for _ in range(10):
        monitor.record_typing()
    for _ in range(2):
        monitor.record_scroll()
    
    context1 = monitor.finalize_and_reset(30)
    print(f"  Typing: {context1['typing_count']}, Scroll: {context1['scroll_count']}")
    
    # Window 2: Browser (passive, some scrolling)
    print("Window 2: Browser")
    for _ in range(3):
        monitor.record_scroll()
    for _ in range(1):
        monitor.record_typing()
    
    context2 = monitor.finalize_and_reset(20)
    print(f"  Typing: {context2['typing_count']}, Scroll: {context2['scroll_count']}")
    
    assert context1['typing_count'] == 10
    assert context1['scroll_count'] == 2
    assert context2['typing_count'] == 1
    assert context2['scroll_count'] == 3
    print("✓ Multi-window flow test passed\n")


if __name__ == "__main__":
    print("\n" + "="*50)
    print("CONTEXT MONITORING TESTS")
    print("="*50)
    
    try:
        test_context_signals()
        test_context_monitor()
        test_context_json_serialization()
        test_window_context_flow()
        
        print("="*50)
        print("✓ ALL TESTS PASSED")
        print("="*50 + "\n")
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        exit(1)
