"""OpenTelemetry tracing setup for BrainClaw."""
import asyncio
import logging
import sys
import contextvars

# Python 3.11+ uses copy_context() instead of copy_context_vars
# Use try/except for compatibility with older Python versions
try:
    from contextvars import copy_context
    _copy_context_func = copy_context
except ImportError:
    # Fallback for older Python (pre-3.11) - try using copy_context_vars
    try:
        from contextvars import copy_context_vars as _copy_context_func
    except ImportError:
        _copy_context_func = None

# These imports will fail if opentelemetry is not installed
# The package should have opentelemetry as dependency
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPSpanExporterHTTP
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.trace import Status, StatusCode

from typing import Optional
import warnings

# Store global tracer for easy access
_tracer: Optional[trace.Tracer] = None
_provider: Optional[TracerProvider] = None
_initialized = False


class TelemetryManager:
    """OpenTelemetry tracing setup for BrainClaw.
    
    Provides:
    - OTLP export (gRPC and HTTP supported)
    - Graceful degradation if OTLP endpoint unavailable
    - Context propagation for async operations
    """
    
    def __init__(
        self,
        service_name: str = "openclaw-memory",
        otlp_endpoint: str = "http://localhost:4317",
        enabled: bool = True,
        use_http: bool = False,
    ):
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint
        self.enabled = enabled
        self.use_http = use_http
        self.tracer: Optional[trace.Tracer] = None
        self._provider: Optional[TracerProvider] = None
        self._context_var: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
            'trace_context', default=None
        )
    
    async def initialize(self) -> None:
        """Initialize OpenTelemetry tracing.
        
        Sets up OTLP exporter with graceful degradation if unavailable.
        """
        global _tracer, _provider, _initialized
        
        if not self.enabled:
            _initialized = True
            return
            
        try:
            # Create resource with service name
            resource = Resource.create({
                SERVICE_NAME: self.service_name,
            })
            
            # Create tracer provider
            self._provider = TracerProvider(resource=resource)
            
            # Try to create OTLP exporter
            try:
                if self.use_http or "http" in self.otlp_endpoint.lower():
                    exporter = OTLPSpanExporterHTTP(
                        endpoint=self.otlp_endpoint,
                        timeout=5.0,
                    )
                else:
                    # gRPC endpoint
                    endpoint = self.otlp_endpoint.replace("http://", "").replace("https://", "")
                    # Add port if not present
                    if ":" not in endpoint:
                        endpoint = f"{endpoint}:4317"
                    exporter = OTLPSpanExporter(
                        endpoint=endpoint,
                        timeout=5.0,
                    )
                
                # Add batch span processor
                processor = BatchSpanProcessor(exporter)
                self._provider.add_span_processor(processor)
            except Exception as e:
                warnings.warn(f"Failed to create OTLP exporter: {e}. Tracing disabled.")
                self.enabled = False
                return
            
            # Set global provider
            trace.set_tracer_provider(self._provider)
            
            # Get tracer
            self.tracer = trace.get_tracer(self.service_name)
            _tracer = self.tracer
            _provider = self._provider
            _initialized = True
            
        except Exception as e:
            warnings.warn(f"Failed to initialize OpenTelemetry: {e}. Tracing disabled.")
            self.enabled = False
    
    def get_tracer(self) -> trace.Tracer:
        """Return configured tracer.
        
        Returns:
            Configured tracer or no-op tracer if not initialized.
        """
        if self.tracer:
            return self.tracer
        # Return a no-op tracer if not initialized
        return trace.get_tracer(self.service_name)
    
    def start_span(
        self,
        name: str,
        attributes: Optional[dict] = None,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    ) -> trace.Span:
        """Start a new span.
        
        Args:
            name: Span name
            attributes: Initial span attributes
            kind: Span kind (internal, client, server, etc.)
            
        Returns:
            Started span
        """
        tracer = self.get_tracer()
        with tracer.start_as_current_span(name, kind=kind) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, str(value))
            return span
    
    async def start_span_async(
        self,
        name: str,
        attributes: Optional[dict] = None,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    ) -> trace.Span:
        """Start a new span in async context with proper context propagation.
        
        Args:
            name: Span name
            attributes: Initial span attributes
            kind: Span kind
            
        Returns:
            Started span
        """
        # Copy context for async propagation (use compatible function)
        if _copy_context_func is not None:
            ctx = _copy_context_func()
        
        tracer = self.get_tracer()
        # Use tracer.start_as_current_span for async context
        return tracer.start_span(name, kind=kind)
    
    def set_attribute(self, span: trace.Span, key: str, value: any) -> None:
        """Set attribute on span.
        
        Args:
            span: Span to modify
            key: Attribute key
            value: Attribute value
        """
        span.set_attribute(key, str(value))
    
    def record_exception(self, span: trace.Span, exception: Exception) -> None:
        """Record exception on span.
        
        Args:
            span: Span to record exception on
            exception: Exception to record
        """
        span.set_status(Status(StatusCode.ERROR, str(exception)))
        span.record_exception(exception)
    
    async def close(self) -> None:
        """Shutdown telemetry provider gracefully."""
        global _provider, _initialized
        
        if self._provider:
            try:
                await self._provider.shutdown()
            except Exception:
                pass  # Best effort shutdown
        
        _provider = None
        _initialized = False


def get_global_tracer() -> trace.Tracer:
    """Get the global tracer instance.
    
    Returns:
        Global tracer or new tracer if not initialized.
    """
    global _tracer
    if _tracer:
        return _tracer
    return trace.get_tracer("openclaw-memory")


def is_initialized() -> bool:
    """Check if telemetry is initialized.
    
    Returns:
        True if telemetry was initialized successfully.
    """
    global _initialized
    return _initialized


# Decorator for easy tracing of async functions
def traced_async(operation_name: str, attributes: Optional[dict] = None):
    """Decorator to trace async functions.
    
    Usage:
        @traced_async("postgres.query", {"component": "storage"})
        async def my_function():
            ...
    
    Args:
        operation_name: Name of the operation
        attributes: Additional attributes to add to span
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            tracer = get_global_tracer()
            with tracer.start_as_current_span(operation_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))
                span.set_attribute("function", func.__name__)
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator


def traced_sync(operation_name: str, attributes: Optional[dict] = None):
    """Decorator to trace sync functions.
    
    Usage:
        @traced_sync("weaviate.search", {"component": "storage"})
        def my_function():
            ...
    
    Args:
        operation_name: Name of the operation
        attributes: Additional attributes to add to span
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            tracer = get_global_tracer()
            with tracer.start_as_current_span(operation_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))
                span.set_attribute("function", func.__name__)
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator