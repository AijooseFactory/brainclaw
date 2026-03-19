"""Sync error handling, rollback, and retry policy for BrainClaw.

FR-026: Ingestion and sync must be rollback-safe and failure-aware.

Required behavior:
  - Failed imports must not commit partially promoted durable memory
  - Failed derived index writes must not corrupt canonical records
  - Failed bootstrap operations must support restart from last valid checkpoint
  - Invalid artifacts must be quarantined or marked failed
  - Retry/backoff policy must be explicit
  - Dead-letter handling for repeated failures
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time


class SyncFailureType(Enum):
    VALIDATION_FAILURE = "validation_failure"
    EXTRACTION_FAILURE = "extraction_failure"
    PROMOTION_FAILURE = "promotion_failure"
    CANONICAL_WRITE_FAILURE = "canonical_write_failure"
    DERIVED_INDEX_FAILURE = "derived_index_failure"
    CHECKPOINT_FAILURE = "checkpoint_failure"
    BOOTSTRAP_FAILURE = "bootstrap_failure"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class RetryPolicy:
    """Configurable retry/backoff policy for sync operations."""

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt (0-indexed)."""
        delay = self.base_delay_seconds * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay_seconds)
        if self.jitter:
            import random
            delay = delay * (0.5 + random.random() * 0.5)
        return delay


@dataclass
class SyncFailureRecord:
    """Record of a sync failure for operational visibility."""

    failure_type: SyncFailureType
    artifact_id: Optional[str] = None
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    recoverable: bool = True
    quarantined: bool = False
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TransactionalSyncContext:
    """Context manager for rollback-safe sync operations.

    Ensures that if any step in the promotion pipeline fails, partial
    writes are rolled back and failure state is recorded.

    Usage:
        with TransactionalSyncContext(repository) as ctx:
            ctx.import_artifact(artifact)
            ctx.extract_candidates(candidates)
            ctx.promote_candidates(promoted)
            # If any step fails, ctx.rollback() is called automatically
    """

    def __init__(self, repository: Any):
        self._repository = repository
        self._imported_artifact_ids: List[str] = []
        self._promoted_memory_ids: List[str] = []
        self._backfill_marks: List[tuple] = []
        self._committed = False
        self._failures: List[SyncFailureRecord] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and not self._committed:
            self.rollback(
                reason=f"{exc_type.__name__}: {exc_val}" if exc_val else "Unknown error"
            )
        return False  # Don't suppress exceptions

    def record_artifact(self, artifact_id: str) -> None:
        """Track an imported artifact for potential rollback."""
        self._imported_artifact_ids.append(artifact_id)

    def record_promotion(self, memory_item_id: str) -> None:
        """Track a promoted memory item for potential rollback."""
        self._promoted_memory_ids.append(memory_item_id)

    def record_backfill(self, memory_item_id: str, target: str) -> None:
        """Track a backfill mark for potential rollback."""
        self._backfill_marks.append((memory_item_id, target))

    def record_failure(self, failure: SyncFailureRecord) -> None:
        """Record a failure within this transaction."""
        self._failures.append(failure)

    def commit(self) -> None:
        """Mark the transaction as committed (no rollback needed)."""
        self._committed = True

    def rollback(self, reason: str = "") -> None:
        """Roll back all tracked operations.

        In practice this marks artifacts as failed and prevents partial
        promotion from persisting. For PostgreSQL, actual transaction
        rollback happens at the connection/cursor level.
        """
        for artifact_id in self._imported_artifact_ids:
            try:
                if hasattr(self._repository, "mark_artifact_failed"):
                    self._repository.mark_artifact_failed(artifact_id, reason)
            except Exception:
                pass  # Best-effort rollback

        for memory_id in self._promoted_memory_ids:
            try:
                if hasattr(self._repository, "mark_memory_rolled_back"):
                    self._repository.mark_memory_rolled_back(memory_id, reason)
            except Exception:
                pass

        self._failures.append(
            SyncFailureRecord(
                failure_type=SyncFailureType.CANONICAL_WRITE_FAILURE,
                error_message=f"Rollback triggered: {reason}",
                timestamp=_utcnow(),
            )
        )

    @property
    def failures(self) -> List[SyncFailureRecord]:
        return list(self._failures)

    @property
    def has_failures(self) -> bool:
        return len(self._failures) > 0


def retry_with_backoff(
    func: Callable,
    policy: Optional[RetryPolicy] = None,
    on_failure: Optional[Callable[[Exception, int], None]] = None,
) -> Any:
    """Execute a function with retry and exponential backoff.

    Args:
        func: Callable to execute
        policy: Retry policy (defaults to standard policy)
        on_failure: Optional callback on each failure (exception, attempt)

    Returns:
        Result of func()

    Raises:
        Last exception if all retries exhausted
    """
    if policy is None:
        policy = RetryPolicy()

    last_exception = None
    for attempt in range(policy.max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_exception = e
            if on_failure:
                on_failure(e, attempt)
            if attempt < policy.max_retries:
                delay = policy.delay_for_attempt(attempt)
                time.sleep(delay)

    raise last_exception  # type: ignore[misc]
