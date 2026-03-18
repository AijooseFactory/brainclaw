"""Structured JSON logging for BrainClaw.

Provides:
- JSON output for log aggregators (Grafana Loki, ELK)
- Correlation IDs (trace_id, span_id) for tracing correlation
- Configurable log levels and formats
"""
import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from contextvars import ContextVar
from functools import wraps

import structlog
from structlog.types import EventDict, Processor
from structlog.stdlib import LoggerFactory

# Python version detection for structlog compatibility
_python_version = sys.version_info

# Context variables for correlation IDs
_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_span_id_var: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
_tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

# Structlog contextvars merge function - with fallback for older versions
try:
    # structlog 24+ uses merge_contextvars from contextvars module
    if hasattr(structlog.contextvars, 'merge_contextvars'):
        _structlog_merge_contextvars = structlog.contextvars.merge_contextvars
    else:
        # Fallback for older structlog versions that don't have contextvars support
        def _structlog_merge_contextvars(
            logger: Any, method_name: str, event_dict: EventDict
        ) -> EventDict:
            """Fallback context merge that just returns event_dict unchanged."""
            return event_dict
except (ImportError, AttributeError):
    # If contextvars module doesn't exist in structlog
    def _structlog_merge_contextvars(
        logger: Any, method_name: str, event_dict: EventDict
    ) -> EventDict:
        """Fallback context merge that just returns event_dict unchanged."""
        return event_dict

# Global service name
_service_name = "openclaw-memory"
_log_level = "INFO"
_log_format = "json"
_configured = False


def _add_timestamp(
    logger: Any, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add ISO timestamp to log event."""
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    return event_dict


def _add_service_name(
    logger: Any, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add service name to log event."""
    event_dict["service"] = _service_name
    return event_dict


def _add_correlation_ids(
    logger: Any, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add trace_id and span_id for correlation with traces."""
    trace_id = _trace_id_var.get()
    if trace_id:
        event_dict["trace_id"] = trace_id
    
    span_id = _span_id_var.get()
    if span_id:
        event_dict["span_id"] = span_id
    
    tenant_id = _tenant_id_var.get()
    if tenant_id:
        event_dict["tenant_id"] = tenant_id
    
    return event_dict


def _convert_log_level(
    logger: Any, method_name: str, event_dict: EventDict
) -> EventDict:
    """Convert structlog method name to standard log level."""
    level_map = {
        "debug": "DEBUG",
        "info": "INFO",
        "warning": "WARNING",
        "error": "ERROR",
        "exception": "ERROR",
        "critical": "CRITICAL",
    }
    event_dict["level"] = level_map.get(method_name, "INFO")
    return event_dict


def _rename_event_to_message(
    logger: Any, method_name: str, event_dict: EventDict
) -> EventDict:
    """Rename 'event' to 'message' for standard compatibility."""
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _json_serializer(
    logger: Any, method_name: str, event_dict: EventDict
) -> str:
    """Serialize log event as JSON string."""
    # Ensure all values are JSON serializable
    serializable_dict = {}
    for key, value in event_dict.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            serializable_dict[key] = value
        elif isinstance(value, dict):
            serializable_dict[key] = _make_serializable(value)
        elif isinstance(value, (list, tuple)):
            serializable_dict[key] = [
                _make_serializable(v) if isinstance(v, (dict, list, tuple)) else v
                for v in value
            ]
        else:
            serializable_dict[key] = str(value)
    
    return json.dumps(serializable_dict)


def _make_serializable(obj: Any) -> Any:
    """Make object JSON serializable."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)


def configure_logging(
    service_name: str = "openclaw-memory",
    level: str = "INFO",
    log_format: str = "json",
) -> None:
    """Configure structlog with JSON output.
    
    Args:
        service_name: Name of the service for logging
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ("json" or "console")
    """
    global _service_name, _log_level, _log_format, _configured
    
    _service_name = service_name
    _log_level = level
    _log_format = log_format
    
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add stdout handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(handler)
    
    # Configure processors based on format
    processors = [
        _structlog_merge_contextvars,
        _add_timestamp,
        _add_service_name,
        _add_correlation_ids,
        _convert_log_level,
        _rename_event_to_message,
    ]
    
    if log_format == "json":
        processors.append(_json_serializer)
    else:
        # Console format - add more readable formatting
        processors.append(
            structlog.dev.ConsoleRenderer()
        )
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    _configured = True


def get_logger(name: str) -> structlog.BoundLogger:
    """Return configured logger.
    
    Args:
        name: Logger name (usually module name)
        
    Returns:
        Configured structlog bound logger
    """
    global _configured
    
    # Auto-configure if not configured
    if not _configured:
        configure_logging()
    
    return structlog.get_logger(name)


def set_trace_context(
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """Set correlation context for logging.
    
    Args:
        trace_id: Trace ID for correlation
        span_id: Span ID for correlation
        tenant_id: Tenant ID for multi-tenant filtering
    """
    if trace_id:
        _trace_id_var.set(trace_id)
    if span_id:
        _span_id_var.set(span_id)
    if tenant_id:
        _tenant_id_var.set(tenant_id)


def clear_trace_context() -> None:
    """Clear trace correlation context."""
    _trace_id_var.set(None)
    _span_id_var.set(None)
    _tenant_id_var.set(None)


def get_trace_context() -> Dict[str, Optional[str]]:
    """Get current trace context.
    
    Returns:
        Dictionary with trace_id, span_id, tenant_id
    """
    return {
        "trace_id": _trace_id_var.get(),
        "span_id": _span_id_var.get(),
        "tenant_id": _tenant_id_var.get(),
    }


# Decorator for automatic trace context in async functions
def logged_async(operation_name: str):
    """Decorator to add logging to async functions.
    
    Automatically adds operation name and captures exceptions.
    
    Usage:
        @logged_async("postgres.query")
        async def my_function():
            ...
    
    Args:
        operation_name: Name of the operation for logging
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            logger = logger.bind(operation=operation_name)
            
            try:
                logger.info("started")
                result = await func(*args, **kwargs)
                logger.info("completed")
                return result
            except Exception as e:
                logger.error("failed", error=str(e), error_type=type(e).__name__)
                raise
        
        return wrapper
    return decorator


def logged_sync(operation_name: str):
    """Decorator to add logging to sync functions.
    
    Automatically adds operation name and captures exceptions.
    
    Usage:
        @logged_sync("weaviate.search")
        def my_function():
            ...
    
    Args:
        operation_name: Name of the operation for logging
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            logger = logger.bind(operation=operation_name)
            
            try:
                logger.info("started")
                result = func(*args, **kwargs)
                logger.info("completed")
                return result
            except Exception as e:
                logger.error("failed", error=str(e), error_type=type(e).__name__)
                raise
        
        return wrapper
    return decorator


class LoggerAdapter:
    """Adapter to add context to logger calls.
    
    Usage:
        logger = LoggerAdapter("module")
        logger = logger.bind(tenant_id="abc", user_id="123")
        logger.info("message", extra_key="value")
    """
    
    def __init__(self, name: str, **context):
        self._logger = get_logger(name)
        self._context = context
    
    def bind(self, **kwargs) -> "LoggerAdapter":
        """Add more context to the adapter."""
        new_ctx = {**self._context, **kwargs}
        return LoggerAdapter(self._logger.name, **new_ctx)
    
    def _log(self, level: str, msg: str, **kwargs):
        context = {**self._context, **kwargs}
        getattr(self._logger, level)(msg, **context)
    
    def debug(self, msg: str, **kwargs):
        self._log("debug", msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        self._log("info", msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self._log("warning", msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        self._log("error", msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        self._log("critical", msg, **kwargs)
    
    def exception(self, msg: str, **kwargs):
        self._log("exception", msg, **kwargs)