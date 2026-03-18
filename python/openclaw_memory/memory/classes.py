"""
Memory Classes for the BrainClaw Memory System.

Defines all 7 memory classes with their properties and behaviors:
- Episodic: Conversations, sessions, tool runs (temporal + semantic)
- Semantic: Facts, concepts, domain knowledge (semantic + graph)
- Procedural: Workflows, patterns, playbooks (semantic + temporal)
- Decision: What decided, why, alternatives (graph traversal + temporal)
- Identity: Persona, guardrails, preferences (key-value lookup)
- Relational: People, projects, dependencies (graph)
- Summary: Session/topic/conversation summaries (semantic)
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from uuid import UUID, uuid4


class MemoryClass(str, Enum):
    """Enumeration of all memory classes with storage mappings."""
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    DECISION = "decision"
    IDENTITY = "identity"
    RELATIONAL = "relational"
    SUMMARY = "summary"

    @property
    def primary_index(self) -> List[str]:
        """Primary storage indices for this memory class."""
        indices = {
            MemoryClass.EPISODIC: ["postgresql", "weaviate"],
            MemoryClass.SEMANTIC: ["weaviate", "neo4j"],
            MemoryClass.PROCEDURAL: ["postgresql", "weaviate"],
            MemoryClass.DECISION: ["postgresql", "neo4j"],
            MemoryClass.IDENTITY: ["postgresql"],
            MemoryClass.RELATIONAL: ["neo4j"],
            MemoryClass.SUMMARY: ["postgresql", "weaviate"],
        }
        return indices.get(self, ["postgresql"])

    @property
    def retrieval_pattern(self) -> str:
        """Retrieval pattern for this memory class."""
        patterns = {
            MemoryClass.EPISODIC: "temporal + semantic",
            MemoryClass.SEMANTIC: "semantic + graph",
            MemoryClass.PROCEDURAL: "semantic + temporal",
            MemoryClass.DECISION: "graph traversal + temporal",
            MemoryClass.IDENTITY: "key-value lookup",
            MemoryClass.RELATIONAL: "graph traversal",
            MemoryClass.SUMMARY: "semantic",
        }
        return patterns.get(self, "semantic")

    @property
    def memory_types(self) -> List[str]:
        """Valid memory types for this class."""
        types = {
            MemoryClass.EPISODIC: ["conversation", "session", "tool_run", "event"],
            MemoryClass.SEMANTIC: ["fact", "concept", "domain_knowledge", "rule"],
            MemoryClass.PROCEDURAL: ["workflow", "pattern", "playbook", "procedure"],
            MemoryClass.DECISION: ["architectural", "process", "technical", "preference"],
            MemoryClass.IDENTITY: ["persona", "guardrail", "preference", "capability"],
            MemoryClass.RELATIONAL: ["person", "project", "system", "dependency"],
            MemoryClass.SUMMARY: ["session", "conversation", "topic", "project"],
        }
        return types.get(self, [])


class MemoryType(str, Enum):
    """Specific memory types for more granular classification."""
    # Episodic types
    CONVERSATION = "conversation"
    SESSION = "session"
    TOOL_RUN = "tool_run"
    EVENT = "event"

    # Semantic types
    FACT = "fact"
    CONCEPT = "concept"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    RULE = "rule"

    # Procedural types
    WORKFLOW = "workflow"
    PATTERN = "pattern"
    PLAYBOOK = "playbook"
    PROCEDURE = "procedure"

    # Decision types
    ARCHITECTURAL = "architectural"
    PROCESS = "process"
    TECHNICAL = "technical"
    PREFERENCE = "preference"

    # Identity types
    PERSONA = "persona"
    GUARDRAIL = "guardrail"
    CAPABILITY = "capability"

    # Relational types
    PERSON = "person"
    PROJECT = "project"
    SYSTEM = "system"
    DEPENDENCY = "dependency"

    # Summary types
    SESSION_SUMMARY = "session"
    CONVERSATION_SUMMARY = "conversation"
    TOPIC_SUMMARY = "topic"


class DecisionStatus(str, Enum):
    """Status of a decision memory."""
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class MemoryState(str, Enum):
    """Enumeration of memory lifecycle states."""
    RAW = "raw"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    ARCHIVED = "archived"

    def is_valid_transition(self, new_state: "MemoryState") -> bool:
        """Check if transition to new_state is valid from current state."""
        # Allow same-state transitions (idempotent)
        if new_state == self:
            return True
            
        valid_transitions = {
            MemoryState.RAW: [MemoryState.PENDING, MemoryState.ACTIVE],
            MemoryState.PENDING: [MemoryState.CONFIRMED, MemoryState.ACTIVE],
            MemoryState.CONFIRMED: [MemoryState.ACTIVE],
            MemoryState.ACTIVE: [MemoryState.SUPERSEDED, MemoryState.EXPIRED],
            MemoryState.SUPERSEDED: [MemoryState.ARCHIVED],
            MemoryState.EXPIRED: [MemoryState.ARCHIVED],
            MemoryState.ARCHIVED: [],  # Terminal state
        }
        return new_state in valid_transitions.get(self, [])


@dataclass
class Memory:
    """
    Base Memory dataclass with common fields for all memory types.

    This is the core data structure for all memory items in the system.
    """
    id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None  # Added for agent-specific memory isolation
    memory_class: MemoryClass = MemoryClass.SEMANTIC
    memory_type: Optional[str] = None
    status: MemoryState = MemoryState.ACTIVE

    # Content
    content: str = ""
    content_embedding: Optional[List[float]] = None

    # Provenance (ALL REQUIRED for traceability)
    source_session_id: Optional[UUID] = None
    source_message_id: Optional[UUID] = None
    extraction_timestamp: Optional[datetime] = None
    extractor_name: str = "llm"  # Which extractor produced this
    extractor_version: str = "1.0"  # Version of extractor
    confidence: float = 0.5

    # Legacy provenance fields (kept for backwards compatibility)
    source_tool_call_id: Optional[UUID] = None
    extracted_by: str = "llm"
    extraction_method: Optional[str] = None
    extraction_confidence: Optional[float] = 1.0
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)

    # Trust Model
    user_confirmed: bool = False
    user_confirmed_at: Optional[datetime] = None
    user_confirmed_by: Optional[UUID] = None

    # Temporal (Validity Window)
    valid_from: datetime = field(default_factory=datetime.utcnow)
    valid_to: Optional[datetime] = None
    is_current: bool = True
    superseded_by: Optional[UUID] = None
    supersession_reason: Optional[str] = None

    # Governance
    visibility_scope: str = "tenant"
    access_control: Dict[str, Any] = field(default_factory=dict)
    retention_policy: str = "default"
    retention_until: Optional[datetime] = None

    # Indexing Status (Sync Tracking)
    weaviate_id: Optional[str] = None
    neo4j_id: Optional[str] = None
    weaviate_synced: bool = False
    neo4j_synced: bool = False
    weaviate_synced_at: Optional[datetime] = None
    neo4j_synced_at: Optional[datetime] = None
    sync_version: int = 1

    # Provenance Hash Chain
    prev_hash: Optional[bytes] = None
    row_hash: Optional[bytes] = None

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Initialize ID and timestamps if not provided."""
        if self.id is None:
            self.id = uuid4()
        if self.extraction_timestamp is None:
            self.extraction_timestamp = datetime.utcnow()
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()
        if self.valid_from is None:
            self.valid_from = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        result = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "memory_class": self.memory_class.value,
            "memory_type": self.memory_type,
            "status": self.status.value if isinstance(self.status, MemoryState) else self.status,
            "content": self.content,
            "content_embedding": self.content_embedding,
            "source_message_id": self.source_message_id,
            "source_session_id": self.source_session_id,
            "extraction_timestamp": self.extraction_timestamp,
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
            "confidence": self.confidence,
            "user_confirmed": self.user_confirmed,
            "user_confirmed_at": self.user_confirmed_at,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "is_current": self.is_current,
            "superseded_by": self.superseded_by,
            "supersession_reason": self.supersession_reason,
            "visibility_scope": self.visibility_scope,
            "access_control": self.access_control,
            "retention_policy": self.retention_policy,
            "retention_until": self.retention_until,
        }
        
        # Add DecisionMemory-specific fields if present
        if hasattr(self, 'decision_summary'):
            result["decision_summary"] = self.decision_summary
            result["rationale"] = self.rationale
            result["alternatives"] = self.alternatives
            result["decided_at"] = self.decided_at
            result["decided_by"] = self.decided_by
            if isinstance(self.status, DecisionStatus):
                result["status"] = self.status.value
        
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        """Create Memory from dictionary."""
        if isinstance(data.get("memory_class"), str):
            data["memory_class"] = MemoryClass(data["memory_class"])
        if isinstance(data.get("status"), str):
            # Try DecisionStatus first, then MemoryState
            try:
                data["status"] = DecisionStatus(data["status"])
            except ValueError:
                try:
                    data["status"] = MemoryState(data["status"])
                except ValueError:
                    pass
        # Filter data to only include valid fields for the class
        import inspect
        valid_fields = set(inspect.signature(cls).parameters.keys())
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)

    def compute_hash(self, prev_hash: Optional[bytes] = None) -> bytes:
        """Compute row hash for provenance chain.
        
        Creates a SHA-256 hash of the memory content fields to ensure
        integrity and enable chain verification. The hash is computed
        from:
        - Previous hash (if provided)
        - Memory ID
        - Content
        - Confidence
        - Memory class
        - Memory type
        
        Args:
            prev_hash: Optional previous hash in the chain.
            
        Returns:
            32-byte SHA-256 hash digest.
        """
        # Build hash input string
        prev_hex = prev_hash.hex() if prev_hash else "genesis"
        
        # Use string representation of UUID for consistent hashing
        id_str = str(self.id) if self.id else ""
        
        # Handle enums
        class_str = self.memory_class.value if isinstance(self.memory_class, MemoryClass) else str(self.memory_class)
        type_str = self.memory_type if self.memory_type else ""
        
        # Build data string for hashing
        data = f"{prev_hex}:{id_str}:{self.content}:{self.confidence}:{class_str}:{type_str}"
        
        return hashlib.sha256(data.encode('utf-8')).digest()

    def verify_hash_chain(self, expected_prev_hash: Optional[bytes] = None) -> bool:
        """Verify the hash chain integrity.
        
        Args:
            expected_prev_hash: The hash that should precede this row.
            
        Returns:
            True if the hash chain is valid, False otherwise.
        """
        if self.row_hash is None:
            return False
        
        if expected_prev_hash is not None and self.prev_hash != expected_prev_hash:
            return False
        
        # Compute what the hash should be
        computed = self.compute_hash(self.prev_hash)
        return computed == self.row_hash


@dataclass
class EpisodicMemory(Memory):
    """
    Episodic Memory: Stores conversations, sessions, and tool runs.

    Primary characteristics:
    - Temporal + semantic retrieval
    - Captures what happened, when, and in what context
    - Used for session recall and conversation history
    """
    memory_class: MemoryClass = MemoryClass.EPISODIC
    memory_type: str = "session"

    # Additional episodic-specific fields
    event_type: Optional[str] = None
    participants: List[UUID] = field(default_factory=list)
    channel: Optional[str] = None


@dataclass
class SemanticMemory(Memory):
    """
    Semantic Memory: Stores facts, concepts, and domain knowledge.

    Primary characteristics:
    - Semantic + graph retrieval
    - Captures "known truths" and understanding
    - Used for fact lookup and concept explanation
    """
    memory_class: MemoryClass = MemoryClass.SEMANTIC
    memory_type: str = "fact"

    # Additional semantic-specific fields
    is_fact: bool = False
    is_verified: bool = False
    related_concepts: List[str] = field(default_factory=list)


@dataclass
class ProceduralMemory(Memory):
    """
    Procedural Memory: Stores workflows, patterns, and playbooks.

    Primary characteristics:
    - Semantic + temporal retrieval
    - Captures how to do things and recurring patterns
    - Used for procedural recall and workflow automation
    """
    memory_class: MemoryClass = MemoryClass.PROCEDURAL
    memory_type: str = "workflow"

    # Additional procedural-specific fields
    workflow_steps: List[Dict[str, Any]] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    last_successful_execution: Optional[datetime] = None


@dataclass
class DecisionMemory(Memory):
    """
    Decision Memory: Stores what was decided, why, and alternatives.

    Primary characteristics:
    - Graph traversal + temporal retrieval
    - Captures decisions and their rationale
    - Used for decision recall and change detection
    """
    memory_class: MemoryClass = MemoryClass.DECISION
    memory_type: str = "technical"
    # Decision-specific fields (7 new fields)
    decision_summary: str = ""
    rationale: str = ""  
    alternatives: List[str] = field(default_factory=list)
    status: DecisionStatus = DecisionStatus.PROPOSED
    superseded_by: Optional[str] = None
    supersession_reason: Optional[str] = None
    supporting_evidence: List[str] = field(default_factory=list)
    decided_at: Optional[datetime] = None
    decided_by: str = ""

    # Legacy fields
    decision_type: Optional[str] = None
    alternatives_considered: List[str] = field(default_factory=list)


@dataclass
class IdentityMemory(Memory):
    """
    Identity Memory: Stores persona, guardrails, and preferences.

    Primary characteristics:
    - Key-value lookup retrieval
    - Captures "who I am" and "what I prefer"
    - Used for persona consistency and preference recall
    """
    memory_class: MemoryClass = MemoryClass.IDENTITY
    memory_type: str = "preference"
    visibility_scope: str = "personal"

    # Additional identity-specific fields
    identity_type: Optional[str] = None  # persona, guardrail, preference
    is_core: bool = False  # Core identity vs. learned preference


@dataclass
class RelationalMemory(Memory):
    """
    Relational Memory: Stores people, projects, and dependencies.

    Primary characteristics:
    - Graph traversal retrieval
    - Captures relationships and dependencies
    - Used for relationship queries and dependency tracking
    """
    memory_class: MemoryClass = MemoryClass.RELATIONAL
    memory_type: str = "project"

    # Additional relational-specific fields
    entity_type: Optional[str] = None  # person, project, system
    related_entities: List[UUID] = field(default_factory=list)
    relationship_strength: float = 0.5

    def __init__(self, **kwargs):
        # Pop relational-specific fields before passing to parent
        self.entity_type = kwargs.pop('entity_type', None)
        self.related_entities = kwargs.pop('related_entities', [])
        self.relationship_strength = kwargs.pop('relationship_strength', 0.5)
        
        kwargs.setdefault("memory_class", MemoryClass.RELATIONAL)
        kwargs.setdefault("memory_type", kwargs.get("memory_type", "project"))
        super().__init__(**kwargs)


@dataclass
class SummaryMemory(Memory):
    """
    Summary Memory: Stores session, topic, and conversation summaries.

    Primary characteristics:
    - Semantic retrieval
    - Condensed representations of longer content
    - Used for quick context and overview
    """
    memory_class: MemoryClass = MemoryClass.SUMMARY
    memory_type: str = "session"

    # Additional summary-specific fields
    summary_type: Optional[str] = None  # session, conversation, topic
    token_count: int = 0
    source_item_ids: List[UUID] = field(default_factory=list)

    def __init__(self, **kwargs):
        # Pop summary-specific fields before passing to parent
        self.summary_type = kwargs.pop('summary_type', None)
        self.token_count = kwargs.pop('token_count', 0)
        self.source_item_ids = kwargs.pop('source_item_ids', [])
        
        kwargs.setdefault("memory_class", MemoryClass.SUMMARY)
        kwargs.setdefault("memory_type", kwargs.get("memory_type", "session"))
        super().__init__(**kwargs)


def create_memory(
    memory_class: MemoryClass,
    content: str,
    **kwargs
) -> Memory:
    """
    Factory function to create the appropriate memory type.

    Args:
        memory_class: The class of memory to create
        content: The content of the memory
        **kwargs: Additional fields for the memory

    Returns:
        An instance of the appropriate Memory subclass
    """
    memory_class_map = {
        MemoryClass.EPISODIC: EpisodicMemory,
        MemoryClass.SEMANTIC: SemanticMemory,
        MemoryClass.PROCEDURAL: ProceduralMemory,
        MemoryClass.DECISION: DecisionMemory,
        MemoryClass.IDENTITY: IdentityMemory,
        MemoryClass.RELATIONAL: RelationalMemory,
        MemoryClass.SUMMARY: SummaryMemory,
    }

    memory_cls = memory_class_map.get(memory_class, Memory)
    return memory_cls(content=content, **kwargs)


class VisibilityScope(str, Enum):
    """
    Visibility scopes for agent-specific memory isolation.
    Defines who can access a given memory item.
    """
    PERSONAL = "personal"   # Private to individual user/agent
    AGENT = "agent"         # Private to this agent only
    TEAM = "team"           # Shared with team members
    PROJECT = "project"     # Shared within project
    TENANT = "tenant"      # Shared within organization
    ORG = "org"             # Organization-wide
    PUBLIC = "public"       # Public access


@dataclass
class AgentMemory(Memory):
    """
    Memory specific to an agent's context with isolation support.

    Provides agent-specific fields for memory isolation and team sharing.
    This extends the base Memory class with:
    - agent_id: Which agent owns this memory
    - visibility: Who can access this memory (agent, team, tenant, etc.)
    - shared_with: List of agent IDs this memory is shared with
    - is_team_memory: True if shared across team
    """
    # Agent-specific fields (shadowing base class visibility_scope)
    visibility: str = "agent"  # 'agent', 'team', 'tenant', 'public'
    shared_with: List[str] = field(default_factory=list)  # Other agent IDs if shared
    is_team_memory: bool = False  # True if shared across team

    def __init__(self, **kwargs):
        # Handle visibility vs visibility_scope
        # AgentMemory uses 'visibility' but maps to 'visibility_scope' for base class
        if 'visibility' in kwargs:
            kwargs['visibility_scope'] = kwargs.pop('visibility')
        
        # Set default visibility to 'agent' for private memory
        kwargs.setdefault("visibility_scope", "agent")
        
        # Extract agent-specific fields before passing to parent
        is_team_memory = kwargs.pop('is_team_memory', False)
        shared_with = kwargs.pop('shared_with', [])
        
        super().__init__(**kwargs)
        
        # Now set the agent-specific visibility after parent init
        # Use visibility_scope if visibility wasn't explicitly passed via kwargs
        if 'visibility' in kwargs:
            self.visibility = kwargs['visibility']
        elif self.visibility_scope:
            self.visibility = self.visibility_scope
        else:
            self.visibility = "agent"  # Default
            
        # Set agent-specific fields
        self.is_team_memory = is_team_memory
        self.shared_with = list(shared_with) if shared_with is not None else []

    def is_agent_private(self, check_agent_id: str) -> bool:
        """
        Check if this memory is private to a specific agent.

        Args:
            check_agent_id: The agent ID to check against.

        Returns:
            True if this memory is private to the specified agent.
        """
        if self.agent_id is None:
            return False
        return str(self.agent_id) == check_agent_id and self.visibility == "agent"

    def can_agent_access(self, agent_id: str, team_member_ids: List[str]) -> bool:
        """
        Check if an agent can access this memory based on visibility scope.

        Args:
            agent_id: The agent ID requesting access.
            team_member_ids: List of team member agent IDs.

        Returns:
            True if the agent can access this memory.
        """
        # Public is accessible to everyone
        if self.visibility == "public":
            return True

        # Check if explicitly shared with this agent
        if hasattr(self, "shared_with") and agent_id in self.shared_with:
            return True

        # Agent-private: only the owner can access
        if self.visibility == "agent":
            if self.agent_id is None:
                return True  # No agent_id means it's not agent-specific
            return str(self.agent_id) == agent_id

        # Team-shared: accessible to team members
        if self.visibility == "team":
            return agent_id in team_member_ids or str(self.agent_id) == agent_id

        # Tenant/org: check if agent belongs to same tenant
        if self.visibility in ("tenant", "org", "project"):
            return True  # For now, allow tenant/org level access

        # Personal scope
        if self.visibility == "personal":
            return str(self.agent_id) == agent_id if self.agent_id else True

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary including agent-specific fields."""
        result = super().to_dict()
        result.update({
            "agent_id": self.agent_id,
            "visibility": self.visibility,
            "shared_with": self.shared_with,
            "is_team_memory": self.is_team_memory,
        })
        return result