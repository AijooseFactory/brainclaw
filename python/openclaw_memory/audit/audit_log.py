"""Immutable audit log for state transitions.

This module provides an append-only audit log for tracking all memory
operations. It is designed for compliance (GDPR, SOC2) and provides
non-repudiation for memory operations.

The audit log is immutable - no UPDATE or DELETE operations are permitted.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

import asyncpg


class AuditAction(str, Enum):
    """Actions that can be audited."""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    PROMOTE = "PROMOTE"
    SUPERSEDE = "SUPERSEDE"
    EXPIRE = "EXPIRE"
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"


class AuditResourceType(str, Enum):
    """Resource types that can be audited."""
    MEMORY_ITEM = "memory_item"
    COMMUNITY = "community"
    SUMMARY = "summary"
    ENTITY = "entity"
    DECISION = "decision"
    CLAIM = "claim"
    SESSION = "session"


@dataclass
class AuditEvent:
    """An audit event representing a state transition."""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    actor_id: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "actor_id": self.actor_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "AuditEvent":
        """Create AuditEvent from database row."""
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            actor_id=row["actor_id"],
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            before_state=row.get("before_state"),
            after_state=row.get("after_state"),
            correlation_id=row.get("correlation_id"),
            metadata=row.get("metadata", {}),
        )


class AuditLogger:
    """Immutable audit log for state transitions.
    
    This class provides an append-only audit log that captures all state
    transitions in the memory system. It is designed for compliance with
    GDPR, SOC2, and other regulatory frameworks.
    
    The audit log is immutable - no UPDATE or DELETE operations are permitted.
    All operations are append-only.
    """

    def __init__(self, postgres: "PostgresClient"):
        """Initialize audit logger.
        
        Args:
            postgres: PostgreSQL client for database access
        """
        self.postgres = postgres

    async def log(
        self,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log an audit event.
        
        This is an append-only operation. The event is persisted to the
        audit_log table and cannot be modified or deleted.
        
        Args:
            actor_id: Who performed the action (agent_id, user_id, system)
            action: The action performed (CREATE, READ, UPDATE, DELETE, etc.)
            resource_type: Type of resource (memory_item, community, etc.)
            resource_id: ID of the resource
            before_state: State before the action (null for CREATE)
            after_state: State after the action (null for DELETE)
            correlation_id: Trace ID for distributed tracing
            metadata: Additional context
            
        Returns:
            The ID of the audit log entry
        """
        # Validate action
        try:
            AuditAction(action)
        except ValueError:
            raise ValueError(f"Invalid audit action: {action}")

        # Validate resource type
        try:
            AuditResourceType(resource_type)
        except ValueError:
            raise ValueError(f"Invalid resource type: {resource_type}")

        # Auto-generate correlation_id if not provided
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        query = """
            INSERT INTO audit_log (
                timestamp,
                actor_id,
                action,
                resource_type,
                resource_id,
                before_state,
                after_state,
                correlation_id,
                metadata
            ) VALUES (
                NOW(),
                $1, $2, $3, $4, $5, $6, $7, $8
            )
            RETURNING id
        """

        async with self.postgres._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                actor_id,
                action,
                resource_type,
                resource_id,
                before_state,
                after_state,
                correlation_id,
                metadata or {},
            )
            return row["id"]

    async def log_create(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        after_state: Dict[str, Any],
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log a CREATE event.
        
        Args:
            actor_id: Who created the resource
            resource_type: Type of resource
            resource_id: ID of the created resource
            after_state: State after creation
            correlation_id: Optional trace ID
            metadata: Optional additional metadata
            
        Returns:
            Audit log entry ID
        """
        return await self.log(
            actor_id=actor_id,
            action=AuditAction.CREATE.value,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=None,
            after_state=after_state,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def log_read(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log a READ event.
        
        Args:
            actor_id: Who read the resource
            resource_type: Type of resource
            resource_id: ID of the read resource
            correlation_id: Optional trace ID
            metadata: Optional additional metadata
            
        Returns:
            Audit log entry ID
        """
        return await self.log(
            actor_id=actor_id,
            action=AuditAction.READ.value,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=None,
            after_state=None,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def log_update(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log an UPDATE event.
        
        Args:
            actor_id: Who performed the update
            resource_type: Type of resource
            resource_id: ID of the updated resource
            before_state: State before update
            after_state: State after update
            correlation_id: Optional trace ID
            metadata: Optional additional metadata
            
        Returns:
            Audit log entry ID
        """
        return await self.log(
            actor_id=actor_id,
            action=AuditAction.UPDATE.value,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=before_state,
            after_state=after_state,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def log_delete(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        before_state: Dict[str, Any],
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log a DELETE event.
        
        Args:
            actor_id: Who deleted the resource
            resource_type: Type of resource
            resource_id: ID of the deleted resource
            before_state: State before deletion
            correlation_id: Optional trace ID
            metadata: Optional additional metadata
            
        Returns:
            Audit log entry ID
        """
        return await self.log(
            actor_id=actor_id,
            action=AuditAction.DELETE.value,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=before_state,
            after_state=None,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def log_promote(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log a PROMOTE event (e.g., promoting raw extraction to memory).
        
        Args:
            actor_id: Who performed the promotion
            resource_type: Type of resource
            resource_id: ID of the promoted resource
            before_state: State before promotion
            after_state: State after promotion
            correlation_id: Optional trace ID
            metadata: Optional additional metadata
            
        Returns:
            Audit log entry ID
        """
        return await self.log(
            actor_id=actor_id,
            action=AuditAction.PROMOTE.value,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=before_state,
            after_state=after_state,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    async def log_supersede(
        self,
        actor_id: str,
        resource_type: str,
        old_resource_id: str,
        new_resource_id: str,
        old_state: Dict[str, Any],
        new_state: Dict[str, Any],
        reason: str,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log a SUPERSEDE event (replacing old with new).
        
        Args:
            actor_id: Who performed the supersession
            resource_type: Type of resource
            old_resource_id: ID of the old resource
            new_resource_id: ID of the new resource
            old_state: State of the old resource
            new_state: State of the new resource
            reason: Reason for supersession
            correlation_id: Optional trace ID
            metadata: Optional additional metadata
            
        Returns:
            Audit log entry ID
        """
        meta = metadata or {}
        meta["supersession_reason"] = reason
        meta["superseded_by"] = new_resource_id

        return await self.log(
            actor_id=actor_id,
            action=AuditAction.SUPERSEDE.value,
            resource_type=resource_type,
            resource_id=old_resource_id,
            before_state=old_state,
            after_state=new_state,
            correlation_id=correlation_id,
            metadata=meta,
        )

    async def query(
        self,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit log (read-only).
        
        All parameters are optional filters that are ANDed together.
        
        Args:
            actor_id: Filter by actor
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            action: Filter by action type
            start_time: Filter by start timestamp
            end_time: Filter by end timestamp
            correlation_id: Filter by correlation/trace ID
            limit: Maximum results
            offset: Result offset
            
        Returns:
            List of matching audit events
        """
        conditions = []
        params = []
        param_idx = 1

        if actor_id is not None:
            conditions.append(f"actor_id = ${param_idx}")
            params.append(actor_id)
            param_idx += 1

        if resource_type is not None:
            conditions.append(f"resource_type = ${param_idx}")
            params.append(resource_type)
            param_idx += 1

        if resource_id is not None:
            conditions.append(f"resource_id = ${param_idx}")
            params.append(resource_id)
            param_idx += 1

        if action is not None:
            conditions.append(f"action = ${param_idx}")
            params.append(action)
            param_idx += 1

        if start_time is not None:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(start_time)
            param_idx += 1

        if end_time is not None:
            conditions.append(f"timestamp <= ${param_idx}")
            params.append(end_time)
            param_idx += 1

        if correlation_id is not None:
            conditions.append(f"correlation_id = ${param_idx}")
            params.append(correlation_id)
            param_idx += 1

        # Build query
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        query = f"""
            SELECT * FROM audit_log
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        
        params.extend([limit, offset])

        async with self.postgres._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [AuditEvent.from_row(row) for row in rows]

    async def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
    ) -> List[AuditEvent]:
        """Get complete history for a specific resource.
        
        Args:
            resource_type: Type of resource
            resource_id: ID of the resource
            
        Returns:
            Chronological list of all events for this resource
        """
        query = """
            SELECT * FROM audit_log
            WHERE resource_type = $1 AND resource_id = $2
            ORDER BY timestamp ASC
        """
        
        async with self.postgres._pool.acquire() as conn:
            rows = await conn.fetch(query, resource_type, resource_id)
            return [AuditEvent.from_row(row) for row in rows]

    async def get_actor_activity(
        self,
        actor_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Get all activity by a specific actor.
        
        Args:
            actor_id: Actor to query
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum results
            
        Returns:
            List of audit events by this actor
        """
        return await self.query(
            actor_id=actor_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    async def get_correlation_trace(
        self,
        correlation_id: str,
    ) -> List[AuditEvent]:
        """Get all events in a distributed trace.
        
        Args:
            correlation_id: Correlation/trace ID
            
        Returns:
            List of all events with this correlation ID
        """
        return await self.query(correlation_id=correlation_id, limit=1000)


# Type hint for PostgresClient to avoid circular import
from ..storage.postgres import PostgresClient