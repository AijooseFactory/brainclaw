"""
Memory Classes and Lifecycle for the BrainClaw Memory System.

This module provides:
- Memory classes (Episodic, Semantic, Procedural, Decision, Identity, Relational, Summary)
- Agent-specific memory (AgentMemory) with isolation support
- Lifecycle management (state transitions, supersession, expiration, archival)
- Write policy (determining what to store and promote)
- Agent isolation policy (for team-based memory access control)

Usage:
    from openclaw_memory.memory import (
        Memory, MemoryClass, MemoryType,
        EpisodicMemory, SemanticMemory, ProceduralMemory,
        DecisionMemory, IdentityMemory, RelationalMemory, SummaryMemory,
        AgentMemory, VisibilityScope,
        create_memory,
        LifecycleManager, MemoryState, MemoryEvent,
        default_lifecycle_manager,
        WritePolicy, default_write_policy,
        AgentIsolationPolicy, default_agent_isolation,
        should_promote, check_write_policy,
    )
"""

from .classes import (
    Memory,
    MemoryClass,
    MemoryType,
    DecisionStatus,
    MemoryState,
    VisibilityScope,
    EpisodicMemory,
    SemanticMemory,
    ProceduralMemory,
    DecisionMemory,
    IdentityMemory,
    RelationalMemory,
    SummaryMemory,
    AgentMemory,
    create_memory,
)

from .lifecycle import (
    MemoryEvent,
    LifecycleManager,
    default_lifecycle_manager,
    get_state,
    transition,
    supersede,
    expire,
    archive,
)

from .write_policy import (
    ContentType,
    ExtractionResult,
    WritePolicy,
    default_write_policy,
    AgentIsolationPolicy,
    default_agent_isolation,
    should_promote,
    check_write_policy,
    classify_content_type,
)

__all__ = [
    # Classes
    "Memory",
    "MemoryClass",
    "MemoryType",
    "VisibilityScope",
    "AgentMemory",
    "EpisodicMemory",
    "SemanticMemory",
    "ProceduralMemory",
    "DecisionMemory",
    "IdentityMemory",
    "RelationalMemory",
    "SummaryMemory",
    "create_memory",
    # Lifecycle
    "MemoryState",
    "MemoryEvent",
    "LifecycleManager",
    "default_lifecycle_manager",
    "get_state",
    "transition",
    "supersede",
    "expire",
    "archive",
    # Write Policy
    "ContentType",
    "ExtractionResult",
    "WritePolicy",
    "default_write_policy",
    "AgentIsolationPolicy",
    "default_agent_isolation",
    "should_promote",
    "check_write_policy",
    "classify_content_type",
]