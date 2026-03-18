"""PostgreSQL client with asyncpg and pgvector support."""
import asyncpg
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID, uuid4, uuid5
import json
import time
import warnings

# Observability imports (optional - graceful degradation)
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from openclaw_memory.observability.logging import get_logger, set_trace_context
    from openclaw_memory.observability.metrics import MetricsHelper
    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False

# Get logger
logger = get_logger("openclaw.storage.postgres") if _OBSERVABILITY_AVAILABLE else None

BRAINCLAW_NS = UUID("b4a1bc1a-0000-4000-a000-b4a1bc1ab000")


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


def _coerce_identity_uuid(value: Optional[Any]) -> Optional[UUID]:
    """Normalize OpenClaw identity strings into stable UUIDs for storage."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value

    text = str(value).strip()
    if not text:
        return None

    try:
        return UUID(text)
    except ValueError:
        return uuid5(BRAINCLAW_NS, text)


@dataclass
class MemoryItem:
    """Memory item representing stored knowledge in the system.
    
    Maps to the memory_items table in PostgreSQL with pgvector.
    """
    id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    memory_class: str = "semantic"
    memory_type: Optional[str] = None
    content: str = ""
    content_embedding: Optional[List[float]] = None
    source_message_id: Optional[UUID] = None
    source_session_id: Optional[UUID] = None
    source_tool_call_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    extracted_by: Optional[str] = None
    extraction_method: Optional[str] = None
    extraction_timestamp: Optional[datetime] = None
    extraction_confidence: Optional[float] = None
    extraction_metadata: dict = field(default_factory=dict)
    confidence: float = 0.5
    user_confirmed: bool = False
    user_confirmed_at: Optional[datetime] = None
    user_confirmed_by: Optional[UUID] = None
    valid_from: datetime = field(default_factory=datetime.utcnow)
    valid_to: Optional[datetime] = None
    is_current: bool = True
    superseded_by: Optional[UUID] = None
    supersession_reason: Optional[str] = None
    visibility_scope: str = "tenant"
    access_control: dict = field(default_factory=dict)
    retention_policy: str = "default"
    retention_until: Optional[datetime] = None
    weaviate_id: Optional[str] = None
    neo4j_id: Optional[str] = None
    weaviate_synced: bool = False
    neo4j_synced: bool = False
    weaviate_synced_at: Optional[datetime] = None
    neo4j_synced_at: Optional[datetime] = None
    sync_version: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid4()
        
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = _coerce_identity_uuid(current_agent_id)
            except Exception:
                pass

        # Automatically set tenant_id from the verified security context if not provided
        if self.tenant_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_tenant_id
                current_tenant_id = get_current_tenant_id()
                if current_tenant_id:
                    self.tenant_id = _coerce_identity_uuid(current_tenant_id)
            except Exception:
                pass
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        d = {
            "tenant_id": self.tenant_id,
            "memory_class": self.memory_class,
            "memory_type": self.memory_type,
            "content": self.content,
            "content_embedding": self.content_embedding,
            "source_message_id": self.source_message_id,
            "source_session_id": self.source_session_id,
            "source_tool_call_id": self.source_tool_call_id,
            "agent_id": self.agent_id,
            "extracted_by": self.extracted_by,
            "extraction_method": self.extraction_method,
            "extraction_confidence": self.extraction_confidence,
            "extraction_metadata": json.dumps(self.extraction_metadata),
            "confidence": self.confidence,
            "user_confirmed": self.user_confirmed,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "is_current": self.is_current,
            "visibility_scope": self.visibility_scope,
            "access_control": json.dumps(self.access_control),
            "retention_policy": self.retention_policy,
            "retention_until": self.retention_until,
        }
        if self.id:
            d["id"] = self.id
        return d


class PostgresClient:
    """Async PostgreSQL client with pgvector support for memory storage.
    
    Provides:
    - Connection pooling with asyncpg
    - MemoryItem CRUD operations
    - Vector similarity search using cosine distance (<=>)
    - Batch inserts for efficient bulk loading
    - Sync status tracking for Weaviate/Neo4j
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "openclaw_memory",
        user: str = "openclaw",
        password: str = "openclaw_secret",
        min_pool_size: int = 5,
        max_pool_size: int = 20,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """Create connection pool."""
        self._pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            min_size=self.min_pool_size,
            max_size=self.max_pool_size,
        )
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
    
    async def is_connected(self) -> bool:
        """Check if connection pool is active."""
        return self._pool is not None
    
    async def insert_memory_item(
        self,
        item: MemoryItem,
        embedding_service=None
    ) -> MemoryItem:
        """Insert a new memory item.
        
        Args:
            item: MemoryItem to insert
            embedding_service: Optional EmbeddingService to generate embeddings
            
        Returns:
            MemoryItem with generated ID and timestamps
        """
        # Get tracer if observability is available
        tracer = trace.get_tracer(__name__) if _OBSERVABILITY_AVAILABLE else None
        
        with tracer.start_as_current_span("postgres.insert") if tracer else _FakeSpan() as span:
            if tracer:
                span.set_attribute("postgres.operation", "insert")
                span.set_attribute("postgres.memory_class", item.memory_class)
                if item.tenant_id:
                    span.set_attribute("postgres.tenant_id", str(item.tenant_id))
            
            if item.id is None:
                item.id = uuid4()
            
            # Generate embedding if service provided and content exists
            if embedding_service and item.content and not item.content_embedding:
                try:
                    item.content_embedding = await embedding_service.generate_embedding(item.content)
                except Exception:
                    # Continue without embedding if generation fails
                    pass
            
            start_time = time.perf_counter() if _OBSERVABILITY_AVAILABLE else 0
            
            query = """
                INSERT INTO memory_items (
                    id, tenant_id, agent_id, memory_class, memory_type, content,
                    content_embedding, source_message_id, source_session_id,
                    source_tool_call_id, extracted_by, extraction_method,
                    extraction_confidence, extraction_metadata, confidence, user_confirmed,
                    valid_from, valid_to, is_current, visibility_scope, access_control,
                    retention_policy, retention_until
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                    $17, $18, $19, $20, $21, $22, $23
                )
                RETURNING *
            """
            async with self._pool.acquire() as conn:
                from openclaw_memory.security.access_control import set_db_session_context
                await set_db_session_context(conn)
                row = await conn.fetchrow(
                    query,
                    item.id,
                    item.tenant_id,
                    item.agent_id,
                    item.memory_class,
                    item.memory_type,
                    item.content,
                    item.content_embedding,
                    item.source_message_id,
                    item.source_session_id,
                    item.source_tool_call_id,
                    item.extracted_by,
                    item.extraction_method,
                    item.extraction_confidence,
                    json.dumps(item.extraction_metadata),
                    item.confidence,
                    item.user_confirmed,
                    item.valid_from,
                    item.valid_to,
                    item.is_current,
                    item.visibility_scope,
                    json.dumps(item.access_control),
                    item.retention_policy,
                    item.retention_until,
                )
            
            # Record metrics
            if _OBSERVABILITY_AVAILABLE:
                duration = time.perf_counter() - start_time
                if tracer and span:
                    span.set_attribute("postgres.duration_ms", duration * 1000)
                    span.set_status(Status(StatusCode.OK))
                
                MetricsHelper.record_memory_operation(
                    operation="insert",
                    memory_class=item.memory_class,
                    status="success",
                    tenant_id=str(item.tenant_id) if item.tenant_id else "default",
                )
                MetricsHelper.record_latency("insert", "postgres", duration)
            
            return self._row_to_memory_item(row)
    
    async def get_memory_item(self, item_id: UUID) -> Optional[MemoryItem]:
        """Get a memory item by ID.
        
        Args:
            item_id: UUID of the memory item
            
        Returns:
            MemoryItem if found, None otherwise
        """
        query = "SELECT * FROM memory_items WHERE id = $1"
        async with self._pool.acquire() as conn:
            from openclaw_memory.security.access_control import set_db_session_context
            await set_db_session_context(conn)
            row = await conn.fetchrow(
                query,
                item_id
            )
            if row:
                return self._row_to_memory_item(row)
            return None

    async def query(
        self,
        sql_or_query: str,
        params: Optional[List[Any]] = None,
        limit: Optional[int] = None,
    ) -> List[asyncpg.Record]:
        """Execute raw SQL or a text-search fallback query against memory_items."""
        if not sql_or_query:
            return []

        params = list(params or [])
        is_sql = sql_or_query.lstrip().upper().startswith(
            ("SELECT", "WITH", "UPDATE", "INSERT", "DELETE")
        )

        async with self._pool.acquire() as conn:
            from openclaw_memory.security.access_control import set_db_session_context

            await set_db_session_context(conn)

            if is_sql:
                return await conn.fetch(sql_or_query, *params)

            text_limit = limit or 10
            text_query = """
                SELECT DISTINCT ON (agent_id, content)
                       id, content, memory_class, agent_id, visibility_scope,
                       confidence, created_at, metadata
                FROM memory_items
                WHERE is_current = TRUE
                  AND content ILIKE $1
                ORDER BY agent_id, content, created_at DESC
                LIMIT $2
            """
            return await conn.fetch(text_query, f"%{sql_or_query}%", text_limit)

    async def get_agent_memories(
        self,
        agent_id: Optional[str] = None,
        memory_class: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryItem]:
        """Get current memories visible to a specific agent."""
        conditions = ["is_current = TRUE"]
        params: List[Any] = []
        param_idx = 1

        canonical_agent_id = _coerce_identity_uuid(agent_id)
        if canonical_agent_id:
            conditions.append(
                f"(agent_id = ${param_idx} OR visibility_scope IN ('team', 'tenant', 'public'))"
            )
            params.append(canonical_agent_id)
            param_idx += 1

        if memory_class:
            conditions.append(f"memory_class = ${param_idx}")
            params.append(memory_class)
            param_idx += 1

        params.append(limit)

        query = f"""
            SELECT DISTINCT ON (agent_id, content) *
            FROM memory_items
            WHERE {' AND '.join(conditions)}
            ORDER BY agent_id, content, created_at DESC
            LIMIT ${param_idx}
        """

        async with self._pool.acquire() as conn:
            from openclaw_memory.security.access_control import set_db_session_context

            await set_db_session_context(conn)
            rows = await conn.fetch(query, *params)
            return [self._row_to_memory_item(row) for row in rows]
    
    async def search_memory_items(
        self,
        memory_class: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[MemoryItem]:
        """Search memory items by filters.
        
        Args:
            memory_class: Filter by memory class (episodic, semantic, etc.)
            tenant_id: Filter by tenant
            session_id: Filter by source session
            limit: Maximum results
            offset: Result offset for pagination
            
        Returns:
            List of matching MemoryItems
        """
        tracer = trace.get_tracer(__name__) if _OBSERVABILITY_AVAILABLE else None
        
        with tracer.start_as_current_span("postgres.search") if tracer else _FakeSpan() as span:
            if tracer:
                span.set_attribute("postgres.operation", "search")
                span.set_attribute("postgres.limit", limit)
                span.set_attribute("postgres.offset", offset)
                if memory_class:
                    span.set_attribute("postgres.memory_class", memory_class)
                if tenant_id:
                    span.set_attribute("postgres.tenant_id", str(tenant_id))
            
            conditions = ["is_current = TRUE"]
            params = []
            param_idx = 1
            
            if memory_class:
                conditions.append(f"memory_class = ${param_idx}")
                params.append(memory_class)
                param_idx += 1
            
            if tenant_id:
                conditions.append(f"tenant_id = ${param_idx}")
                params.append(tenant_id)
                param_idx += 1
            
            if session_id:
                conditions.append(f"source_session_id = ${param_idx}")
                params.append(session_id)
                param_idx += 1
            
            params.extend([limit, offset])
            
            query = f"""
                SELECT * FROM memory_items
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            
            start_time = time.perf_counter() if _OBSERVABILITY_AVAILABLE else 0
            
            async with self._pool.acquire() as conn:
                from openclaw_memory.security.access_control import set_db_session_context
                await set_db_session_context(conn)
                rows = await conn.fetch(query, *params)
                result = [self._row_to_memory_item(row) for row in rows]
            
            # Record metrics
            if _OBSERVABILITY_AVAILABLE:
                duration = time.perf_counter() - start_time
                tenant_str = str(tenant_id) if tenant_id else "default"
                
                if tracer and span:
                    span.set_attribute("postgres.result_count", len(result))
                    span.set_attribute("postgres.duration_ms", duration * 1000)
                    span.set_status(Status(StatusCode.OK))
                
                MetricsHelper.record_memory_operation(
                    operation="search",
                    memory_class=memory_class or "all",
                    status="success",
                    tenant_id=tenant_str,
                )
                MetricsHelper.record_latency("search", "postgres", duration)
            
            return result
    
    async def supersede_memory_item(
        self,
        original_id: UUID,
        new_content: str,
        reason: str,
        new_confidence: Optional[float] = None,
    ) -> MemoryItem:
        """Supersede a memory item with new content.
        
        Marks the original as superseded and creates a new current item.
        
        Args:
            original_id: ID of the item to supersede
            new_content: New content for the replacement item
            reason: Reason for supersession
            new_confidence: Optional new confidence score
            
        Returns:
            New MemoryItem that supersedes the original
        """
        async with self._pool.acquire() as conn:
            from openclaw_memory.security.access_control import set_db_session_context, get_current_agent_id
            await set_db_session_context(conn)
            update_query = """
                    UPDATE memory_items
                    SET is_current = FALSE, 
                        supersession_reason = $2,
                        updated_at = NOW()
                    WHERE id = $1
            """
            async with conn.transaction():
                # Mark original as superseded
                _ = await conn.execute(update_query, original_id, reason)
                
                # Create new item based on original
                insert_query = """
                    INSERT INTO memory_items (
                        tenant_id, agent_id, memory_class, memory_type, status,
                        content, source_message_id, source_session_id,
                        source_tool_call_id, extracted_by, extraction_method,
                        extraction_timestamp, extractor_name, extractor_version,
                        extraction_confidence, extraction_metadata, confidence,
                        user_confirmed, user_confirmed_at, user_confirmed_by,
                        valid_from, valid_to, is_current, superseded_by,
                        supersession_reason, visibility_scope, access_control,
                        retention_policy, retention_until, weaviate_id,
                        neo4j_id, weaviate_synced, neo4j_synced,
                        weaviate_synced_at, neo4j_synced_at, sync_version,
                        metadata
                    )
                    SELECT
                        tenant_id, agent_id, memory_class, memory_type, status,
                        $2, source_message_id, source_session_id,
                        source_tool_call_id, extracted_by, extraction_method,
                        NOW(), COALESCE(extractor_name, extracted_by, 'brainclaw'),
                        COALESCE(extractor_version, '1.3.0'),
                        extraction_confidence, COALESCE(extraction_metadata, '{}'::jsonb),
                        COALESCE($3, confidence), user_confirmed,
                        user_confirmed_at, user_confirmed_by, NOW(), NULL,
                        TRUE, $1, $4, visibility_scope,
                        COALESCE(access_control, '{}'::jsonb), retention_policy,
                        retention_until, NULL, NULL, FALSE, FALSE, NULL, NULL,
                        COALESCE(sync_version, 1) + 1, COALESCE(metadata, '{}'::jsonb)
                    FROM memory_items WHERE id = $1
                    RETURNING *
                """
                row = await conn.fetchrow(insert_query, original_id, new_content, new_confidence, reason)
                
                # Update original's superseded_by reference
                ref_update_query = """
                    UPDATE memory_items
                    SET superseded_by = $2, updated_at = NOW()
                    WHERE id = $1
                """
                _ = await conn.execute(ref_update_query, original_id, row["id"])
                
                return self._row_to_memory_item(row)
    
    async def vector_search(
        self,
        query_embedding: List[float],
        memory_class: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        limit: int = 10,
    ) -> List[MemoryItem]:
        """Search by embedding similarity using cosine distance.
        
        Uses pgvector's <=> operator for cosine distance calculations.
        Lower distance = higher similarity.
        
        Args:
            query_embedding: Query vector to search against
            memory_class: Optional filter by memory class
            tenant_id: Optional filter by tenant
            limit: Maximum results
            
        Returns:
            List of MemoryItems sorted by similarity (best first)
        """
        conditions = ["is_current = TRUE", "content_embedding IS NOT NULL"]
        params: List[Any] = [query_embedding]
        param_idx = 2
        
        if memory_class:
            conditions.append(f"memory_class = ${param_idx}")
            params.append(memory_class)
            param_idx += 1
        
        if tenant_id:
            conditions.append(f"tenant_id = ${param_idx}")
            params.append(tenant_id)
            param_idx += 1
        
        params.append(limit)
        
        query = f"""
            SELECT *, (content_embedding <=> $1) as distance
            FROM memory_items
            WHERE {' AND '.join(conditions)}
            ORDER BY content_embedding <=> $1
            LIMIT ${param_idx}
        """
        
        async with self._pool.acquire() as conn:
            from openclaw_memory.security.access_control import set_db_session_context
            await set_db_session_context(conn)
            rows = await conn.fetch(query, *params)
            return [self._row_to_memory_item(row) for row in rows]
    
    async def batch_insert_memory_items(
        self,
        items: List[MemoryItem],
    ) -> List[MemoryItem]:
        """Batch insert memory items efficiently.
        
        Args:
            items: List of MemoryItems to insert
            
        Returns:
            List of inserted MemoryItems with generated IDs
        """
        if not items:
            return []
        
        # Assign IDs to items that don't have one
        for item in items:
            if item.id is None:
                item.id = uuid4()
        
        async with self._pool.acquire() as conn:
            from openclaw_memory.security.access_control import set_db_session_context
            await set_db_session_context(conn)
            query = """
                    INSERT INTO memory_items (
                        id, tenant_id, agent_id, memory_class, memory_type, content,
                        content_embedding, source_message_id, source_session_id,
                        source_tool_call_id, extracted_by, extraction_method,
                        extraction_confidence, confidence, user_confirmed,
                        valid_from, visibility_scope, retention_policy
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                        $15, $16, $17, $18
                    )
                    RETURNING *
            """
            async with conn.transaction():
                rows = await conn.fetch(
                    query,
                    *[
                        (
                            item.id,
                            item.tenant_id,
                            item.agent_id,
                            item.memory_class,
                            item.memory_type,
                            item.content,
                            item.content_embedding,
                            item.source_message_id,
                            item.source_session_id,
                            item.source_tool_call_id,
                            item.extracted_by,
                            item.extraction_method,
                            item.extraction_confidence,
                            item.confidence,
                            item.user_confirmed,
                            item.valid_from,
                            item.visibility_scope,
                            item.retention_policy,
                        )
                        for item in items
                    ]
                )
                
                return [self._row_to_memory_item(row) for row in rows]
    
    async def update_sync_status(
        self,
        item_id: UUID,
        weaviate_id: Optional[str] = None,
        neo4j_id: Optional[str] = None,
        weaviate_synced: Optional[bool] = None,
        neo4j_synced: Optional[bool] = None,
    ) -> None:
        """Update sync status for Weaviate/Neo4j.
        
        Args:
            item_id: Memory item ID
            weaviate_id: Weaviate document ID
            neo4j_id: Neo4j node ID
            weaviate_synced: Whether synced to Weaviate
            neo4j_synced: Whether synced to Neo4j
        """
        updates = ["updated_at = NOW()"]
        params: List[Any] = [item_id]
        param_idx = 2
        
        if weaviate_id is not None:
            updates.append(f"weaviate_id = ${param_idx}")
            params.append(weaviate_id)
            param_idx += 1
        
        if neo4j_id is not None:
            updates.append(f"neo4j_id = ${param_idx}")
            params.append(neo4j_id)
            param_idx += 1
        
        if weaviate_synced is not None:
            updates.append(f"weaviate_synced = ${param_idx}")
            params.append(weaviate_synced)
            param_idx += 1
            if weaviate_synced:
                updates.append(f"weaviate_synced_at = NOW()")
        
        if neo4j_synced is not None:
            updates.append(f"neo4j_synced = ${param_idx}")
            params.append(neo4j_synced)
            param_idx += 1
            if neo4j_synced:
                updates.append(f"neo4j_synced_at = NOW()")
        
        async with self._pool.acquire() as conn:
            _ = await conn.execute(
                f"UPDATE memory_items SET {', '.join(updates)} WHERE id = $1",
                *params
            )
    
    def _row_to_memory_item(self, row: asyncpg.Record) -> MemoryItem:
        """Convert database row to MemoryItem."""
        return MemoryItem(
            id=row["id"],
            tenant_id=row["tenant_id"],
            memory_class=row["memory_class"],
            memory_type=row["memory_type"],
            content=row["content"],
            content_embedding=list(row["content_embedding"]) if row["content_embedding"] else None,
            source_message_id=row["source_message_id"],
            source_session_id=row["source_session_id"],
            source_tool_call_id=row["source_tool_call_id"],
            agent_id=row.get("agent_id"),
            extracted_by=row["extracted_by"],
            extraction_method=row["extraction_method"],
            extraction_confidence=row["extraction_confidence"],
            extraction_metadata=row.get("extraction_metadata", {}),
            confidence=row["confidence"],
            user_confirmed=row["user_confirmed"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            is_current=row["is_current"],
            superseded_by=row["superseded_by"],
            supersession_reason=row["supersession_reason"],
            visibility_scope=row["visibility_scope"],
            access_control=row.get("access_control", {}),
            retention_policy=row["retention_policy"],
            retention_until=row["retention_until"],
            weaviate_id=row["weaviate_id"],
            neo4j_id=row["neo4j_id"],
            weaviate_synced=row["weaviate_synced"],
            neo4j_synced=row["neo4j_synced"],
            weaviate_synced_at=row["weaviate_synced_at"],
            neo4j_synced_at=row["neo4j_synced_at"],
            sync_version=row["sync_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
