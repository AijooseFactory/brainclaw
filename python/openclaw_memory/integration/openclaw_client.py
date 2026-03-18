"""
OpenClaw Memory System Integration Client.

This module provides the integration layer between the BrainClaw
Memory System and OpenClaw's core.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import asyncio

from ..storage.postgres import PostgresClient
from ..storage.weaviate_client import WeaviateClient
from ..storage.neo4j_client import Neo4jClient
from ..memory.classes import Memory, MemoryClass, AgentMemory
from ..memory.write_policy import WritePolicy, AgentIsolationPolicy
from ..pipeline.ingestion import IngestionPipeline
from ..retrieval.intent import IntentClassifier, Intent
from ..retrieval.policy import RetrievalPolicy
from ..retrieval.fusion import ResultFusion
from ..config import OpenClawMemoryConfig
from ..embeddings import EmbeddingService, EmbeddingConfig
from ..audit import AuditLogger


class OpenClawMemoryClient:
    """
    Main client for OpenClaw to interact with the GraphRAG Memory System.
    
    This client provides:
    - Memory storage and retrieval
    - Session-based memory context
    - Agent isolation
    - Intent-routed retrieval
    """
    
    def __init__(self, config: OpenClawMemoryConfig):
        self.config = config
        self.postgres = PostgresClient(
            host=config.postgres.host,
            port=config.postgres.port,
            database=config.postgres.database,
            user=config.postgres.user,
            password=config.postgres.password,
        )
        self.weaviate = WeaviateClient(
            url=f"http://{config.weaviate.host}:{config.weaviate.port}",
            api_key=config.weaviate.api_key,
        )
        self.neo4j = Neo4jClient(
            uri=config.neo4j.uri,
            user=config.neo4j.user,
            password=config.neo4j.password,
            database=config.neo4j.database,
        )
        self.write_policy = WritePolicy()
        self.agent_policy = AgentIsolationPolicy()
        
        # Initialize embedding service
        self.embedding_service = EmbeddingService(EmbeddingConfig.from_env())
        
        self.ingestion = IngestionPipeline(
            self.postgres, 
            self.weaviate, 
            self.neo4j,
            embedding_service=self.embedding_service,
        )
        self.intent_classifier = IntentClassifier()
        self.retrieval_policy = RetrievalPolicy(self.postgres, self.weaviate, self.neo4j)
        self.result_fusion = ResultFusion(config)
        
        # Initialize audit logger (optional - graceful degradation)
        self.audit_logger: Optional[AuditLogger] = None
        self._audit_enabled = False
    
    @classmethod
    def from_env(cls) -> "OpenClawMemoryClient":
        """Create client from environment variables."""
        config = OpenClawMemoryConfig.from_env()
        return cls(config)
    
    async def initialize(self):
        """Initialize all storage clients."""
        await self.postgres.connect()
        await self.weaviate.connect()
        await self.neo4j.connect()
        
        # Initialize embedding service
        await self.embedding_service.initialize()
        
        # Initialize result fusion with storage clients
        await self.result_fusion.initialize(
            postgres=self.postgres,
            weaviate=self.weaviate,
            neo4j=self.neo4j
        )
    
    async def close(self):
        """Close all storage clients."""
        await self.result_fusion.close()
        await self.embedding_service.close()
        await self.postgres.disconnect()
        await self.weaviate.disconnect()
        await self.neo4j.disconnect()
    
    # ═══════════════════════════════════════════════════════════════════════
    # Audit Logging
    # ═══════════════════════════════════════════════════════════════════════
    
    async def enable_audit(self) -> None:
        """Enable audit logging for all operations.
        
        Creates an AuditLogger instance connected to PostgreSQL.
        Call this after initialize() when database connection is ready.
        """
        self.audit_logger = AuditLogger(self.postgres)
        self._audit_enabled = True
    
    async def disable_audit(self) -> None:
        """Disable audit logging."""
        self._audit_enabled = False
        self.audit_logger = None
    
    def is_audit_enabled(self) -> bool:
        """Check if audit is enabled."""
        return self._audit_enabled
    
    # ═══════════════════════════════════════════════════════════════════════
    # Memory Storage
    # ═══════════════════════════════════════════════════════════════════════
    
    async def store_memory(
        self,
        content: str,
        memory_class: MemoryClass,
        agent_id: str,
        session_id: str,
        message_id: str,
        visibility: str = 'team',
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Store a memory in the GraphRAG system.
        
        Args:
            content: The memory content
            memory_class: Type of memory (episodic, semantic, decision, etc.)
            agent_id: Which agent owns this memory
            session_id: Source session ID
            message_id: Source message ID
            visibility: 'agent', 'team', 'tenant', 'public'
            metadata: Additional metadata
            
        Returns:
            Memory ID if stored successfully, None if blocked by policy
        """
        # Create memory object
        memory = AgentMemory(
            id=uuid.uuid4(),
            memory_class=memory_class,
            content=content,
            visibility=visibility,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
        )
        
        # Set agent-specific fields
        memory.agent_id = agent_id
        memory.source_session_id = session_id
        memory.source_message_id = message_id
        
        # Check write policy
        should_block, reason = self.write_policy.should_block_promotion(memory)
        if should_block:
            # Still persist to raw history
            await self.ingestion.persist_raw_extraction(memory)
            return None
        
        # Ingest through pipeline
        memory_id = await self.ingestion.ingest(memory)
        result_id = str(memory_id) if memory_id else None
        
        # Log audit event if enabled
        if self._audit_enabled and self.audit_logger and result_id:
            import uuid
            await self.audit_logger.log_create(
                actor_id=agent_id,
                resource_type="memory_item",
                resource_id=result_id,
                after_state={
                    "content": content,
                    "memory_class": str(memory_class),
                    "visibility": visibility,
                    "session_id": session_id,
                },
                correlation_id=str(uuid.uuid4()),
                metadata={"reason": "store_memory"},
            )
        
        return result_id
    
    # ═══════════════════════════════════════════════════════════════════════
    # Memory Retrieval
    # ═══════════════════════════════════════════════════════════════════════
    
    async def retrieve_memories(
        self,
        query: str,
        agent_id: str,
        team_member_ids: List[str],
        intent: Optional[Intent] = None,
        limit: int = 10
    ) -> List[Memory]:
        """
        Retrieve memories relevant to a query.
        
        Uses intent-based routing:
        - fact_lookup → semantic search (Weaviate)
        - decision_recall → decision memories (PostgreSQL)
        - relationship_query → graph traversal (Neo4j)
        - change_detection → supersession chain (PostgreSQL)
        - ownership_query → agent-filtered (PostgreSQL)
        - procedural_recall → procedural memories (PostgreSQL + Weaviate)
        
        Args:
            query: The search query
            agent_id: Agent making the query
            team_member_ids: Team member IDs for visibility
            intent: Optional pre-classified intent
            limit: Maximum results
            
        Returns:
            List of accessible memories
        """
        # Classify intent if not provided
        if intent is None:
            intent = self.intent_classifier.classify(query)
        
        # Get retrieval plan
        plan = self.retrieval_policy.plan(intent, query)
        
        # Execute retrieval
        raw_results = await plan.execute()
        
        # Fuse results
        fused = self.result_fusion.fuse(raw_results, intent)
        
        # Filter by agent visibility
        accessible = self.agent_policy.filter_memories_for_agent(
            fused, agent_id, team_member_ids
        )
        
        return accessible[:limit]
    
    async def get_decision_chain(
        self,
        decision_id: str
    ) -> List[Memory]:
        """
        Get the full supersession chain for a decision.
        
        Returns decisions from oldest to newest.
        """
        chain = []
        current_id = decision_id
        
        while current_id:
            memory = await self.postgres.get_memory(current_id)
            if memory:
                chain.append(memory)
                current_id = memory.superseded_by
            else:
                break
        
        return list(reversed(chain))
    
    async def get_agent_context(
        self,
        agent_id: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get memory context for an agent session.
        
        Returns:
            - Recent decisions
            - Active tasks
            - Relevant facts
            - Relationship context
        """
        context = {
            'decisions': [],
            'facts': [],
            'relationships': [],
            'recent_sessions': []
        }
        
        # Get recent decisions
        context['decisions'] = await self.postgres.get_agent_memories(
            agent_id=agent_id,
            memory_class='decision',
            limit=5,
        )
        
        # Get active facts
        context['facts'] = await self.postgres.get_agent_memories(
            agent_id=agent_id,
            memory_class='semantic',
            limit=10,
        )
        
        # Get relationships from Neo4j
        try:
            context['relationships'] = await self.neo4j.get_agent_relationships(agent_id)
        except Exception:
            context['relationships'] = []
        
        return context
    
    # ═══════════════════════════════════════════════════════════════════════
    # Memory Lifecycle
    # ═══════════════════════════════════════════════════════════════════════
    
    async def supersede_memory(
        self,
        old_memory_id: str,
        new_content: str,
        reason: str,
        actor_id: str = "system",
    ) -> str:
        """
        Supersede an old memory with a new one.
        
        Creates the new memory and links the old one via superseded_by.
        
        Args:
            old_memory_id: ID of the memory to supersede
            new_content: New content for the replacement
            reason: Reason for supersession
            actor_id: Who is performing the supersession
            
        Returns:
            ID of the new memory item
        """
        from uuid import UUID
        
        # Get old item for audit
        old_item = await self.postgres.get_memory_item(UUID(old_memory_id))
        old_state = None
        if old_item:
            old_state = {"content": old_item.content, "confidence": old_item.confidence}
        
        new_item = await self.postgres.supersede_memory_item(
            original_id=UUID(old_memory_id),
            new_content=new_content,
            reason=reason,
        )
        result_id = str(new_item.id) if new_item else None
        
        # Log audit event if enabled
        if self._audit_enabled and self.audit_logger and result_id:
            import uuid
            await self.audit_logger.log_supersede(
                actor_id=actor_id,
                resource_type="memory_item",
                old_resource_id=old_memory_id,
                new_resource_id=result_id,
                old_state=old_state,
                new_state={"content": new_content},
                reason=reason,
                correlation_id=str(uuid.uuid4()),
            )
        
        return result_id
    
    async def expire_memory(
        self,
        memory_id: str,
        reason: str = "expired",
        actor_id: str = "system",
    ):
        """Mark a memory as expired.
        
        Args:
            memory_id: ID of the memory to expire
            reason: Reason for expiration
            actor_id: Who is expiring the memory
        """
        from uuid import UUID
        
        # Get old item for audit
        old_item = await self.postgres.get_memory_item(UUID(memory_id))
        old_state = None
        if old_item:
            old_state = {"content": old_item.content, "is_current": old_item.is_current}
        
        async with self.postgres._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_items
                SET is_current = FALSE, 
                    valid_to = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                UUID(memory_id)
            )
        
        # Log audit event if enabled
        if self._audit_enabled and self.audit_logger:
            import uuid
            await self.audit_logger.log(
                actor_id=actor_id,
                action="EXPIRE",
                resource_type="memory_item",
                resource_id=memory_id,
                before_state=old_state,
                after_state={"is_current": False, "valid_to": "NOW()"},
                correlation_id=str(uuid.uuid4()),
                metadata={"reason": reason},
            )