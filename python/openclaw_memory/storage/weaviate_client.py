"""Weaviate client for semantic and hybrid search."""
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any, Dict, Generator
import json
import time
import warnings

# Observability imports (optional - graceful degradation)
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from openclaw_memory.observability.logging import get_logger
    from openclaw_memory.observability.metrics import MetricsHelper
    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False

import weaviate
from weaviate.classes.init import Auth
from weaviate.collections import Collection
from weaviate.types import UUID as WeaviateUUID

# Get logger
logger = get_logger("openclaw.storage.weaviate") if _OBSERVABILITY_AVAILABLE else None


class _FakeSpan:
    """Fake span for when tracing is not available."""
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def set_attribute(self, key, value):
        pass
    
    def set_status(self, status):
        pass
    
    def record_exception(self, exc):
        pass


# Weaviate collection schemas based on spec
MEMORY_CHUNK_SCHEMA = {
    "class": "MemoryChunk",
    "description": "Chunks of memory content with embeddings",
    "vectorIndexConfig": {
        "distance": "cosine",
        "ef": 64,
        "efConstruction": 128,
        "maxConnections": 32,
    },
    "vectorizer": "text2vec-openai",
    "moduleConfig": {
        "text2vec-openai": {
            "vectorizeClassName": False,
        }
    },
    "properties": [
        {"name": "memory_item_id", "dataType": ["uuid"]},
        {"name": "tenant_id", "dataType": ["uuid"]},
        {"name": "agent_id", "dataType": ["uuid"]},
        {"name": "memory_class", "dataType": ["text"]},
        {"name": "memory_type", "dataType": ["text"]},
        {"name": "content", "dataType": ["text"]},
        {"name": "session_id", "dataType": ["uuid"]},
        {"name": "valid_from", "dataType": ["date"]},
        {"name": "valid_to", "dataType": ["date"]},
        {"name": "confidence", "dataType": ["number"]},
        {"name": "visibility_scope", "dataType": ["text"]},
        {"name": "source_type", "dataType": ["text"]},
    ],
}

SUMMARY_SCHEMA = {
    "class": "Summary",
    "description": "Session and conversation summaries",
    "vectorIndexConfig": {
        "distance": "cosine",
    },
    "vectorizer": "text2vec-openai",
    "moduleConfig": {
        "text2vec-openai": {
            "vectorizeClassName": False,
        }
    },
    "properties": [
        {"name": "summary_id", "dataType": ["uuid"]},
        {"name": "session_id", "dataType": ["uuid"]},
        {"name": "tenant_id", "dataType": ["uuid"]},
        {"name": "agent_id", "dataType": ["uuid"]},
        {"name": "summary_type", "dataType": ["text"]},
        {"name": "content", "dataType": ["text"]},
        {"name": "token_count", "dataType": ["int"]},
        {"name": "created_at", "dataType": ["date"]},
    ],
}

ENTITY_SCHEMA = {
    "class": "Entity",
    "description": "Named entities extracted from conversations",
    "vectorIndexConfig": {
        "distance": "cosine",
    },
    "vectorizer": "text2vec-openai",
    "moduleConfig": {
        "text2vec-openai": {
            "vectorizeClassName": False,
        }
    },
    "properties": [
        {"name": "entity_id", "dataType": ["uuid"]},
        {"name": "neo4j_id", "dataType": ["text"]},
        {"name": "tenant_id", "dataType": ["uuid"]},
        {"name": "agent_id", "dataType": ["uuid"]},
        {"name": "entity_type", "dataType": ["text"]},
        {"name": "name", "dataType": ["text"]},
        {"name": "canonical_name", "dataType": ["text"]},
        {"name": "description", "dataType": ["text"]},
        {"name": "aliases", "dataType": ["text[]"]},
        {"name": "confidence", "dataType": ["number"]},
    ],
}

DECISION_SCHEMA = {
    "class": "Decision",
    "description": "Decisions with semantic search",
    "vectorIndexConfig": {
        "distance": "cosine",
    },
    "vectorizer": "text2vec-openai",
    "moduleConfig": {
        "text2vec-openai": {
            "vectorizeClassName": False,
        }
    },
    "properties": [
        {"name": "decision_id", "dataType": ["uuid"]},
        {"name": "neo4j_id", "dataType": ["text"]},
        {"name": "tenant_id", "dataType": ["uuid"]},
        {"name": "agent_id", "dataType": ["uuid"]},
        {"name": "summary", "dataType": ["text"]},
        {"name": "decision_type", "dataType": ["text"]},
        {"name": "rationale", "dataType": ["text"]},
        {"name": "alternatives", "dataType": ["text"]},
        {"name": "status", "dataType": ["text"]},
        {"name": "valid_from", "dataType": ["date"]},
        {"name": "valid_to", "dataType": ["date"]},
        {"name": "confidence", "dataType": ["number"]},
    ],
}


@dataclass
class MemoryChunk:
    """Memory chunk for Weaviate storage."""
    memory_item_id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    memory_class: str = "semantic"
    memory_type: Optional[str] = None
    content: str = ""
    session_id: Optional[uuid.UUID] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    confidence: float = 0.5
    visibility_scope: str = "tenant"
    source_type: str = "message"
    weaviate_id: Optional[str] = None
    
    def __post_init__(self):
        """Initialize IDs if not provided."""
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = uuid.UUID(current_agent_id)
            except Exception:
                pass

        # Automatically set tenant_id from the verified security context if not provided
        if self.tenant_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_tenant_id
                current_tenant_id = get_current_tenant_id()
                if current_tenant_id:
                    self.tenant_id = uuid.UUID(current_tenant_id)
            except Exception:
                pass
    
    def to_dict(self) -> dict:
        return {
            "memory_item_id": str(self.memory_item_id) if self.memory_item_id else None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "memory_class": self.memory_class,
            "memory_type": self.memory_type,
            "content": self.content,
            "session_id": str(self.session_id) if self.session_id else None,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "confidence": self.confidence,
            "visibility_scope": self.visibility_scope,
            "source_type": self.source_type,
        }


@dataclass
class Summary:
    """Summary for Weaviate storage."""
    summary_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    summary_type: str = "session"
    content: str = ""
    token_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    weaviate_id: Optional[str] = None
    
    def __post_init__(self):
        """Initialize IDs if not provided."""
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = uuid.UUID(current_agent_id)
            except Exception:
                pass

        # Automatically set tenant_id from the verified security context if not provided
        if self.tenant_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_tenant_id
                current_tenant_id = get_current_tenant_id()
                if current_tenant_id:
                    self.tenant_id = uuid.UUID(current_tenant_id)
            except Exception:
                pass
    
    def to_dict(self) -> dict:
        return {
            "summary_id": str(self.summary_id) if self.summary_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "summary_type": self.summary_type,
            "content": self.content,
            "token_count": self.token_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class Entity:
    """Entity for Weaviate storage."""
    entity_id: Optional[uuid.UUID] = None
    neo4j_id: Optional[str] = None
    tenant_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    entity_type: str = ""
    name: str = ""
    canonical_name: Optional[str] = None
    description: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    confidence: float = 0.5
    weaviate_id: Optional[str] = None
    
    def __post_init__(self):
        """Initialize IDs if not provided."""
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = uuid.UUID(current_agent_id)
            except Exception:
                pass

        # Automatically set tenant_id from the verified security context if not provided
        if self.tenant_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_tenant_id
                current_tenant_id = get_current_tenant_id()
                if current_tenant_id:
                    self.tenant_id = uuid.UUID(current_tenant_id)
            except Exception:
                pass
    
    def to_dict(self) -> dict:
        return {
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "neo4j_id": self.neo4j_id,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "entity_type": self.entity_type,
            "name": self.name,
            "canonical_name": self.canonical_name,
            "description": self.description,
            "aliases": self.aliases,
            "confidence": self.confidence,
        }


@dataclass
class Decision:
    """Decision for Weaviate storage."""
    decision_id: Optional[uuid.UUID] = None
    neo4j_id: Optional[str] = None
    tenant_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    summary: str = ""
    decision_type: str = ""
    rationale: Optional[str] = None
    alternatives: Optional[str] = None
    status: str = "active"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    confidence: float = 0.5
    weaviate_id: Optional[str] = None
    
    def __post_init__(self):
        """Initialize IDs if not provided."""
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = uuid.UUID(current_agent_id)
            except Exception:
                pass

        # Automatically set tenant_id from the verified security context if not provided
        if self.tenant_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_tenant_id
                current_tenant_id = get_current_tenant_id()
                if current_tenant_id:
                    self.tenant_id = uuid.UUID(current_tenant_id)
            except Exception:
                pass
    
    def to_dict(self) -> dict:
        return {
            "decision_id": str(self.decision_id) if self.decision_id else None,
            "neo4j_id": self.neo4j_id,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "summary": self.summary,
            "decision_type": self.decision_type,
            "rationale": self.rationale,
            "alternatives": self.alternatives,
            "status": self.status,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "confidence": self.confidence,
        }


class WeaviateClient:
    """Async Weaviate client for semantic and hybrid search.
    
    Provides:
    - Collection management (MemoryChunk, Summary, Entity, Decision)
    - Hybrid search (BM25 + vector with configurable alpha)
    - Batch import with UUID cross-references to PostgreSQL
    - Near-vector and near-text query support
    
    Uses ThreadPoolExecutor to run sync Weaviate operations without blocking
    the event loop.
    
    Alpha weight: 0.7 means 70% vector similarity, 30% BM25
    """
    
    def __init__(
        self,
        url: str = "http://localhost:8080",
        api_key: Optional[str] = None,
    ):
        self.url = url
        self.api_key = api_key
        self._client: Optional[weaviate.Client] = None
        self._pool = ThreadPoolExecutor(max_workers=4)
    
    async def connect(self) -> None:
        """Initialize Weaviate connection."""
        loop = asyncio.get_event_loop()
        self._client = await loop.run_in_executor(
            self._pool,
            self._sync_connect
        )
    
    def _sync_connect(self) -> weaviate.WeaviateClient:
        """Synchronous connect (runs in thread pool)."""
        headers = {}
        if self.api_key:
            headers["X-OpenAI-Api-Key"] = self.api_key
        
        # Parse URL to get host and port
        url = self.url
        http_secure = url.startswith("https")
        host = url.replace("http://", "").replace("https://", "").split(":")[0]
        port_str = url.rsplit(":", 1)[-1] if ":" in url.split("//", 1)[-1] else "8080"
        try:
            port = int(port_str)
        except ValueError:
            port = 8080
        
        return weaviate.connect_to_custom(
            http_host=host, http_port=port, http_secure=http_secure,
            grpc_host=host, grpc_port=50051, grpc_secure=False,
            headers=headers,
        )
    
    async def disconnect(self) -> None:
        """Close Weaviate connection."""
        if self._client:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._pool,
                self._client.close
            )
            self._client = None
        self._pool.shutdown(wait=True)
    
    async def is_connected(self) -> bool:
        """Check if connected to Weaviate."""
        if not self._client:
            return False
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._pool,
                self._client.is_ready
            )
        except Exception:
            return False
    
    async def create_collections(self) -> None:
        """Create all required collections if they don't exist."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._pool,
            self._sync_create_collections
        )
    
    def _sync_create_collections(self):
        """Synchronous create collections (runs in thread pool)."""
        schemas = [MEMORY_CHUNK_SCHEMA, SUMMARY_SCHEMA, ENTITY_SCHEMA, DECISION_SCHEMA]
        
        for schema in schemas:
            class_name = schema["class"]
            if not self._client.collections.exists(class_name):
                self._client.collections.create_from_dict(schema)
    
    async def delete_collections(self) -> None:
        """Delete all collections (for testing/reset)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._pool,
            self._sync_delete_collections
        )
    
    def _sync_delete_collections(self):
        """Synchronous delete collections (runs in thread pool)."""
        for class_name in ["MemoryChunk", "Summary", "Entity", "Decision"]:
            if self._client.collections.exists(class_name):
                self._client.collections.delete(class_name)
    
    # MemoryChunk operations
    async def insert_chunk(self, chunk: MemoryChunk) -> str:
        """Insert a memory chunk.
        
        Args:
            chunk: MemoryChunk to insert
            
        Returns:
            Weaviate ID of inserted object
        """
        data = chunk.to_dict()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._pool,
            self._sync_insert_chunk,
            data
        )
    
    def _sync_insert_chunk(self, data: dict) -> str:
        """Synchronous insert chunk (runs in thread pool)."""
        collection = self._client.collections.get("MemoryChunk")
        result = collection.data.insert(data)
        return str(result)
    
    async def insert_chunks_batch(
        self,
        chunks: List[MemoryChunk],
    ) -> List[str]:
        """Batch insert memory chunks efficiently.
        
        Args:
            chunks: List of MemoryChunks to insert
            
        Returns:
            List of Weaviate IDs
        """
        if not chunks:
            return []
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._pool,
            self._sync_insert_chunks_batch,
            chunks
        )
    
    def _sync_insert_chunks_batch(self, chunks: List[MemoryChunk]) -> List[str]:
        """Synchronous batch insert (runs in thread pool)."""
        collection = self._client.collections.get("MemoryChunk")
        
        with collection.batch.dynamic() as batch:
            for chunk in chunks:
                if chunk.memory_item_id is None:
                    chunk.memory_item_id = uuid.uuid4()
                batch.add_object(properties=chunk.to_dict())
        
        return [str(obj.uuid) for obj in collection.batch.inserted_objects]
    
    async def search_chunks_hybrid(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        memory_class: Optional[str] = None,
        tenant_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
        limit: int = 10,
        alpha: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Hybrid search on MemoryChunk collection.
        
        Combines BM25 keyword search with vector similarity.
        Alpha of 0.7 means 70% weight on vector, 30% on BM25.
        
        Args:
            query: Text query for BM25
            query_vector: Optional vector for semantic search
            memory_class: Filter by memory class
            tenant_id: Filter by tenant
            limit: Maximum results
            alpha: Weight for vector vs BM25 (0=BM25 only, 1=vector only)
            
        Returns:
            List of matching chunks with scores
        """
        tracer = trace.get_tracer(__name__) if _OBSERVABILITY_AVAILABLE else None
        
        with tracer.start_as_current_span("weaviate.search") if tracer else _FakeSpan() as span:
            if tracer:
                span.set_attribute("weaviate.operation", "search_chunks_hybrid")
                span.set_attribute("weaviate.collection", "MemoryChunk")
                span.set_attribute("weaviate.limit", limit)
                span.set_attribute("weaviate.alpha", alpha)
                span.set_attribute("weaviate.query_length", len(query))
                if query_vector:
                    span.set_attribute("weaviate.has_query_vector", True)
                if memory_class:
                    span.set_attribute("weaviate.memory_class", memory_class)
                if tenant_id:
                    span.set_attribute("weaviate.tenant_id", str(tenant_id))
                if agent_id:
                    span.set_attribute("weaviate.agent_id", str(agent_id))
            
            start_time = time.perf_counter() if _OBSERVABILITY_AVAILABLE else 0
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._pool,
                self._sync_search_chunks_hybrid,
                query, query_vector, memory_class, tenant_id, agent_id, limit, alpha
            )
            
            # Record metrics
            if _OBSERVABILITY_AVAILABLE:
                duration = time.perf_counter() - start_time
                tenant_str = str(tenant_id) if tenant_id else "default"
                
                if tracer and span:
                    span.set_attribute("weaviate.result_count", len(result))
                    span.set_attribute("weaviate.duration_ms", duration * 1000)
                    span.set_status(Status(StatusCode.OK))
                
                MetricsHelper.record_memory_operation(
                    operation="search",
                    memory_class=memory_class or "all",
                    status="success",
                    tenant_id=tenant_str,
                )
                MetricsHelper.record_latency("search", "weaviate", duration)
            
            return result
    
    def _sync_search_chunks_hybrid(
        self,
        query: str,
        query_vector: Optional[List[float]],
        memory_class: Optional[str],
        tenant_id: Optional[uuid.UUID],
        agent_id: Optional[uuid.UUID],
        limit: int,
        alpha: float,
    ) -> List[Dict[str, Any]]:
        """Synchronous hybrid search (runs in thread pool)."""
        collection = self._client.collections.get("MemoryChunk")
        
        filters = []
        if memory_class:
            filters.append(f"memory_class == '{memory_class}'")
        if tenant_id:
            filters.append(f"tenant_id == '{str(tenant_id)}'")
        if agent_id:
            filters.append(f"agent_id == '{str(agent_id)}'")
        
        where_filter = None
        if filters:
            where_filter = {"operator": "And", "operands": [
                {"path": [f.split(" ")[0]], "operator": "Equal", "valueText": f.split("==")[1].strip()}
                for f in filters
            ]}
        
        search_params = {
            "query": query,
            "limit": limit,
            "alpha": alpha,
        }
        
        if where_filter:
            search_params["where"] = where_filter
        
        if query_vector:
            search_params["vector"] = query_vector
        
        results = collection.query.hybrid(**search_params)
        
        return [
            {
                "weaviate_id": str(obj.uuid),
                **obj.properties,
                "score": obj.metadata.score if hasattr(obj.metadata, 'score') else None,
            }
            for obj in results.objects
        ]
    
    async def search_chunks_near_vector(
        self,
        query_vector: List[float],
        memory_class: Optional[str] = None,
        agent_id: Optional[uuid.UUID] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Near-vector search on MemoryChunk collection.
        
        Args:
            query_vector: Query vector
            memory_class: Optional filter
            limit: Maximum results
            
        Returns:
            List of matching chunks
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._pool,
            self._sync_search_chunks_near_vector,
            query_vector, memory_class, agent_id, limit
        )
    
    def _sync_search_chunks_near_vector(
        self,
        query_vector: List[float],
        memory_class: Optional[str],
        agent_id: Optional[uuid.UUID],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Synchronous near-vector search (runs in thread pool)."""
        collection = self._client.collections.get("MemoryChunk")
        
        filters = []
        if memory_class:
            filters.append(f"memory_class == '{memory_class}'")
        if agent_id:
            filters.append(f"agent_id == '{str(agent_id)}'")
        
        where_filter = None
        if filters:
            where_filter = {"operator": "And", "operands": [
                {"path": [f.split(" ")[0]], "operator": "Equal", "valueText": f.split("==")[1].strip()}
                for f in filters
            ]}

        search_params = {
            "vector": query_vector,
            "limit": limit,
        }
        
        if where_filter:
            search_params["where"] = where_filter
        
        results = collection.query.near_vector(**search_params)
        
        return [
            {
                "weaviate_id": str(obj.uuid),
                **obj.properties,
            }
            for obj in results.objects
        ]
    
    async def search_chunks_near_text(
        self,
        text: str,
        memory_class: Optional[str] = None,
        agent_id: Optional[uuid.UUID] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Near-text (semantic) search on MemoryChunk collection.
        
        Args:
            text: Query text
            memory_class: Optional filter
            limit: Maximum results
            
        Returns:
            List of matching chunks
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._pool,
            self._sync_search_chunks_near_text,
            text, memory_class, agent_id, limit
        )
    
    def _sync_search_chunks_near_text(
        self,
        text: str,
        memory_class: Optional[str],
        agent_id: Optional[uuid.UUID],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Synchronous near-text search (runs in thread pool)."""
        collection = self._client.collections.get("MemoryChunk")
        
        filters = []
        if memory_class:
            filters.append(f"memory_class == '{memory_class}'")
        if agent_id:
            filters.append(f"agent_id == '{str(agent_id)}'")
        
        where_filter = None
        if filters:
            where_filter = {"operator": "And", "operands": [
                {"path": [f.split(" ")[0]], "operator": "Equal", "valueText": f.split("==")[1].strip()}
                for f in filters
            ]}

        search_params = {
            "query": text,
            "limit": limit,
        }
        
        if where_filter:
            search_params["where"] = where_filter
        
        results = collection.query.near_text(**search_params)
        
        return [
            {
                "weaviate_id": str(obj.uuid),
                **obj.properties,
            }
            for obj in results.objects
        ]
    
    # Summary operations
    async def insert_summary(self, summary: Summary) -> str:
        """Insert a summary.
        
        Args:
            summary: Summary to insert
            
        Returns:
            Weaviate ID
        """
        collection = self._client.collections.get("Summary")
        if summary.summary_id is None:
            summary.summary_id = uuid.uuid4()
        
        result = collection.data.insert(summary.to_dict())
        return str(result)
    
    async def search_summaries_hybrid(
        self,
        query: str,
        tenant_id: Optional[uuid.UUID] = None,
        limit: int = 10,
        alpha: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Hybrid search on Summary collection."""
        collection = self._client.collections.get("Summary")
        
        results = collection.query.hybrid(
            query=query,
            limit=limit,
            alpha=alpha,
        )
        
        return [
            {
                "weaviate_id": str(obj.uuid),
                **obj.properties,
            }
            for obj in results.objects
        ]
    
    # Entity operations
    async def insert_entity(self, entity: Entity) -> str:
        """Insert an entity."""
        collection = self._client.collections.get("Entity")
        if entity.entity_id is None:
            entity.entity_id = uuid.uuid4()
        
        result = collection.data.insert(entity.to_dict())
        return str(result)
    
    async def search_entities_hybrid(
        self,
        query: str,
        tenant_id: Optional[uuid.UUID] = None,
        entity_type: Optional[str] = None,
        limit: int = 10,
        alpha: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Hybrid search on Entity collection."""
        collection = self._client.collections.get("Entity")
        
        results = collection.query.hybrid(
            query=query,
            limit=limit,
            alpha=alpha,
        )
        
        return [
            {
                "weaviate_id": str(obj.uuid),
                **obj.properties,
            }
            for obj in results.objects
        ]
    
    # Decision operations
    async def insert_decision(self, decision: Decision) -> str:
        """Insert a decision."""
        collection = self._client.collections.get("Decision")
        if decision.decision_id is None:
            decision.decision_id = uuid.uuid4()
        
        result = collection.data.insert(decision.to_dict())
        return str(result)
    
    async def search_decisions_hybrid(
        self,
        query: str,
        tenant_id: Optional[uuid.UUID] = None,
        status: str = "active",
        limit: int = 10,
        alpha: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Hybrid search on Decision collection."""
        collection = self._client.collections.get("Decision")
        
        results = collection.query.hybrid(
            query=query,
            limit=limit,
            alpha=alpha,
            where={"path": ["status"], "operator": "Equal", "valueText": status},
        )
        
        return [
            {
                "weaviate_id": str(obj.uuid),
                **obj.properties,
            }
            for obj in results.objects
        ]
    
    async def get_object(self, class_name: str, weaviate_id: str) -> Optional[Dict[str, Any]]:
        """Get an object by ID.
        
        Args:
            class_name: Weaviate class name
            weaviate_id: Object UUID
            
        Returns:
            Object properties or None
        """
        collection = self._client.collections.get(class_name)
        
        try:
            obj = collection.data.get_by_id(weaviate_id)
            if obj:
                return obj.properties
        except Exception:
            pass
        return None
    
    async def delete_object(self, class_name: str, weaviate_id: str) -> bool:
        """Delete an object by ID.
        
        Args:
            class_name: Weaviate class name
            weaviate_id: Object UUID
            
        Returns:
            True if deleted successfully
        """
        collection = self._client.collections.get(class_name)
        
        try:
            collection.data.delete_by_id(weaviate_id)
            return True
        except Exception:
            return False