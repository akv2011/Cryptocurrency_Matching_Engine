"""
Performance metrics collection for the matching engine.

Tracks latency and throughput for monitoring and optimization.
"""

import time
from typing import Dict, List
from collections import deque
from datetime import datetime
import threading


class LatencyTracker:
    """Track latency statistics with percentiles."""
    
    def __init__(self, max_samples: int = 10000):
        self.max_samples = max_samples
        self.samples = deque(maxlen=max_samples)
        self.lock = threading.Lock()
    
    def record(self, latency_ms: float) -> None:
        """Record a latency sample in milliseconds."""
        with self.lock:
            self.samples.append(latency_ms)
    
    def get_statistics(self) -> Dict[str, float]:
        """Get latency statistics."""
        with self.lock:
            if not self.samples:
                return {
                    "count": 0,
                    "mean": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0
                }
            
            sorted_samples = sorted(self.samples)
            count = len(sorted_samples)
            
            return {
                "count": count,
                "mean": sum(sorted_samples) / count,
                "min": sorted_samples[0],
                "max": sorted_samples[-1],
                "p50": sorted_samples[int(count * 0.50)],
                "p95": sorted_samples[int(count * 0.95)],
                "p99": sorted_samples[int(count * 0.99)]
            }
    
    def reset(self) -> None:
        """Reset all samples."""
        with self.lock:
            self.samples.clear()


class ThroughputTracker:
    """Track throughput (operations per second)."""
    
    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.timestamps = deque()
        self.lock = threading.Lock()
    
    def record(self) -> None:
        """Record an operation."""
        with self.lock:
            now = time.time()
            self.timestamps.append(now)
            
            # Remove timestamps outside the window
            cutoff = now - self.window_seconds
            while self.timestamps and self.timestamps[0] < cutoff:
                self.timestamps.popleft()
    
    def get_rate(self) -> float:
        """Get current operations per second."""
        with self.lock:
            if not self.timestamps:
                return 0.0
            
            now = time.time()
            cutoff = now - self.window_seconds
            
            # Remove stale timestamps
            while self.timestamps and self.timestamps[0] < cutoff:
                self.timestamps.popleft()
            
            if not self.timestamps:
                return 0.0
            
            # Calculate rate
            time_span = now - self.timestamps[0]
            if time_span == 0:
                return 0.0
            
            return len(self.timestamps) / time_span
    
    def reset(self) -> None:
        """Reset all timestamps."""
        with self.lock:
            self.timestamps.clear()


class PerformanceMetrics:
    """
    Collect and track performance metrics for the matching engine.
    
    Tracks:
    - Order processing latency
    - BBO update latency
    - Trade generation latency
    - Order submission throughput
    """
    
    def __init__(self):
        self.order_latency = LatencyTracker()
        self.bbo_latency = LatencyTracker()
        self.trade_latency = LatencyTracker()
        self.order_throughput = ThroughputTracker()
        
        self.start_time = datetime.utcnow()
    
    def record_order_latency(self, latency_ms: float) -> None:
        """Record order processing latency."""
        self.order_latency.record(latency_ms)
        self.order_throughput.record()
    
    def record_bbo_latency(self, latency_ms: float) -> None:
        """Record BBO update latency."""
        self.bbo_latency.record(latency_ms)
    
    def record_trade_latency(self, latency_ms: float) -> None:
        """Record trade generation latency."""
        self.trade_latency.record(latency_ms)
    
    def get_statistics(self) -> Dict:
        """Get all performance statistics."""
        return {
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
            "order_processing": self.order_latency.get_statistics(),
            "bbo_updates": self.bbo_latency.get_statistics(),
            "trade_generation": self.trade_latency.get_statistics(),
            "throughput": {
                "orders_per_second": self.order_throughput.get_rate()
            }
        }
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.order_latency.reset()
        self.bbo_latency.reset()
        self.trade_latency.reset()
        self.order_throughput.reset()
        self.start_time = datetime.utcnow()


# Global metrics instance
_metrics = PerformanceMetrics()


def get_metrics() -> PerformanceMetrics:
    """Get global metrics instance."""
    return _metrics


# Context manager for timing operations
class Timer:
    """Context manager for timing code blocks."""
    
    def __init__(self):
        self.start_time = None
        self.elapsed_ms = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        end_time = time.perf_counter()
        self.elapsed_ms = (end_time - self.start_time) * 1000  # Convert to ms
    
    def get_elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return self.elapsed_ms if self.elapsed_ms is not None else 0.0
