"""Observability module for BrainClaw Memory System.

Provides:
- OpenTelemetry tracing for distributed request tracking
- Structured JSON logging with correlation IDs
- Prometheus metrics for monitoring

Quick Start:
    from openclaw_memory.observability.init import init_observability
    await init_observability()  # Initialize all observability

    from openclaw_memory.observability import get_logger
    logger = get_logger(__name__)
    logger.info("Hello structured world!")
"""
# Make imports optional with graceful degradation
try:
    from .telemetry import TelemetryManager
except ImportError:
    TelemetryManager = None

try:
    from .logging import configure_logging, get_logger, set_trace_context
except ImportError as e:
    raise ImportError(f"Failed to import logging: {e}")

try:
    from .metrics import (
        MEMORY_OPERATIONS,
        LATENCY_SECONDS,
        ACTIVE_CONNECTIONS,
        EMBEDDING_LATENCY,
        OBSERVABLE_ENABLED,
        MetricsHelper,
        Timer,
    )
except ImportError:
    MEMORY_OPERATIONS = None
    LATENCY_SECONDS = None
    ACTIVE_CONNECTIONS = None
    EMBEDDING_LATENCY = None
    OBSERVABLE_ENABLED = None
    MetricsHelper = None
    Timer = None

__all__ = [
    "TelemetryManager",
    "configure_logging",
    "get_logger",
    "set_trace_context",
    "MEMORY_OPERATIONS",
    "LATENCY_SECONDS",
    "ACTIVE_CONNECTIONS",
    "EMBEDDING_LATENCY",
    "OBSERVABLE_ENABLED",
    "MetricsHelper",
    "Timer",
    # Init
    "init_observability",
]

# Lazy import for init to avoid circular dependency
def __getattr__(name):
    if name == "init_observability":
        try:
            from .init import init_observability
            return init_observability
        except ImportError:
            def _dummy_init(*args, **kwargs):
                raise ImportError("init_observability requires opentelemetry package")
            return _dummy_init
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")