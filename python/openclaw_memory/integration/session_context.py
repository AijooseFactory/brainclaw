"""
Session-based memory context for OpenClaw agents.

Provides automatic memory context loading and storage for agent sessions.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from .openclaw_client import OpenClawMemoryClient
from ..memory.classes import Memory, MemoryClass


@dataclass
class SessionMemoryContext:
    """
    Memory context for an agent session.
    
    Automatically loads relevant context and stores new memories.
    """
    
    client: OpenClawMemoryClient
    session_id: str
    agent_id: str
    team_member_ids: List[str]
    
    # Loaded context
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Pending memories to store
    pending_memories: List[Dict[str, Any]] = field(default_factory=list)
    
    async def load(self):
        """Load memory context for this session."""
        self.context = await self.client.get_agent_context(
            self.agent_id,
            self.session_id
        )
        return self.context
    
    async def store(
        self,
        content: str,
        memory_class: MemoryClass,
        visibility: str = 'team',
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Store a memory from this session."""
        return await self.client.store_memory(
            content=content,
            memory_class=memory_class,
            agent_id=self.agent_id,
            session_id=self.session_id,
            message_id=str(uuid.uuid4()),
            visibility=visibility,
            metadata=metadata
        )
    
    async def query(
        self,
        query: str,
        limit: int = 10
    ) -> List[Memory]:
        """Query memories relevant to the session."""
        return await self.client.retrieve_memories(
            query=query,
            agent_id=self.agent_id,
            team_member_ids=self.team_member_ids,
            limit=limit
        )
    
    async def close(self):
        """Store any pending memories and close context."""
        for memory_data in self.pending_memories:
            await self.store(**memory_data)
        self.pending_memories.clear()