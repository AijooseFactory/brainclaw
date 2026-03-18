"""Neo4j client for relationship graph storage and traversal."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any, Dict
import json
import time

# Observability imports (optional - graceful degradation)
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from openclaw_memory.observability.logging import get_logger
    from openclaw_memory.observability.metrics import MetricsHelper
    from openclaw_memory.observability.telemetry import traced_async
    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False
    # Placeholder when observability not available
    def traced_async(operation_name: str, attributes: dict = None):
        """No-op decorator when observability not available."""
        def decorator(func):
            return func
        return decorator

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import AuthError, ServiceUnavailable

# Get logger
logger = get_logger("openclaw.storage.neo4j") if _OBSERVABILITY_AVAILABLE else None


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


# Node labels based on spec
NODE_LABELS = {
    "USER": "User",
    "AGENT": "Agent", 
    "SESSION": "Session",
    "MESSAGE": "Message",
    "CHUNK": "Chunk",
    "SUMMARY": "Summary",
    "ENTITY": "Entity",
    "CONCEPT": "Concept",
    "TASK": "Task",
    "DECISION": "Decision",
    "CLAIM": "Claim",
    "ISSUE": "Issue",
    "DOCUMENT": "Document",
    "TOOL_CALL": "ToolCall",
    "TEMPORAL_CONTEXT": "TemporalContext",
}

# Relationship types based on spec
RELATIONSHIP_TYPES = {
    # Content relationships
    "SAID_IN": "SAID_IN",
    "PART_OF": "PART_OF",
    "SUMMARIZES": "SUMMARIZES",
    
    # Memory relationships
    "MENTIONS": "MENTIONS",
    "REFERRED_TO": "REFERRED_TO",
    "REFERS_TO": "REFERS_TO",
    "DERIVED_FROM": "DERIVED_FROM",
    "SUPPORTS": "SUPPORTS",
    "CONTRADICTS": "CONTRADICTS",
    
    # Decision relationships
    "DECIDED_BY": "DECIDED_BY",
    "PARTICIPANT": "PARTICIPANT",
    "DECIDED_ABOUT": "DECIDED_ABOUT",
    "DEPENDS_ON": "DEPENDS_ON",
    "ALTERNATIVE_TO": "ALTERNATIVE_TO",
    "SUPERSEDES": "SUPERSEDES",
    "REVERSES": "REVERSES",
    "SUPPORTED_BY": "SUPPORTED_BY",
    
    # Task relationships
    "ASSIGNED_TO": "ASSIGNED_TO",
    "RELATED_TO": "RELATED_TO",
    "ABOUT": "ABOUT",
    
    # Session relationships
    "INVOLVED": "INVOLVED",
    "DISCUSSED": "DISCUSSED",
    "CREATED": "CREATED",
    
    # Temporal relationships
    "VALID_AT": "VALID_AT",
    "SUPERSEDED_AT": "SUPERSEDED_AT",
    "EXPIRES_AT": "EXPIRES_AT",
    
    # Provenance relationships
    "EXTRACTED_FROM": "EXTRACTED_FROM",
    "EXTRACTED_BY": "EXTRACTED_BY",
    
    # Tool relationships
    "ACCESSED": "ACCESSED",
    "MODIFIED": "MODIFIED",
    "USED_TOOL": "USED_TOOL",
}


@dataclass
class UserNode:
    """User node for Neo4j."""
    id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    name: str = ""
    email: Optional[str] = None
    external_id: Optional[str] = None
    preferences: Dict[str, Any] = field(default_factory=dict)
    agent_id: Optional[uuid.UUID] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    neo4j_id: Optional[str] = None

    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid.uuid4()
        
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


@dataclass
class AgentNode:
    """Agent node for Neo4j."""
    id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    name: str = ""
    role: Optional[str] = None
    model: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    agent_id: Optional[uuid.UUID] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    neo4j_id: Optional[str] = None

    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid.uuid4()
        
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


@dataclass
class SessionNode:
    """Session node for Neo4j."""
    id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    channel: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    agent_id: Optional[uuid.UUID] = None
    neo4j_id: Optional[str] = None

    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid.uuid4()
        
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


@dataclass
class MessageNode:
    """Message node for Neo4j."""
    id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    role: str = "user"
    content: str = ""
    tokens_used: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    agent_id: Optional[uuid.UUID] = None
    neo4j_id: Optional[str] = None

    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid.uuid4()
        
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = uuid.UUID(current_agent_id)
            except Exception:
                pass


@dataclass
class EntityNode:
    """Entity node for Neo4j."""
    id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    entity_type: str = ""
    name: str = ""
    canonical_name: Optional[str] = None
    description: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    confidence: float = 0.5
    agent_id: Optional[uuid.UUID] = None
    neo4j_id: Optional[str] = None

    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid.uuid4()
        
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


@dataclass
class DecisionNode:
    """Decision node for Neo4j."""
    id: Optional[uuid.UUID] = None
    memory_item_id: Optional[uuid.UUID] = None
    summary: str = ""
    decision_type: Optional[str] = None
    rationale: Optional[str] = None
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "active"
    confidence: float = 0.5
    valid_from: datetime = field(default_factory=datetime.utcnow)
    valid_to: Optional[datetime] = None
    decided_by: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    neo4j_id: Optional[str] = None

    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid.uuid4()
        
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = uuid.UUID(current_agent_id)
            except Exception:
                pass


@dataclass
class ClaimNode:
    """Claim node for Neo4j."""
    id: Optional[uuid.UUID] = None
    memory_item_id: Optional[uuid.UUID] = None
    content: str = ""
    confidence: float = 0.5
    source_message_id: Optional[uuid.UUID] = None
    extracted_by: Optional[str] = None
    valid_from: datetime = field(default_factory=datetime.utcnow)
    valid_to: Optional[datetime] = None
    agent_id: Optional[uuid.UUID] = None
    neo4j_id: Optional[str] = None

    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid.uuid4()
        
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = uuid.UUID(current_agent_id)
            except Exception:
                pass


@dataclass
class ToolCallNode:
    """ToolCall node for Neo4j."""
    id: Optional[uuid.UUID] = None
    message_id: Optional[uuid.UUID] = None
    tool_name: str = ""
    success: bool = False
    execution_time_ms: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    agent_id: Optional[uuid.UUID] = None
    neo4j_id: Optional[str] = None

    def __post_init__(self):
        """Initialize IDs and timestamps if not provided."""
        if self.id is None:
            self.id = uuid.uuid4()
        
        # Automatically set agent_id from the verified security context if not provided
        if self.agent_id is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    self.agent_id = uuid.UUID(current_agent_id)
            except Exception:
                pass


class Neo4jClient:
    """Async Neo4j client for relationship graph storage.
    
    Provides:
    - Node creation: User, Agent, Session, Message, Chunk, Summary, 
      Entity, Concept, Task, Decision, Claim, Issue, Document, ToolCall
    - Relationship creation: All relationship types from spec
    - Graph traversal queries for relationship retrieval
    - Constraint and index management
    
    Uses the configured Neo4j database for relationship storage.
    """
    
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "",
        database: str = "neo4j",
        max_connection_pool_size: int = 50,
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.max_connection_pool_size = max_connection_pool_size
        self._driver: Optional[AsyncDriver] = None
    
    @traced_async("neo4j.connect", {"component": "storage"})
    async def connect(self) -> None:
        """Initialize Neo4j driver connection."""
        self._driver = AsyncGraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
            max_connection_pool_size=self.max_connection_pool_size,
        )
        # Verify connectivity
        await self._driver.verify_connectivity()
    
    @traced_async("neo4j.disconnect", {"component": "storage"})
    async def disconnect(self) -> None:
        """Close Neo4j driver."""
        if self._driver:
            await self._driver.close()
            self._driver = None
    
    async def is_connected(self) -> bool:
        """Check if connected to Neo4j."""
        if not self._driver:
            return False
        try:
            await self._driver.verify_connectivity()
            return True
        except Exception:
            return False
    
    async def create_constraints(self) -> None:
        """Create uniqueness constraints for key nodes."""
        constraints = [
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT agent_id_unique IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT session_id_unique IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT message_id_unique IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT decision_id_unique IF NOT EXISTS FOR (d:Decision) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT claim_id_unique IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT toolcall_id_unique IF NOT EXISTS FOR (t:ToolCall) REQUIRE t.id IS UNIQUE",
        ]
        
        async with self._driver.session(database=self.database) as session:
            for constraint in constraints:
                try:
                    await session.run(constraint)
                except Exception:
                    pass  # Constraint may already exist
    
    async def create_indexes(self) -> None:
        """Create indexes for performance."""
        indexes = [
            "CREATE INDEX tenant_idx IF NOT EXISTS FOR (n) ON (n.tenant_id)",
            "CREATE INDEX entity_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
            "CREATE INDEX entity_name_idx IF NOT EXISTS FOR (e:Entity) ON (e.name)",
            "CREATE INDEX decision_status_idx IF NOT EXISTS FOR (d:Decision) ON (d.status)",
            "CREATE INDEX session_channel_idx IF NOT EXISTS FOR (s:Session) ON (s.channel)",
        ]
        
        async with self._driver.session(database=self.database) as session:
            for index in indexes:
                try:
                    await session.run(index)
                except Exception:
                    pass  # Index may already exist
    
    # User operations
    async def create_user(self, user: UserNode) -> str:
        """Create a User node."""
        if user.id is None:
            user.id = uuid.uuid4()
        
        query = """
            CREATE (u:User {
                id: $id,
                tenant_id: $tenant_id,
                name: $name,
                email: $email,
                external_id: $external_id,
                preferences: $preferences,
                agent_id: $agent_id,
                created_at: $created_at
            })
            RETURN elementId(u) as neo4j_id
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                id=str(user.id),
                tenant_id=str(user.tenant_id) if user.tenant_id else None,
                name=user.name,
                email=user.email,
                external_id=user.external_id,
                preferences=json.dumps(user.preferences),
                agent_id=str(user.agent_id) if user.agent_id else None,
                created_at=user.created_at.isoformat(),
            )
            record = await result.single()
            return record["neo4j_id"] if record else None
    
    async def get_user(self, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get a User node by ID."""
        query = "MATCH (u:User {id: $id}) RETURN u"
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(query, id=str(user_id))
            record = await result.single()
            if record:
                return dict(record["u"])
            return None
    
    # Agent operations
    async def create_agent(self, agent: AgentNode) -> str:
        """Create an Agent node."""
        if agent.id is None:
            agent.id = uuid.uuid4()
        
        query = """
            CREATE (a:Agent {
                id: $id,
                tenant_id: $tenant_id,
                name: $name,
                role: $role,
                model: $model,
                capabilities: $capabilities,
                agent_id: $agent_id,
                created_at: $created_at
            })
            RETURN elementId(a) as neo4j_id
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                id=str(agent.id),
                tenant_id=str(agent.tenant_id) if agent.tenant_id else None,
                name=agent.name,
                role=agent.role,
                model=agent.model,
                capabilities=agent.capabilities,
                agent_id=str(agent.agent_id) if agent.agent_id else None,
                created_at=agent.created_at.isoformat(),
            )
            record = await result.single()
            return record["neo4j_id"] if record else None
    
    # Session operations
    async def create_session(self, session: SessionNode) -> str:
        """Create a Session node."""
        if session.id is None:
            session.id = uuid.uuid4()
        
        query = """
            CREATE (s:Session {
                id: $id,
                tenant_id: $tenant_id,
                channel: $channel,
                started_at: $started_at,
                ended_at: $ended_at,
                agent_id: $agent_id,
                metadata: $metadata
            })
            RETURN elementId(s) as neo4j_id
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                id=str(session.id),
                tenant_id=str(session.tenant_id) if session.tenant_id else None,
                channel=session.channel,
                started_at=session.started_at.isoformat(),
                ended_at=session.ended_at.isoformat() if session.ended_at else None,
                agent_id=str(session.agent_id) if session.agent_id else None,
                metadata=json.dumps(session.metadata),
            )
            record = await result.single()
            return record["neo4j_id"] if record else None
    
    # Message operations
    async def create_message(self, message: MessageNode) -> str:
        """Create a Message node."""
        if message.id is None:
            message.id = uuid.uuid4()
        
        query = """
            CREATE (m:Message {
                id: $id,
                session_id: $session_id,
                role: $role,
                content: $content,
                tokens_used: $tokens_used,
                agent_id: $agent_id,
                created_at: $created_at
            })
            RETURN elementId(m) as neo4j_id
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                id=str(message.id),
                session_id=str(message.session_id) if message.session_id else None,
                role=message.role,
                content=message.content,
                tokens_used=message.tokens_used,
                agent_id=str(message.agent_id) if message.agent_id else None,
                created_at=message.created_at.isoformat(),
            )
            record = await result.single()
            return record["neo4j_id"] if record else None
    
    async def create_message_relationship(
        self,
        message_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Create SAID_IN relationship from Message to Session."""
        query = """
            MATCH (m:Message {id: $message_id})
            MATCH (s:Session {id: $session_id})
            CREATE (m)-[:SAID_IN]->(s)
        """
        
        async with self._driver.session(database=self.database) as session:
            await session.run(
                query,
                message_id=str(message_id),
                session_id=str(session_id),
            )
    
    # Entity operations
    async def create_entity(self, entity: EntityNode) -> str:
        """Create an Entity node."""
        if entity.id is None:
            entity.id = uuid.uuid4()
        
        query = """
            CREATE (e:Entity {
                id: $id,
                tenant_id: $tenant_id,
                entity_type: $entity_type,
                name: $name,
                canonical_name: $canonical_name,
                description: $description,
                properties: $properties,
                aliases: $aliases,
                confidence: $confidence,
                agent_id: $agent_id
            })
            RETURN elementId(e) as neo4j_id
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                id=str(entity.id),
                tenant_id=str(entity.tenant_id) if entity.tenant_id else None,
                entity_type=entity.entity_type,
                name=entity.name,
                canonical_name=entity.canonical_name,
                description=entity.description,
                properties=json.dumps(entity.properties),
                aliases=entity.aliases,
                confidence=entity.confidence,
                agent_id=str(entity.agent_id) if entity.agent_id else None,
            )
            record = await result.single()
            return record["neo4j_id"] if record else None
    
    async def get_entity(
        self,
        tenant_id: uuid.UUID,
        entity_type: str,
        canonical_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Get an Entity by type and canonical name."""
        query = """
            MATCH (e:Entity {tenant_id: $tenant_id, entity_type: $entity_type, canonical_name: $canonical_name})
            RETURN e
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                tenant_id=str(tenant_id),
                entity_type=entity_type,
                canonical_name=canonical_name,
            )
            record = await result.single()
            if record:
                return dict(record["e"])
            return None
    
    async def create_entity_relationship(
        self,
        source_entity_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a relationship between two entities."""
        valid_types = ["MENTIONS", "REFERRED_TO", "DEPENDS_ON", "RELATED_TO"]
        if relationship_type not in valid_types:
            raise ValueError(f"Invalid relationship type: {relationship_type}")
        
        query = f"""
            MATCH (a:Entity {{id: $source_id}})
            MATCH (b:Entity {{id: $target_id}})
            CREATE (a)-[r:{relationship_type} $props]->(b)
        """
        
        async with self._driver.session(database=self.database) as session:
            await session.run(
                query,
                source_id=str(source_entity_id),
                target_id=str(target_entity_id),
                props=properties or {},
            )
    
    # Decision operations
    async def create_decision(self, decision: DecisionNode) -> str:
        """Create a Decision node."""
        if decision.id is None:
            decision.id = uuid.uuid4()
        
        query = """
            CREATE (d:Decision {
                id: $id,
                memory_item_id: $memory_item_id,
                summary: $summary,
                decision_type: $decision_type,
                rationale: $rationale,
                alternatives: $alternatives,
                status: $status,
                confidence: $confidence,
                valid_from: $valid_from,
                valid_to: $valid_to,
                decided_by: $decided_by,
                agent_id: $agent_id,
                created_at: $created_at
            })
            RETURN elementId(d) as neo4j_id
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                id=str(decision.id),
                memory_item_id=str(decision.memory_item_id) if decision.memory_item_id else None,
                summary=decision.summary,
                decision_type=decision.decision_type,
                rationale=decision.rationale,
                alternatives=json.dumps(decision.alternatives),
                status=decision.status,
                confidence=decision.confidence,
                valid_from=decision.valid_from.isoformat(),
                valid_to=decision.valid_to.isoformat() if decision.valid_to else None,
                decided_by=str(decision.decided_by) if decision.decided_by else None,
                agent_id=str(decision.agent_id) if decision.agent_id else None,
                created_at=decision.created_at.isoformat(),
            )
            record = await result.single()
            return record["neo4j_id"] if record else None
    
    async def get_active_decisions(
        self,
        tenant_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Get all active decisions for a tenant."""
        query = """
            MATCH (d:Decision {tenant_id: $tenant_id, status: 'active'})
            RETURN d
            ORDER BY d.created_at DESC
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(query, tenant_id=str(tenant_id))
            return [dict(record["d"]) async for record in result]
    
    # Claim operations
    async def create_claim(self, claim: ClaimNode) -> str:
        """Create a Claim node."""
        if claim.id is None:
            claim.id = uuid.uuid4()
        
        query = """
            CREATE (c:Claim {
                id: $id,
                memory_item_id: $memory_item_id,
                content: $content,
                confidence: $confidence,
                source_message_id: $source_message_id,
                extracted_by: $extracted_by,
                valid_from: $valid_from,
                valid_to: $valid_to,
                agent_id: $agent_id,
                superseded_by: $superseded_by
            })
            RETURN elementId(c) as neo4j_id
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                id=str(claim.id),
                memory_item_id=str(claim.memory_item_id) if claim.memory_item_id else None,
                content=claim.content,
                confidence=claim.confidence,
                source_message_id=str(claim.source_message_id) if claim.source_message_id else None,
                extracted_by=claim.extracted_by,
                valid_from=claim.valid_from.isoformat(),
                valid_to=claim.valid_to.isoformat() if claim.valid_to else None,
                agent_id=str(claim.agent_id) if claim.agent_id else None,
                superseded_by=str(claim.superseded_by) if claim.superseded_by else None,
            )
            record = await result.single()
            return record["neo4j_id"] if record else None
    
    # ToolCall operations
    async def create_tool_call(self, tool_call: ToolCallNode) -> str:
        """Create a ToolCall node."""
        if tool_call.id is None:
            tool_call.id = uuid.uuid4()
        
        query = """
            CREATE (t:ToolCall {
                id: $id,
                message_id: $message_id,
                tool_name: $tool_name,
                success: $success,
                execution_time_ms: $execution_time_ms,
                agent_id: $agent_id,
                created_at: $created_at
            })
            RETURN elementId(t) as neo4j_id
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                id=str(tool_call.id),
                message_id=str(tool_call.message_id) if tool_call.message_id else None,
                tool_name=tool_call.tool_name,
                success=tool_call.success,
                execution_time_ms=tool_call.execution_time_ms,
                agent_id=str(tool_call.agent_id) if tool_call.agent_id else None,
                created_at=tool_call.created_at.isoformat(),
            )
            record = await result.single()
            return record["neo4j_id"] if record else None
    
    # Graph traversals
    @traced_async("neo4j.traverse", {"component": "storage"})
    async def traverse_entity_relationships(
        self,
        entity_id: uuid.UUID,
        agent_id: Optional[uuid.UUID] = None,
        depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """Traverse relationships from an entity up to specified depth."""
        tracer = trace.get_tracer(__name__) if _OBSERVABILITY_AVAILABLE else None
        
        with tracer.start_as_current_span("neo4j.traverse") if tracer else _FakeSpan() as span:
            if tracer:
                span.set_attribute("neo4j.operation", "traverse_entity_relationships")
                span.set_attribute("neo4j.entity_id", str(entity_id))
                span.set_attribute("neo4j.depth", depth)
            
            start_time = time.perf_counter() if _OBSERVABILITY_AVAILABLE else 0
            
            query = f"""
                MATCH path = (e:Entity {{id: $id, agent_id: $agent_id}})-[{':'.join(['r'] * depth)}*1..{depth}]->(related)
                WHERE related.agent_id = $agent_id OR related.visibility_scope = 'public'
                RETURN path
                LIMIT 100
            """
            
            async with self._driver.session(database=self.database) as session:
                result = await session.run(query, id=str(entity_id), agent_id=str(agent_id) if agent_id else None)
                paths = []
                async for record in result:
                    path = record["path"]
                    nodes = []
                    for node in path.nodes:
                        nodes.append({"label": list(node.labels)[0] if node.labels else "Unknown", "properties": dict(node)})
                    paths.append({"nodes": nodes, "relationships": len(path.relationships)})
            
            # Record metrics
            if _OBSERVABILITY_AVAILABLE:
                duration = time.perf_counter() - start_time
                
                if tracer and span:
                    span.set_attribute("neo4j.result_count", len(paths))
                    span.set_attribute("neo4j.duration_ms", duration * 1000)
                    span.set_status(Status(StatusCode.OK))
                
                MetricsHelper.record_memory_operation(
                    operation="traverse",
                    memory_class="entity",
                    status="success",
                    tenant_id="default",
                )
                MetricsHelper.record_latency("traverse", "neo4j", duration)
            
            return paths
    
    async def get_decision_relationships(
        self,
        decision_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Get all relationships for a decision."""
        query = """
            MATCH (d:Decision {id: $id})
            OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(c:Claim)
            OPTIONAL MATCH (d)-[:DECIDED_ABOUT]->(e:Entity)
            OPTIONAL MATCH (d)-[:DECIDED_BY]->(u:User)
            OPTIONAL MATCH (d)-[:SUPERSEDES]->(prev:Decision)
            OPTIONAL MATCH (d)-[:REVERSES]->(reversed:Decision)
            RETURN d, collect(DISTINCT c) as supporting_claims, 
                   collect(DISTINCT e) as entities, 
                   collect(DISTINCT u) as decided_by_user,
                   collect(DISTINCT prev) as supersedes,
                   collect(DISTINCT reversed) as reverses
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(query, id=str(decision_id))
            record = await result.single()
            if record:
                return {
                    "decision": dict(record["d"]),
                    "supporting_claims": [dict(c) for c in record["supporting_claims"] if c],
                    "entities": [dict(e) for e in record["entities"] if e],
                    "decided_by": [dict(u) for u in record["decided_by_user"] if u],
                    "supersedes": [dict(p) for p in record["supersedes"] if p],
                    "reverses": [dict(r) for r in record["reverses"] if r],
                }
            return None
    
    async def get_session_context(
        self,
        session_id: uuid.UUID,
        agent_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Get full context for a session (messages, entities, decisions)."""
        query = """
            MATCH (s:Session {id: $session_id, agent_id: $agent_id})
            OPTIONAL MATCH (s)<-[:INVOLVED]-(u:User)
            OPTIONAL MATCH (s)<-[:INVOLVED]-(a:Agent)
            OPTIONAL MATCH (s)<-[:SAID_IN]-(m:Message)
            OPTIONAL MATCH (s)<-[:DISCUSSED]-(e:Entity)
            OPTIONAL MATCH (s)<-[:DECIDED]-(d:Decision)
            RETURN s, collect(DISTINCT u) as users, 
                   collect(DISTINCT a) as agents,
                   collect(DISTINCT m) as messages,
                   collect(DISTINCT e) as entities,
                   collect(DISTINCT d) as decisions
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(query, session_id=str(session_id), agent_id=str(agent_id) if agent_id else None)
            record = await result.single()
            if record:
                return {
                    "session": dict(record["s"]),
                    "users": [dict(u) for u in record["users"] if u],
                    "agents": [dict(a) for a in record["agents"] if a],
                    "messages": [dict(m) for m in record["messages"] if m],
                    "entities": [dict(e) for e in record["entities"] if e],
                    "decisions": [dict(d) for d in record["decisions"] if d],
                }
            return None
    
    async def delete_node(self, node_id: uuid.UUID, label: str) -> bool:
        """Delete a node by ID and label."""
        query = f"""
            MATCH (n:{label} {{id: $id}})
            DETACH DELETE n
        """
        
        async with self._driver.session(database=self.database) as session:
            result = await session.run(query, id=str(node_id))
            return True
    
    @traced_async("neo4j.query", {"component": "storage"})
    async def execute_cypher(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a raw Cypher query."""
        async with self._driver.session(database=self.database) as session:
            result = await session.run(query, parameters or {})
            return [dict(record) async for record in result]
