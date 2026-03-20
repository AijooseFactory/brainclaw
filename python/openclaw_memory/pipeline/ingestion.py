"""Ingestion pipeline module - orchestrates chunking, extraction, and sync."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
import logging
import time

# Observability imports (optional - graceful degradation)
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from openclaw_memory.observability.logging import get_logger
    from openclaw_memory.observability.metrics import MetricsHelper
    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False

from openclaw_memory.storage.postgres import PostgresClient, MemoryItem
from openclaw_memory.pipeline.chunking import chunk_content, Chunk
from openclaw_memory.pipeline.extraction import extract_all, Entity, Relationship, ExtractionResult
from openclaw_memory.pipeline.sync import sync_to_weaviate, sync_to_neo4j, sync_memory_item, SyncStatus
from openclaw_memory.embeddings import EmbeddingService, EmbeddingConfig

logger = logging.getLogger(__name__)

# Get observability logger
obs_logger = get_logger("openclaw.pipeline.ingestion") if _OBSERVABILITY_AVAILABLE else None


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


# Write Policy constants from spec
ALWAYS_STORE_TYPES = [
    "user_messages",
    "assistant_messages", 
    "system_messages",
    "tool_calls",
]

NEVER_PROMOTE_TYPES = [
    "low_confidence_extractions",
    "contradicted_claims",
    "chit_chat",
]

DECISION_PHRASES = [
    "we decided",
    "let's go with",
    "agreed on",
    "the decision was",
    "will use",
    "going with",
    "chose to",
]

PREFERENCE_PHRASES = [
    "remember this",
    "i prefer",
    "i like",
    "my preference",
]


@dataclass
class IngestionEvent:
    """An event to be ingested into memory.
    
    Attributes:
        event_type: Type of event (message, tool_call, summary, etc.)
        content: The content to ingest
        role: Role (user, assistant, system)
        session_id: Associated session ID
        message_id: Original message ID
        tool_name: If tool_call, the tool name
        metadata: Additional metadata
    """
    event_type: str
    content: str
    role: Optional[str] = None
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    tool_name: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryLifecycle:
    """Tracks the lifecycle state of a memory item.
    
    States: raw -> active -> superseded/expired -> archived
    """
    state: str = "raw"
    history: List[Dict[str, Any]] = field(default_factory=list)
    
    def transition_to(self, new_state: str) -> None:
        """Transition to a new state."""
        valid_transitions = {
            "raw": ["active"],
            "active": ["superseded", "expired"],
            "superseded": ["archived"],
            "expired": ["archived"],
            "archived": [],
        }
        
        if new_state in valid_transitions.get(self.state, []):
            self.state = new_state
            self.history.append({
                "from": self.state,
                "to": new_state,
                "timestamp": datetime.utcnow().isoformat(),
            })
        else:
            logger.warning(f"Invalid transition from {self.state} to {new_state}")


@dataclass 
class IngestionResult:
    """Result of ingestion containing the memory item and sync status."""
    memory_item: Optional[MemoryItem] = None
    lifecycle: Optional[MemoryLifecycle] = None
    sync_status: Optional[SyncStatus] = None
    chunks: List[Chunk] = field(default_factory=list)
    extraction: Optional[ExtractionResult] = None
    promoted: bool = False


class WritePolicy:
    """Implements the Write Policy from the spec.
    
    Determines what content should be stored and promoted to memory.
    """
    
    def __init__(self):
        self.always_store = ALWAYS_STORE_TYPES
        self.never_promote = NEVER_PROMOTE_TYPES
    
    def should_always_store(self, event_type: str) -> bool:
        """Check if event type should always be stored."""
        return event_type in self.always_store
    
    def should_never_promote(self, content_type: str) -> bool:
        """Check if content should never be promoted."""
        return content_type in self.never_promote
    
    def should_promote(
        self,
        memory_type: str = "",
        content: str = "",
        confidence: float = 0.0,
        user_confirmed: bool = False,
        explicitly_marked: bool = False,
        explicit_remember: bool = False,
        occurrence_count: int = 1,
        contradiction_detected: bool = False,
    ) -> bool:
        """Determine if content should be promoted to memory.
        
        Args:
            memory_type: Type of memory (fact, decision, preference, etc.)
            content: The content text
            confidence: Extraction confidence
            user_confirmed: Whether user confirmed this content
            explicitly_marked: Whether explicitly marked as important
            explicit_remember: Whether user said "remember this"
            occurrence_count: How many times mentioned
            contradiction_detected: Whether a contradiction was detected with existing memory
            
        Returns:
            True if should be promoted to active memory
        """
        # Phase 12 Refined Perfection (v1.5.0-intel): Temporal Authority
        # Automatically approve contradictions if they are newer 'summaries', 'reports', or 'corrections'.
        if contradiction_detected:
            if memory_type in ["summary", "report", "correction"] or user_confirmed:
                logger.info(f"Temporal Authority: Auto-approving contradiction resolution for {memory_type}")
                return True
            logger.warning(f"Blocking promotion due to contradiction: {content[:50]}...")
            return False

        # Check never promote first
        if self.should_never_promote(memory_type):
            return False
        
        # Facts: confidence >= 0.7 OR user_confirmed
        if memory_type == "fact":
            return confidence >= 0.7 or user_confirmed
        
        # Decisions: explicitly marked OR contains decision phrases
        if memory_type == "decision":
            if explicitly_marked:
                return True
            content_lower = content.lower()
            return any(phrase in content_lower for phrase in DECISION_PHRASES)
        
        # Preferences: "remember this" OR stated 2+ times
        if memory_type == "preference":
            if explicit_remember:
                return True
            content_lower = content.lower()
            if any(phrase in content_lower for phrase in PREFERENCE_PHRASES):
                return True
            return occurrence_count >= 2
        
        # Default: high confidence or user confirmed
        return confidence >= 0.8 or user_confirmed


def should_promote_to_memory(
    memory_type: str = "",
    content: str = "",
    confidence: float = 0.0,
    user_confirmed: bool = False,
    explicit_remember: bool = False,
    occurrence_count: int = 1,
) -> bool:
    """Convenience function to check if content should be promoted."""
    policy = WritePolicy()
    
    # Build content_lower once
    content_lower = content.lower() if content else ""
    
    return policy.should_promote(
        memory_type=memory_type,
        content=content,
        confidence=confidence,
        user_confirmed=user_confirmed,
        explicit_remember=explicit_remember or "remember this" in content_lower,
        occurrence_count=occurrence_count,
    )


def determine_memory_class(content: str, event_type: str, role: str) -> str:
    """Determine the memory class based on content and context.
    
    Args:
        content: The content text
        event_type: Type of event
        role: Message role
        
    Returns:
        Memory class string
    """
    content_lower = content.lower() if content else ""
    
    # Check for decision
    if any(phrase in content_lower for phrase in DECISION_PHRASES):
        return "decision"
    
    # Check for preference
    if any(phrase in content_lower for phrase in PREFERENCE_PHRASES):
        return "preference"
    
    # Event type based
    if event_type == "tool_call":
        return "episodic"
    
    if event_type == "summary":
        return "summary"
    
    # Role based default
    if role == "system":
        return "identity"
    
    # Default to semantic for facts/concepts
    return "semantic"


class IngestionPipeline:
    """Main ingestion pipeline that orchestrates the full flow.
    
    Coordinates: raw event -> chunk -> extract -> sync -> promote
    """
    
    def __init__(
        self,
        postgres_client: PostgresClient,
        weaviate_client: Any,
        neo4j_client: Any,
        chunk_size: int = 512,
        overlap: int = 50,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """Initialize the ingestion pipeline.
        
        Args:
            postgres_client: PostgreSQL client
            weaviate_client: Weaviate client
            neo4j_client: Neo4j client
            chunk_size: Default chunk size in tokens
            overlap: Overlap between chunks
            embedding_service: Optional embedding service for generating embeddings
        """
        self.postgres = postgres_client
        self.weaviate = weaviate_client
        self.neo4j = neo4j_client
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.write_policy = WritePolicy()
        self.embedding_service = embedding_service
    
    async def ingest(self, event: IngestionEvent) -> IngestionResult:
        """Ingest an event through the full pipeline.
        
        Args:
            event: The event to ingest
            
        Returns:
            IngestionResult with memory item and sync status
        """
        tracer = trace.get_tracer(__name__) if _OBSERVABILITY_AVAILABLE else None
        
        with tracer.start_as_current_span("ingestion.ingest") if tracer else _FakeSpan() as span:
            if tracer:
                span.set_attribute("ingestion.event_type", event.event_type or "unknown")
                span.set_attribute("ingestion.role", event.role or "unknown")
                if event.tenant_id:
                    span.set_attribute("ingestion.tenant_id", str(event.tenant_id))
            
            start_time = time.perf_counter() if _OBSERVABILITY_AVAILABLE else 0
            
            result = IngestionResult()
        
        # Step 1: Store raw event (always)
        # Create memory item in raw state
        memory_item = await self._store_raw_event(event)
        result.memory_item = memory_item
        result.lifecycle = MemoryLifecycle("raw")
        
        # Step 2: Chunk content
        chunks = chunk_content(
            content=event.content,
            chunk_size=self.chunk_size,
            overlap=self.overlap,
            source_type=event.event_type,
            source_id=event.message_id or str(uuid4()),
        )
        result.chunks = chunks
        
        # Step 3: Extract entities and relationships
        extraction = extract_all(event.content)
        result.extraction = extraction
        
        # Step 4: Determine if should promote
        memory_class = determine_memory_class(
            event.content,
            event.event_type,
            event.role or "",
        )
        
        # Check write policy for promotion
        should_promote = self._should_promote(event, memory_class, extraction)
        
        # Step 5: Sync to indexes
        if should_promote:
            result.promoted = True
            result.lifecycle.transition_to("active")
            
            # Update memory item with extraction details
            memory_item.memory_class = memory_class
            memory_item.extraction_method = "rule"
            if extraction.entities:
                # Use highest confidence as extraction confidence
                memory_item.extraction_confidence = max(
                    (e.confidence for e in extraction.entities), default=0.5
                )
            
            # Sync to weaviate and neo4j
            sync_status = await sync_memory_item(
                postgres_client=self.postgres,
                weaviate_client=self.weaviate,
                neo4j_client=self.neo4j,
                memory_item=memory_item,
                entities=extraction.entities,
                relationships=extraction.relationships,
            )
            result.sync_status = sync_status
        
        # Record metrics
        if _OBSERVABILITY_AVAILABLE:
            duration = time.perf_counter() - start_time
            tenant_id_str = str(event.tenant_id) if event.tenant_id else "default"
            memory_class = result.memory_item.memory_class if result.memory_item else "unknown"
            status = "success" if result.sync_status.postgres else "error"
            
            if tracer and span:
                span.set_attribute("ingestion.duration_ms", duration * 1000)
                span.set_attribute("ingestion.promoted", result.promoted)
                span.set_status(Status(StatusCode.OK))
            
            MetricsHelper.record_ingestion(
                memory_class=memory_class,
                tenant_id=tenant_id_str,
                status=status,
            )
            MetricsHelper.record_ingestion_latency("full_pipeline", duration)
        
        return result
    
    async def _store_raw_event(self, event: IngestionEvent) -> MemoryItem:
        """Store raw event in PostgreSQL with embedding."""
        # Generate embedding if service is available
        content_embedding = None
        if self.embedding_service and event.content:
            try:
                if await self.embedding_service.is_initialized():
                    content_embedding = await self.embedding_service.generate_embedding(event.content)
                else:
                    logger.warning("Embedding service not initialized, skipping embedding generation")
            except Exception as e:
                # Log warning but don't break ingestion - embeddings are optional
                logger.warning(f"Failed to generate embedding: {e}")
        
        item = MemoryItem(
            tenant_id=event.metadata.get("tenant_id"),
            memory_class="episodic",
            memory_type=event.event_type,
            content=event.content,
            content_embedding=content_embedding,
            source_message_id=event.message_id,
            source_session_id=event.session_id,
            role=event.role,
            extracted_by="system",
            extraction_method="none",
            extraction_confidence=1.0,  # Raw events always have full confidence
            confidence=1.0,
            visibility_scope="tenant",
        )
        
        return await self.postgres.insert_memory_item(item)
    
    def _should_promote(
        self,
        event: IngestionEvent,
        memory_class: str,
        extraction: ExtractionResult,
    ) -> bool:
        """Determine if event should be promoted to active memory."""
        # Check event type - tool calls are episodic, don't promote
        if event.event_type == "tool_call":
            return False
        
        # Use write policy
        return self.write_policy.should_promote(
            memory_type=memory_class,
            content=event.content,
            confidence=extraction.entities[0].confidence if extraction.entities else 0.0,
            user_confirmed=event.metadata.get("user_confirmed", False),
            explicitly_marked=event.metadata.get("explicitly_marked", False),
            explicit_remember="remember this" in event.content.lower(),
            contradiction_detected=event.metadata.get("contradiction_detected", False),
        )


async def ingest_event(
    event: IngestionEvent,
    postgres_client: PostgresClient,
    weaviate_client: Any,
    neo4j_client: Any,
    chunk_size: int = 512,
) -> IngestionResult:
    """Convenience function to ingest an event.
    
    Args:
        event: Event to ingest
        postgres_client: PostgreSQL client
        weaviate_client: Weaviate client
        neo4j_client: Neo4j client
        chunk_size: Target chunk size
        
    Returns:
        IngestionResult
    """
    pipeline = IngestionPipeline(
        postgres_client=postgres_client,
        weaviate_client=weaviate_client,
        neo4j_client=neo4j_client,
        chunk_size=chunk_size,
    )
    
    return await pipeline.ingest(event)