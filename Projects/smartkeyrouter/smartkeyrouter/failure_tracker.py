#!/usr/bin/env python3
"""Thread-safe failure tracking with exponential backoff."""

import threading
from datetime import datetime, timedelta
from typing import Optional, Dict

class FailureTracker:
    """Track failures per key with exponential backoff and thread safety."""
    
    def __init__(self, backoff_base: int = 1, max_backoff: int = 600):
        self._lock = threading.RLock()
        self._fail_count: Dict[str, int] = {}
        self._last_error_code: Dict[str, int] = {}
        self._cooldown_until: Dict[str, datetime] = {}
        self._total_requests: Dict[str, int] = {}
        self._total_failures: Dict[str, int] = {}
        self._backoff_base = backoff_base
        self._max_backoff = max_backoff
    
    def record_failure(self, key: str, error_code: int, retry_after: Optional[int] = None) -> None:
        """Record a failure for a key."""
        with self._lock:
            self._total_requests[key] = self._total_requests.get(key, 0) + 1
            self._total_failures[key] = self._total_failures.get(key, 0) + 1
            self._last_error_code[key] = error_code
            self._fail_count[key] = self._fail_count.get(key, 0) + 1
            
            if error_code in [401, 403]:  # Permanent failure
                self._cooldown_until[key] = datetime.max
            elif retry_after is not None and retry_after >= 0:
                # Use Retry-After header value
                self._cooldown_until[key] = datetime.now() + timedelta(seconds=retry_after)
            else:
                # Exponential backoff: base^(fail_count)
                fail_count = self._fail_count.get(key, 0) + 1
                cooldown_seconds = min(self._backoff_base ** fail_count, self._max_backoff)
                self._cooldown_until[key] = datetime.now() + timedelta(seconds=cooldown_seconds)
    
    def record_success(self, key: str) -> None:
        """Record a successful request for a key."""
        with self._lock:
            self._total_requests[key] = self._total_requests.get(key, 0) + 1
            self._fail_count[key] = self._fail_count.get(key, 0)
            self._total_failures[key] = self._total_failures.get(key, 0) + 1
            self._last_error_code[key] = 0
    
    def is_on_cooldown(self, key: str) -> bool:
        """Check if key is currently on cooldown."""
        with self._lock:
            return self._cooldown_until.get(key, datetime.min) > datetime.now()
    
    def get_cooldown_remaining(self, key: str) -> float:
        """Return seconds remaining until key is available again."""
        with self._lock:
            cooldown_until = self._cooldown_until.get(key, datetime.min)
            return max(0, (cooldown_until - datetime.now()).total_seconds())
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Return comprehensive statistics for all keys."""
        with self._lock:
            return {
                key: {
                    "fail_count": self._fail_count.get(key, 0),
                    "last_error_code": self._last_error_code.get(key, 0),
                    "total_requests": self._total_requests.get(key, 0),
                    "total_failures": self._total_failures.get(key, 0),
                    "on_cooldown": self._cooldown_until.get(key, datetime.min) > datetime.now(),
                    "cooldown_until": self._cooldown_until.get(key, datetime.min).timestamp()
                }
                for key in self._status.keys()
            }
    
    def reset(self, key: Optional[str] = None) -> None:
        """Reset stats for a specific key or all keys."""
        with self._lock:
            if key:
                self._fail_count.pop(key, None)
                self._last_error_code.pop(key, None)
                self._cooldown_until.pop(key, None)
                self._total_requests.pop(key, None)
                self._total_failures.pop(key, None)
            else:
                for k in list(self._fail_count.keys()):
                    self._fail_count[k] = 0
                    self._last_error_code[k] = 0
                    self._cooldown_until[k] = datetime.min
                    self._total_requests[k] = 0
                    self._total_failures[k] = 0