"""Prometheus metrics for BrainClaw Memory System.

Provides:
- Counters for memory operations
- Histograms for latency measurements
- Gauges for connection tracking
- Optional metrics collection (can be disabled)
"""
from typing import Optional
import os

# Check if metrics should be enabled (can be disabled for development)
_METRICS_ENABLED = os.getenv("OPENCLAW_METRICS_ENABLED", "true").lower() == "true"

# Try to import prometheus_client, with graceful fallback
try:
    from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, push_to_gateway
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    # Create no-op classes for when prometheus_client is not available
    class Counter:
        def __init__(*args, **kwargs): pass
        def labels(*args, **kwargs): return self
        def inc(*args, **kwargs): pass
    
    class Histogram:
        def __init__(*args, **kwargs): pass
        def labels(*args, **kwargs): return self
        def observe(*args, **kwargs): pass
        def time(*args, **kwargs): return lambda f: f
    
    class Gauge:
        def __init__(*args, **kwargs): pass
        def labels(*args, **kwargs): return self
        def inc(*args, **kwargs): pass
        def dec(*args, **kwargs): pass
        def set(*args, **kwargs): pass
    
    CollectorRegistry = None
    push_to_gateway = None


# Define metric labels
COMMON_LABELS = ["tenant_id", "agent_id", "operation"]


# Memory Operations Counter
# Tracks total number of memory operations by type
MEMORY_OPERATIONS = None
if _PROMETHEUS_AVAILABLE and _METRICS_ENABLED:
    try:
        MEMORY_OPERATIONS = Counter(
            "openclaw_memory_operations_total",
            "Total number of memory operations",
            ["operation", "memory_class", "status", "tenant_id"]
        )
    except ValueError:
        # Already registered, likely in a test environment
        from prometheus_client import REGISTRY
        MEMORY_OPERATIONS = REGISTRY._names_to_collectors.get("openclaw_memory_operations_total") or \
                           REGISTRY._names_to_collectors.get("openclaw_memory_operations")


# Latency Histogram
# Tracks latency for database and search operations
LATENCY_SECONDS = None
if _PROMETHEUS_AVAILABLE and _METRICS_ENABLED:
    try:
        LATENCY_SECONDS = Histogram(
            "openclaw_operation_latency_seconds",
            "Operation latency in seconds",
            ["operation", "component"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
    except ValueError:
        from prometheus_client import REGISTRY
        LATENCY_SECONDS = REGISTRY._names_to_collectors.get("openclaw_operation_latency_seconds")


# Active Connections Gauge
# Tracks number of active connections to storage backends
ACTIVE_CONNECTIONS = None
if _PROMETHEUS_AVAILABLE and _METRICS_ENABLED:
    try:
        ACTIVE_CONNECTIONS = Gauge(
            "openclaw_active_connections",
            "Number of active connections",
            ["backend", "tenant_id"]
        )
    except ValueError:
        from prometheus_client import REGISTRY
        ACTIVE_CONNECTIONS = REGISTRY._names_to_collectors.get("openclaw_active_connections")


# Embedding Latency Histogram
# Tracks latency for embedding generation
EMBEDDING_LATENCY = None
if _PROMETHEUS_AVAILABLE and _METRICS_ENABLED:
    try:
        EMBEDDING_LATENCY = Histogram(
            "openclaw_embedding_latency_seconds",
            "Embedding generation latency in seconds",
            ["model", "text_length_bucket"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
    except ValueError:
        from prometheus_client import REGISTRY
        EMBEDDING_LATENCY = REGISTRY._names_to_collectors.get("openclaw_embedding_latency_seconds")


# RRF Fusion Metrics
RRF_RESULTS = None
RRF_LATENCY = None
if _PROMETHEUS_AVAILABLE and _METRICS_ENABLED:
    try:
        RRF_RESULTS = Histogram(
            "openclaw_rrf_results",
            "Number of results from RRF fusion",
            ["k_param"],
            buckets=[1, 5, 10, 25, 50, 100, 250, 500]
        )
        RRF_LATENCY = Histogram(
            "openclaw_rrf_latency_seconds",
            "RRF fusion latency in seconds",
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
        )
    except ValueError:
        from prometheus_client import REGISTRY
        RRF_RESULTS = REGISTRY._names_to_collectors.get("openclaw_rrf_results")
        RRF_LATENCY = REGISTRY._names_to_collectors.get("openclaw_rrf_latency_seconds")


# Ingestion Metrics
INGESTION_ITEMS = None
INGESTION_LATENCY = None
if _PROMETHEUS_AVAILABLE and _METRICS_ENABLED:
    try:
        INGESTION_ITEMS = Counter(
            "openclaw_ingestion_items_total",
            "Total items ingested",
            ["memory_class", "tenant_id", "status"]
        )
        INGESTION_LATENCY = Histogram(
            "openclaw_ingestion_latency_seconds",
            "Ingestion pipeline latency in seconds",
            ["stage"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
        )
    except ValueError:
        from prometheus_client import REGISTRY
        INGESTION_ITEMS = REGISTRY._names_to_collectors.get("openclaw_ingestion_items_total")
        INGESTION_LATENCY = REGISTRY._names_to_collectors.get("openclaw_ingestion_latency_seconds")


# Cache Metrics (if applicable)
CACHE_HITS = None
CACHE_MISSES = None
if _PROMETHEUS_AVAILABLE and _METRICS_ENABLED:
    try:
        CACHE_HITS = Counter(
            "openclaw_cache_hits_total",
            "Total cache hits",
            ["cache_name"]
        )
        CACHE_MISSES = Counter(
            "openclaw_cache_misses_total",
            "Total cache misses",
            ["cache_name"]
        )
    except ValueError:
        from prometheus_client import REGISTRY
        CACHE_HITS = REGISTRY._names_to_collectors.get("openclaw_cache_hits_total")
        CACHE_MISSES = REGISTRY._names_to_collectors.get("openclaw_cache_misses_total")


# Observable flag for checking if metrics are enabled
OBSERVABLE_ENABLED = _PROMETHEUS_AVAILABLE and _METRICS_ENABLED


class MetricsHelper:
    """Helper class for recording metrics.
    
    Provides convenient methods for recording metrics with appropriate labels.
    """
    
    @staticmethod
    def record_memory_operation(
        operation: str,
        memory_class: str = "unknown",
        status: str = "success",
        tenant_id: str = "default",
    ) -> None:
        """Record a memory operation.
        
        Args:
            operation: Type of operation (insert, search, update, delete)
            memory_class: Memory class (episodic, semantic, etc.)
            status: Operation status (success, error)
            tenant_id: Tenant identifier
        """
        if MEMORY_OPERATIONS:
            try:
                MEMORY_OPERATIONS.labels(
                    operation=operation,
                    memory_class=memory_class,
                    status=status,
                    tenant_id=tenant_id,
                ).inc()
            except Exception:
                pass  # Best effort
    
    @staticmethod
    def record_latency(
        operation: str,
        component: str,
        duration_seconds: float,
    ) -> None:
        """Record operation latency.
        
        Args:
            operation: Operation type
            component: Component name (postgres, weaviate, neo4j)
            duration_seconds: Duration in seconds
        """
        if LATENCY_SECONDS:
            try:
                LATENCY_SECONDS.labels(
                    operation=operation,
                    component=component,
                ).observe(duration_seconds)
            except Exception:
                pass
    
    @staticmethod
    def set_connections(backend: str, count: int, tenant_id: str = "default") -> None:
        """Set active connection count.
        
        Args:
            backend: Backend name (postgres, weaviate, neo4j)
            count: Number of active connections
            tenant_id: Tenant identifier
        """
        if ACTIVE_CONNECTIONS:
            try:
                ACTIVE_CONNECTIONS.labels(
                    backend=backend,
                    tenant_id=tenant_id,
                ).set(count)
            except Exception:
                pass
    
    @staticmethod
    def record_embedding_latency(
        model: str,
        text_length: int,
        duration_seconds: float,
    ) -> None:
        """Record embedding generation latency.
        
        Args:
            model: Embedding model name
            text_length: Length of input text
            duration_seconds: Duration in seconds
        """
        if EMBEDDING_LATENCY:
            try:
                # Bucket text length
                length_bucket = "short"
                if text_length > 100:
                    length_bucket = "medium"
                if text_length > 500:
                    length_bucket = "long"
                if text_length > 1000:
                    length_bucket = "very_long"
                
                EMBEDDING_LATENCY.labels(
                    model=model,
                    text_length_bucket=length_bucket,
                ).observe(duration_seconds)
            except Exception:
                pass
    
    @staticmethod
    def record_rrf_results(count: int, k_param: int = 60) -> None:
        """Record RRF fusion result count.
        
        Args:
            count: Number of results
            k_param: RRF k parameter used
        """
        if RRF_RESULTS:
            try:
                RRF_RESULTS.labels(k_param=str(k_param)).observe(count)
            except Exception:
                pass
    
    @staticmethod
    def record_rrf_latency(duration_seconds: float) -> None:
        """Record RRF fusion latency.
        
        Args:
            duration_seconds: Duration in seconds
        """
        if RRF_LATENCY:
            try:
                RRF_LATENCY.observe(duration_seconds)
            except Exception:
                pass
    
    @staticmethod
    def record_ingestion(
        memory_class: str,
        tenant_id: str,
        status: str = "success",
    ) -> None:
        """Record ingestion item.
        
        Args:
            memory_class: Memory class
            tenant_id: Tenant identifier
            status: Status (success, error)
        """
        if INGESTION_ITEMS:
            try:
                INGESTION_ITEMS.labels(
                    memory_class=memory_class,
                    tenant_id=tenant_id,
                    status=status,
                ).inc()
            except Exception:
                pass
    
    @staticmethod
    def record_ingestion_latency(stage: str, duration_seconds: float) -> None:
        """Record ingestion stage latency.
        
        Args:
            stage: Ingestion stage (extraction, embedding, storage)
            duration_seconds: Duration in seconds
        """
        if INGESTION_LATENCY:
            try:
                INGESTION_LATENCY.labels(stage=stage).observe(duration_seconds)
            except Exception:
                pass


# Context manager for timing operations
class Timer:
    """Context manager for timing operations.
    
    Usage:
        with Timer("operation", "component") as t:
            # do work
            pass
        # t.duration is available after
    """
    
    def __init__(self, operation: str, component: str):
        self.operation = operation
        self.component = component
        self.duration: Optional[float] = None
        self._start_time: Optional[float] = None
    
    def __enter__(self):
        import time
        self._start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        self.duration = time.perf_counter() - self._start_time
        
        if self.duration is not None:
            MetricsHelper.record_latency(
                self.operation,
                self.component,
                self.duration
            )


# Decorator for automatic latency recording
def timed(operation: str, component: str):
    """Decorator to automatically record operation latency.
    
    Usage:
        @timed("query", "postgres")
        async def my_query():
            ...
    
    Args:
        operation: Operation name
        component: Component name
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            with Timer(operation, component):
                return await func(*args, **kwargs)
        return wrapper
    return decorator