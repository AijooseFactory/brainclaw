"""Initialize observability for OpenClaw Memory.

This module provides a simple interface to initialize tracing, logging,
and metrics for the entire application.

Usage:
    from openclaw_memory.observability.init import init_observability
    
    # Initialize with defaults or from config
    await init_observability()
    
    # Or with custom config
    from openclaw_memory.config import ObservabilityConfig
    config = ObservabilityConfig(enabled=True, log_level="DEBUG")
    await init_observability(config)
"""
from typing import Optional

from openclaw_memory.config import ObservabilityConfig


async def init_observability(
    config: Optional[ObservabilityConfig] = None,
) -> None:
    """Initialize observability infrastructure.
    
    Args:
        config: ObservabilityConfig. If not provided, loads from environment.
    """
    if config is None:
        config = ObservabilityConfig.from_env()
    
    # Import here to avoid circular imports
    from openclaw_memory.observability.telemetry import TelemetryManager
    from openclaw_memory.observability.logging import configure_logging
    from openclaw_memory.observability import metrics as metrics_module
    
    # Always configure logging (even if observability is disabled)
    configure_logging(
        service_name="openclaw-memory",
        level=config.log_level,
        log_format=config.log_format,
    )
    
    # Initialize telemetry if enabled
    if config.enabled:
        tm = TelemetryManager(
            service_name="openclaw-memory",
            otlp_endpoint=config.otlp_endpoint,
            use_http=config.otlp_use_http,
            enabled=config.enabled,
        )
        await tm.initialize()
    
    # Disable metrics if not enabled in config
    if not config.metrics_enabled:
        metrics_module._METRICS_ENABLED = False


__all__ = ["init_observability", "ObservabilityConfig"]