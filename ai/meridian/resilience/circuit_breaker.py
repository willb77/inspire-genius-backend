from __future__ import annotations

"""
Circuit Breaker pattern for LLM provider and agent failures.

States: CLOSED (normal) → OPEN (failing, reject calls) → HALF_OPEN (testing recovery)
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger


class CircuitState(str, Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing — reject calls, use fallback
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading failures.

    - CLOSED: requests pass through normally
    - OPEN: requests are rejected immediately (use fallback)
    - HALF_OPEN: one test request allowed; success → CLOSED, failure → OPEN
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: int = 60,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = timedelta(seconds=recovery_timeout_seconds)
        self._half_open_max = half_open_max_calls
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0
        self._total_calls = 0
        self._total_failures = 0
        self._total_rejected = 0

    @property
    def state(self) -> CircuitState:
        """Get current state, auto-transitioning OPEN → HALF_OPEN after timeout."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            if datetime.utcnow() - self._last_failure_time >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"CircuitBreaker '{self.name}': OPEN → HALF_OPEN (recovery timeout elapsed)")
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            if self._half_open_calls < self._half_open_max:
                self._half_open_calls += 1
                return True
            return False
        # OPEN
        self._total_rejected += 1
        return False

    def record_success(self) -> None:
        """Record a successful call."""
        self._total_calls += 1
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            logger.info(f"CircuitBreaker '{self.name}': HALF_OPEN → CLOSED (success)")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._total_calls += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = datetime.utcnow()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning(f"CircuitBreaker '{self.name}': HALF_OPEN → OPEN (failure during recovery)")
        elif self._state == CircuitState.CLOSED and self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(f"CircuitBreaker '{self.name}': CLOSED → OPEN (threshold {self._failure_threshold} reached)")

    def reset(self) -> None:
        """Manually reset to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0

    def get_stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_rejected": self._total_rejected,
        }
