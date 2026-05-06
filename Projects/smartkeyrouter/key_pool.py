#!/usr/bin/env python3
"""KeyPool for managing keys with round-robin, random, and sequential strategies."""

import threading
from typing import List, Optional, Literal
from datetime import datetime, timedelta

class KeyPool:
    """Round-robin / random / sequential key pool for one provider."""
    
    def __init__(self, keys: List[str], strategy: str = "round_robin", failure_tracker=None):
        self._keys = keys
        self._strategy = strategy
        self._failure_tracker = failure_tracker
        self._index = 0
        self._lock = threading.Lock()
        self._status = {key: {"on_cooldown": False, "cooldown_until": None} for key in keys}
    
    def get_next_key(self) -> Optional[str]:
        """Return next available key, or None if all on cooldown."""
        with self._lock:
            if not self._keys:
                return None
                
            # Get all keys that are not on cooldown
            available_keys = [
                key for key in self._keys 
                if not self._status[key]["on_cooldown"]
            ]
            
            if not available_keys:
                return None
                
            if self._strategy == "round_robin":
                # Find next key in circular order
                start_index = self._index
                for i in range(len(self._keys)):
                    idx = (start_index + i) % len(self._keys)
                    key = self._keys[idx]
                    if not self._status[key]["on_cooldown"]:
                        self._index = (idx + 1) % len(self._keys)
                        return key
                return None
                
            elif self._strategy == "random":
                import random
                available = [key for key in self._keys if not self._status[key]["on_cooldown"]]
                return random.choice(available) if available else None
                
            elif self._strategy == "sequential":
                # Always start from first available key
                for key in self._keys:
                    if not self._status[key]["on_cooldown"]:
                        self._index = self._keys.index(key)
                        return key
                return None
    
    def mark_failed(self, key: str, error_code: int) -> None:
        """Record failure for key and set cooldown."""
        if key not in self._status:
            return
            
        with self._lock:
            self._status[key]["fail_count"] = self._status.get(key, {"fail_count": 0})["fail_count"] + 1
            self._status[key]["last_error_code"] = error_code
            self._status[key]["total_requests"] = self._status.get(key, {"total_requests": 0})["total_requests"] + 1
            self._status[key]["total_failures"] = self._status.get(key, {"total_failures": 0})["total_failures"] + 1
            
            # Set cooldown based on error type
            if error_code in [401, 403]:  # Invalid key
                self._status[key]["on_cooldown"] = True
                self._status[key]["cooldown_until"] = datetime.max
            elif error_code in [429, 500, 502, 503]:  # Rate limit or server error
                retry_after = 30  # Default 30 seconds
                # In real implementation, this would come from response header
                self._status[key]["on_cooldown"] = True
                self._status[key]["cooldown_until"] = datetime.now() + timedelta(seconds=retry_after)
            else:
                # For other errors, use exponential backoff
                fail_count = self._status[key]["fail_count"]
                base = self._failure_tracker.backoff_base_seconds if self._failure_tracker else 1
                cooldown_seconds = min(base ** fail_count, 600)
                self._status[key]["on_cooldown"] = True
                self._status[key]["cooldown_until"] = datetime.now() + timedelta(seconds=cooldown_seconds)
    
    def mark_success(self, key: str) -> None:
        """Reset failure count for key."""
        with self._lock:
            if key in self._status:
                self._status[key]["fail_count"] = 0
                self._status[key]["last_error_code"] = 0
                self._status[key]["on_cooldown"] = False
                self._status[key]["cooldown_until"] = None
    
    def get_status(self) -> dict:
        """Return status of all keys (masked)."""
        with self._lock:
            return {
                self.mask_key(key): {
                    "status": "on_cooldown" if info["on_cooldown"] else "available",
                    "cooldown_until": info["cooldown_until"].timestamp() if info["cooldown_until"] else None,
                    "fail_count": info.get("fail_count", 0),
                    "total_requests": info.get("total_requests", 0),
                    "total_failures": info.get("total_failures", 0)
                }
                for key, info in self._status.items()
            }
    
    def mask_key(self, key: str) -> str:
        """Mask key to show only first 8 characters + '...'."""
        if not key:
            return "..."
        return key[:8] + "..." if len(key) > 8 else key

    def is_on_cooldown(self, key: str) -> bool:
        """Check if key is on cooldown."""
        with self._lock:
            return self._status.get(key, {}).get("on_cooldown", False)