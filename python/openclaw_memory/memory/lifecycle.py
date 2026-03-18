"""
Memory Lifecycle Management for the BrainClaw Memory System.

Manages the lifecycle states of memory items:
- Raw: Ingested event, not processed
- Active: Indexed, retrievable
- Superseded: Replaced by newer information
- Expired: Past valid_to date
- Archived: Retained for audit, not active
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4


from openclaw_memory.memory.classes import MemoryState


@dataclass
class MemoryEvent:
    """
    Represents a lifecycle event for a memory item.

    Tracks provenance: who, when, and why for each state change.
    """
    id: UUID = field(default_factory=uuid4)
    memory_item_id: Optional[UUID] = None
    event_type: str = ""  # created, updated, superseded, expired, archived, promoted
    event_timestamp: datetime = field(default_factory=datetime.utcnow)
    event_data: Dict[str, Any] = field(default_factory=dict)

    # Actor tracking
    triggered_by: Optional[UUID] = None  # user_id
    triggered_by_agent: Optional[UUID] = None
    trigger_reason: Optional[str] = None

    def __post_init__(self):
        if self.event_timestamp is None:
            self.event_timestamp = datetime.utcnow()


@dataclass
class LifecycleManager:
    """
    Manages memory lifecycle state transitions.

    Provides methods for:
    - State transitions with validation
    - Supersession chains
    - Expiration scheduling
    - Archiving for audit

    Provenance is tracked for every state change.
    """

    def __init__(self):
        self._event_history: List[MemoryEvent] = []

    def get_state(self, memory: Any) -> MemoryState:
        """
        Determine current state of a memory item.

        Args:
            memory: Memory object with lifecycle fields

        Returns:
            Current MemoryState
        """
        # Check explicit state indicators
        if hasattr(memory, "is_archived") and memory.is_archived:
            return MemoryState.ARCHIVED

        # Check expired
        if memory.valid_to and memory.valid_to < datetime.utcnow():
            if hasattr(memory, "is_archived") and memory.is_archived:
                return MemoryState.ARCHIVED
            return MemoryState.EXPIRED

        # Check superseded
        if hasattr(memory, "superseded_by") and memory.superseded_by is not None:
            return MemoryState.SUPERSEDED

        # Check is_current - if False, might be superseded or expired
        if hasattr(memory, "is_current") and not memory.is_current:
            if memory.valid_to and memory.valid_to < datetime.utcnow():
                return MemoryState.EXPIRED
            return MemoryState.SUPERSEDED

        # Check if recently created (raw state for very new items)
        if hasattr(memory, "extraction_confidence") and memory.extraction_confidence is None:
            return MemoryState.RAW

        return MemoryState.ACTIVE

    def transition(
        self,
        memory: Any,
        new_state: MemoryState,
        reason: str,
        triggered_by: Optional[UUID] = None,
        triggered_by_agent: Optional[UUID] = None,
    ) -> bool:
        """
        Transition memory to a new state with validation.

        Args:
            memory: Memory object to transition
            new_state: Target state
            reason: Reason for the transition
            triggered_by: User ID who triggered the transition
        """
        if triggered_by_agent is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    triggered_by_agent = UUID(current_agent_id)
            except Exception:
                pass
        current_state = self.get_state(memory)

        # Validate transition
        if not current_state.is_valid_transition(new_state):
            valid_next = [s.value for s in MemoryState if current_state.is_valid_transition(s)]
            raise ValueError(
                f"Invalid transition from {current_state.value} to {new_state.value}. "
                f"Valid transitions from {current_state.value}: {valid_next}"
            )

        # Record the transition event
        event = MemoryEvent(
            memory_item_id=memory.id if hasattr(memory, "id") else None,
            event_type=f"transition_{new_state.value}",
            event_data={
                "from_state": current_state.value,
                "to_state": new_state.value,
            },
            triggered_by=triggered_by,
            triggered_by_agent=triggered_by_agent,
            trigger_reason=reason,
        )
        self._event_history.append(event)

        # Apply state change to memory object
        self._apply_state_change(memory, new_state, reason)

        return True

    def _get_valid_transitions(self, state: MemoryState) -> List[MemoryState]:
        """Get list of valid transitions from a given state."""
        return [s for s in MemoryState if state.is_valid_transition(s)]

    def _apply_state_change(self, memory: Any, new_state: MemoryState, reason: str) -> None:
        """Apply state change to memory object."""
        timestamp = datetime.utcnow()

        if new_state == MemoryState.ACTIVE:
            memory.is_current = True
            memory.valid_from = getattr(memory, "valid_from", timestamp)
            # Set confidence indicator so get_state recognizes it as ACTIVE
            if hasattr(memory, "extraction_confidence") and memory.extraction_confidence is None:
                memory.extraction_confidence = 1.0

        elif new_state == MemoryState.SUPERSEDED:
            memory.is_current = False
            memory.supersession_reason = reason

        elif new_state == MemoryState.EXPIRED:
            memory.is_current = False
            # Note: valid_to should already be set, but ensure it's in the past
            if memory.valid_to is None:
                memory.valid_to = timestamp

        elif new_state == MemoryState.ARCHIVED:
            memory.is_current = False
            if hasattr(memory, "is_archived"):
                memory.is_archived = True
            # Archive typically retains the original valid_to

        # Always update the updated_at timestamp
        memory.updated_at = timestamp

    def supersede(
        self,
        memory: Any,
        new_memory: Any,
        reason: Optional[str] = None,
        triggered_by: Optional[UUID] = None,
        triggered_by_agent: Optional[UUID] = None,
    ) -> bool:
        """
        Create supersession chain: mark old memory as superseded by new one.

        Args:
            memory: Original memory item to supersede
            new_memory: New memory item that supersedes the old one
            reason: Reason for supersession
            triggered_by: User ID who triggered the supersession
        """
        if triggered_by_agent is None:
            try:
                from openclaw_memory.security.access_control import get_current_agent_id
                current_agent_id = get_current_agent_id()
                if current_agent_id:
                    triggered_by_agent = UUID(current_agent_id)
            except Exception:
                pass
        # Record supersession event for old memory
        event_old = MemoryEvent(
            memory_item_id=memory.id if hasattr(memory, "id") else None,
            event_type="superseded",
            event_data={
                "superseded_by": str(new_memory.id) if hasattr(new_memory, "id") else None,
                "reason": reason,
            },
            triggered_by=triggered_by,
            triggered_by_agent=triggered_by_agent,
            trigger_reason=reason,
        )
        self._event_history.append(event_old)

        # Record creation event for new memory
        event_new = MemoryEvent(
            memory_item_id=new_memory.id if hasattr(new_memory, "id") else None,
            event_type="created_superseding",
            event_data={
                "supersedes": str(memory.id) if hasattr(memory, "id") else None,
                "reason": reason,
            },
            triggered_by=triggered_by,
            triggered_by_agent=triggered_by_agent,
            trigger_reason=reason,
        )
        self._event_history.append(event_new)

        # Apply changes to old memory
        memory.is_current = False
        memory.superseded_by = new_memory.id if hasattr(new_memory, "id") else None
        memory.supersession_reason = reason
        memory.updated_at = datetime.utcnow()

        # Set new memory as current
        new_memory.is_current = True
        new_memory.valid_from = datetime.utcnow()

        return True

    def expire(
        self,
        memory: Any,
        valid_to: Optional[datetime] = None,
        reason: Optional[str] = None,
        triggered_by: Optional[UUID] = None,
        triggered_by_agent: Optional[UUID] = None,
    ) -> bool:
        """
        Set expiration for a memory item.

        Args:
            memory: Memory item to expire
            valid_to: Datetime when memory expires (defaults to now)
            reason: Reason for expiration
            triggered_by: User ID who triggered the expiration
            triggered_by_agent: Agent ID that triggered the expiration

        Returns:
            True if expiration was set successfully
        """
        # Set valid_to
        memory.valid_to = valid_to or datetime.utcnow()

        # Record expiration event
        event = MemoryEvent(
            memory_item_id=memory.id if hasattr(memory, "id") else None,
            event_type="expired",
            event_data={
                "valid_to": str(memory.valid_to),
                "reason": reason,
            },
            triggered_by=triggered_by,
            triggered_by_agent=triggered_by_agent,
            trigger_reason=reason,
        )
        self._event_history.append(event)

        # Update state
        memory.is_current = False
        memory.updated_at = datetime.utcnow()

        return True

    def archive(
        self,
        memory: Any,
        reason: Optional[str] = None,
        triggered_by: Optional[UUID] = None,
        triggered_by_agent: Optional[UUID] = None,
    ) -> bool:
        """
        Archive a memory item for audit purposes.

        Archived memories are retained but not active for retrieval.

        Args:
            memory: Memory item to archive
            reason: Reason for archiving
            triggered_by: User ID who triggered the archival
            triggered_by_agent: Agent ID that triggered the archival

        Returns:
            True if archival was successful
        """
        # Record archival event
        event = MemoryEvent(
            memory_item_id=memory.id if hasattr(memory, "id") else None,
            event_type="archived",
            event_data={
                "reason": reason,
                "archived_at": str(datetime.utcnow()),
            },
            triggered_by=triggered_by,
            triggered_by_agent=triggered_by_agent,
            trigger_reason=reason,
        )
        self._event_history.append(event)

        # Apply archival state
        memory.is_current = False
        if hasattr(memory, "is_archived"):
            memory.is_archived = True
        memory.updated_at = datetime.utcnow()

        return True

    def get_event_history(
        self,
        memory_item_id: Optional[UUID] = None,
    ) -> List[MemoryEvent]:
        """
        Get lifecycle event history.

        Args:
            memory_item_id: Optional filter for specific memory item

        Returns:
            List of MemoryEvent objects
        """
        if memory_item_id is None:
            return self._event_history.copy()

        return [
            event for event in self._event_history
            if event.memory_item_id == memory_item_id
        ]

    def clear_history(self) -> None:
        """Clear event history (useful for testing)."""
        self._event_history.clear()


# Default lifecycle manager instance
default_lifecycle_manager = LifecycleManager()


def get_state(memory: Any) -> MemoryState:
    """Convenience function to get memory state."""
    return default_lifecycle_manager.get_state(memory)


def transition(
    memory: Any,
    new_state: MemoryState,
    reason: str,
    triggered_by: Optional[UUID] = None,
    triggered_by_agent: Optional[UUID] = None,
) -> bool:
    """Convenience function to transition memory state."""
    return default_lifecycle_manager.transition(memory, new_state, reason, triggered_by, triggered_by_agent)


def supersede(
    memory: Any,
    new_memory: Any,
    reason: Optional[str] = None,
    triggered_by: Optional[UUID] = None,
    triggered_by_agent: Optional[UUID] = None,
) -> bool:
    """Convenience function to supersede memory."""
    return default_lifecycle_manager.supersede(memory, new_memory, reason, triggered_by, triggered_by_agent)


def expire(
    memory: Any,
    valid_to: Optional[datetime] = None,
    reason: Optional[str] = None,
    triggered_by: Optional[UUID] = None,
    triggered_by_agent: Optional[UUID] = None,
) -> bool:
    """Convenience function to expire memory."""
    return default_lifecycle_manager.expire(memory, valid_to, reason, triggered_by, triggered_by_agent)


def archive(
    memory: Any,
    reason: Optional[str] = None,
    triggered_by: Optional[UUID] = None,
    triggered_by_agent: Optional[UUID] = None,
) -> bool:
    """Convenience function to archive memory."""
    return default_lifecycle_manager.archive(memory, reason, triggered_by, triggered_by_agent)