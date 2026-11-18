"""
Enterprise Connection Resilience & Least-Privilege Policy Enforcement Engine.
Enforces:
1. Least-privilege permission validation (read-only bounds, allowed operations, allowed entities).
2. Rate limiting (sliding window per-connection rate controls).
3. Configurable timeouts and exponential backoff retries on transient faults.
4. Error reporting and telemetry tracking (consecutive failures, status degradation).
"""

import time
from typing import Dict, Any, List, Optional, Callable
from collections import defaultdict, deque
import threading


class ConnectionDisabledError(Exception):
    """Raised when an operation is attempted on a disabled enterprise connection."""
    pass


class PermissionDeniedError(Exception):
    """Raised when an operation violates least-privilege enterprise boundary policies."""
    pass


class RateLimitExceededError(Exception):
    """Raised when request rate exceeds configured thresholds."""
    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


class ConnectionTimeoutError(Exception):
    """Raised when a connector request exceeds configured SLA timeout."""
    pass


class ConnectionRateLimiter:
    """
    Sliding window per-connection rate limiter.
    Ensures AVENTRA adheres to enterprise API quotas and avoids service throttling.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._history = defaultdict(deque)

    def check_and_consume(self, connection_id: str, max_per_minute: int = 60) -> None:
        if max_per_minute <= 0:
            return

        now = time.time()
        window_start = now - 60.0

        with self._lock:
            q = self._history[connection_id]
            # Prune events older than 60s
            while q and q[0] < window_start:
                q.popleft()

            if len(q) >= max_per_minute:
                oldest = q[0]
                retry_after = max(0.1, round(60.0 - (now - oldest), 2))
                raise RateLimitExceededError(
                    f"Rate limit exceeded for connection '{connection_id}'. Limit: {max_per_minute} req/min.",
                    retry_after=retry_after
                )

            q.append(now)

    def reset(self, connection_id: str):
        with self._lock:
            if connection_id in self._history:
                self._history[connection_id].clear()


# Global rate limiter instance
_global_rate_limiter = ConnectionRateLimiter()


class LeastPrivilegeValidator:
    """
    Validates least-privilege security boundaries prior to executing any connector action.
    """
    WRITE_OPERATIONS = {"CREATE", "CREATE_RECORD", "UPDATE", "UPDATE_RECORD", "DELETE", "WRITE", "INSERT"}

    @classmethod
    def validate(
        cls,
        connection: Any,
        operation: str,
        entity: Optional[str] = None
    ) -> None:
        # 1. State check
        if hasattr(connection, "is_enabled") and not connection.is_enabled:
            raise ConnectionDisabledError(
                f"Connection '{connection.name}' (ID: {connection.id}) is disabled by administrator."
            )

        op_upper = operation.upper()

        # 2. Read-only constraint
        if getattr(connection, "read_only", False) and op_upper in cls.WRITE_OPERATIONS:
            raise PermissionDeniedError(
                f"Access Denied: Connection '{connection.name}' is strictly READ-ONLY. "
                f"Attempted write operation '{operation}' is blocked by least-privilege policy."
            )

        # 3. Allowed operations policy
        allowed_ops = getattr(connection, "allowed_operations", None)
        if allowed_ops and isinstance(allowed_ops, list) and len(allowed_ops) > 0:
            allowed_upper = [o.upper() for o in allowed_ops]
            if op_upper not in allowed_upper:
                raise PermissionDeniedError(
                    f"Access Denied: Operation '{operation}' is not in the allowed operations list "
                    f"for connection '{connection.name}'. Allowed: {allowed_ops}"
                )

        # 4. Allowed entities boundary
        allowed_entities = getattr(connection, "allowed_entities", None)
        if entity and allowed_entities and isinstance(allowed_entities, list) and len(allowed_entities) > 0:
            entity_lower = entity.lower()
            allowed_lower = [e.lower() for e in allowed_entities]
            if entity_lower not in allowed_lower:
                raise PermissionDeniedError(
                    f"Access Denied: Entity '{entity}' is outside the authorized data perimeter "
                    f"for connection '{connection.name}'. Allowed entities: {allowed_entities}"
                )


def execute_with_resilience(
    connection: Any,
    operation: str,
    func: Callable[..., Any],
    *args,
    entity: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Executes a connector operation wrapped in least-privilege checks,
    sliding-window rate limiting, SLA timeout constraints, and retry backoff.
    """
    # Step 1: Least-privilege validation
    LeastPrivilegeValidator.validate(connection, operation, entity=entity)

    # Step 2: Rate limit verification
    config = getattr(connection, "config", {}) or {}
    rate_limit = config.get("rate_limit_per_minute", 60)
    conn_id = getattr(connection, "id", "default")
    _global_rate_limiter.check_and_consume(conn_id, rate_limit)

    # Step 3: Execution with retries and timeout
    timeout_sec = config.get("timeout_seconds", 10)
    max_retries = max(1, config.get("max_retries", 3))

    last_exception = None
    delay = 0.05

    for attempt in range(1, max_retries + 1):
        try:
            t0 = time.time()
            res = func(*args, **kwargs)
            duration = time.time() - t0

            if duration > timeout_sec:
                raise ConnectionTimeoutError(
                    f"Operation '{operation}' on connection '{conn_id}' exceeded timeout SLA ({duration:.2f}s > {timeout_sec}s)."
                )

            # Record success metric if tracking
            if hasattr(connection, "metrics") and isinstance(connection.metrics, dict):
                connection.metrics["total_requests"] = connection.metrics.get("total_requests", 0) + 1
                connection.metrics["successful_requests"] = connection.metrics.get("successful_requests", 0) + 1
                connection.metrics["consecutive_failures"] = 0

            return res

        except (ConnectionDisabledError, PermissionDeniedError, RateLimitExceededError):
            # Non-retryable policy or quota violations
            raise
        except Exception as e:
            last_exception = e
            if hasattr(connection, "metrics") and isinstance(connection.metrics, dict):
                connection.metrics["total_requests"] = connection.metrics.get("total_requests", 0) + 1
                connection.metrics["failed_requests"] = connection.metrics.get("failed_requests", 0) + 1
                connection.metrics["consecutive_failures"] = connection.metrics.get("consecutive_failures", 0) + 1

            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                break

    raise last_exception

