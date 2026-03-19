"""LCM-specific Prometheus metrics for BrainClaw integration.

FR-024: BrainClaw must expose integration observability for Lossless-Claw.

Required metrics:
  - lcm_sync_lag_seconds
  - lcm_compaction_duration_seconds
  - lcm_db_size_bytes
  - lcm_dag_integrity_violations_total
  - promotion_success_rate
  - drill_down_invocation_count
  - brainclaw_import_failures_total
  - brainclaw_checkpoint_replay_total
"""

from __future__ import annotations

import os
from typing import Optional

# Try to import prometheus_client, with graceful fallback
try:
    from prometheus_client import Counter, Histogram, Gauge
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

_METRICS_ENABLED = os.getenv("OPENCLAW_METRICS_ENABLED", "true").lower() == "true"


def _safe_register(metric_class, name, description, labels=None, **kwargs):
    """Safely register a Prometheus metric, handling duplicates."""
    if not _PROMETHEUS_AVAILABLE or not _METRICS_ENABLED:
        return None
    try:
        return metric_class(name, description, labels or [], **kwargs)
    except (ValueError, TypeError):
        try:
            from prometheus_client import REGISTRY
            return REGISTRY._names_to_collectors.get(name)
        except Exception:
            return None


# --- FR-024 LCM Integration Metrics ---

LCM_SYNC_LAG = _safe_register(
    Gauge if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_lcm_sync_lag_seconds",
    "Lag between latest LCM compaction and BrainClaw import",
    ["source_plugin"],
) if _PROMETHEUS_AVAILABLE else None

LCM_COMPACTION_DURATION = _safe_register(
    Histogram if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_lcm_compaction_duration_seconds",
    "Duration of LCM compaction processing",
    ["mode"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
) if _PROMETHEUS_AVAILABLE else None

LCM_DB_SIZE = _safe_register(
    Gauge if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_lcm_db_size_bytes",
    "Size of the LCM SQLite database in bytes",
) if _PROMETHEUS_AVAILABLE else None

LCM_DAG_VIOLATIONS = _safe_register(
    Counter if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_lcm_dag_integrity_violations_total",
    "Total DAG integrity violations detected",
    ["violation_type"],
) if _PROMETHEUS_AVAILABLE else None

PROMOTION_SUCCESS = _safe_register(
    Counter if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_promotion_success_total",
    "Total successful promotions from LCM-derived candidates",
    ["candidate_type"],
) if _PROMETHEUS_AVAILABLE else None

PROMOTION_BLOCKED = _safe_register(
    Counter if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_promotion_blocked_total",
    "Total blocked promotions from LCM-derived candidates",
    ["candidate_type", "reason_code"],
) if _PROMETHEUS_AVAILABLE else None

DRILL_DOWN_INVOCATIONS = _safe_register(
    Counter if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_drill_down_invocations_total",
    "Total drill-down invocations to Lossless-Claw",
    ["method", "success"],
) if _PROMETHEUS_AVAILABLE else None

IMPORT_FAILURES = _safe_register(
    Counter if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_import_failures_total",
    "Total import failures from LCM artifacts",
    ["failure_type"],
) if _PROMETHEUS_AVAILABLE else None

CHECKPOINT_REPLAYS = _safe_register(
    Counter if _PROMETHEUS_AVAILABLE else None,
    "brainclaw_checkpoint_replay_total",
    "Total checkpoint replays performed",
    ["mode"],
) if _PROMETHEUS_AVAILABLE else None


class LCMMetricsHelper:
    """Helper for recording LCM-specific integration metrics."""

    @staticmethod
    def record_sync_lag(lag_seconds: float, source_plugin: str = "lossless-claw") -> None:
        if LCM_SYNC_LAG:
            try:
                LCM_SYNC_LAG.labels(source_plugin=source_plugin).set(lag_seconds)
            except Exception:
                pass

    @staticmethod
    def record_compaction_duration(duration_seconds: float, mode: str = "incremental") -> None:
        if LCM_COMPACTION_DURATION:
            try:
                LCM_COMPACTION_DURATION.labels(mode=mode).observe(duration_seconds)
            except Exception:
                pass

    @staticmethod
    def record_db_size(size_bytes: int) -> None:
        if LCM_DB_SIZE:
            try:
                LCM_DB_SIZE.set(size_bytes)
            except Exception:
                pass

    @staticmethod
    def record_dag_violation(violation_type: str) -> None:
        if LCM_DAG_VIOLATIONS:
            try:
                LCM_DAG_VIOLATIONS.labels(violation_type=violation_type).inc()
            except Exception:
                pass

    @staticmethod
    def record_promotion_success(candidate_type: str) -> None:
        if PROMOTION_SUCCESS:
            try:
                PROMOTION_SUCCESS.labels(candidate_type=candidate_type).inc()
            except Exception:
                pass

    @staticmethod
    def record_promotion_blocked(candidate_type: str, reason_code: str) -> None:
        if PROMOTION_BLOCKED:
            try:
                PROMOTION_BLOCKED.labels(
                    candidate_type=candidate_type,
                    reason_code=reason_code,
                ).inc()
            except Exception:
                pass

    @staticmethod
    def record_drill_down(method: str, success: bool) -> None:
        if DRILL_DOWN_INVOCATIONS:
            try:
                DRILL_DOWN_INVOCATIONS.labels(
                    method=method,
                    success=str(success).lower(),
                ).inc()
            except Exception:
                pass

    @staticmethod
    def record_import_failure(failure_type: str) -> None:
        if IMPORT_FAILURES:
            try:
                IMPORT_FAILURES.labels(failure_type=failure_type).inc()
            except Exception:
                pass

    @staticmethod
    def record_checkpoint_replay(mode: str = "repair") -> None:
        if CHECKPOINT_REPLAYS:
            try:
                CHECKPOINT_REPLAYS.labels(mode=mode).inc()
            except Exception:
                pass

    @staticmethod
    def update_lcm_db_size_from_path(db_path: Optional[str] = None) -> None:
        """Read LCM DB file size and update metric."""
        path = db_path or os.getenv("LCM_DATABASE_PATH")
        if path and os.path.exists(path):
            try:
                size = os.path.getsize(path)
                LCMMetricsHelper.record_db_size(size)
            except OSError:
                pass
