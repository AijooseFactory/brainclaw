"""Promotion override control for BrainClaw memory promotion.

FR-016: Promotion override is a privileged action requiring:
  - Privileged-role verification
  - Audit-ledger justification
  - Multi-party approval when configured
  - Override reason preservation
  - No bypass from automated import code paths

Prohibited: No override flag may bypass promotion policy without
privilege enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib
import uuid


class OverrideStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class PrivilegedRole(Enum):
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM_ADMIN = "system_admin"


# Roles that may approve overrides
OVERRIDE_PERMITTED_ROLES = {
    PrivilegedRole.OPERATOR,
    PrivilegedRole.ADMIN,
    PrivilegedRole.SYSTEM_ADMIN,
}

# Roles that may approve low-confidence overrides (multi-party)
LOW_CONFIDENCE_APPROVAL_ROLES = {
    PrivilegedRole.ADMIN,
    PrivilegedRole.SYSTEM_ADMIN,
}


@dataclass
class OverrideRequest:
    """A request to override promotion policy for a candidate."""

    candidate_id: str
    candidate_type: str
    original_blocked_reason: str
    justification: str
    requestor_id: str
    requestor_role: str
    workspace_id: Optional[str] = None
    agent_id: Optional[str] = None
    requires_multi_party: bool = False
    approvals: List[Dict[str, Any]] = field(default_factory=list)
    status: OverrideStatus = OverrideStatus.PENDING
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None
    override_id: Optional[str] = None


@dataclass
class OverrideAuditEntry:
    """Immutable audit record for override actions."""

    override_id: str
    candidate_id: str
    action: str  # "requested", "approved", "denied", "expired"
    actor_id: str
    actor_role: str
    justification: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_override_id(candidate_id: str, requestor_id: str) -> str:
    raw = f"override::{candidate_id}::{requestor_id}::{_utcnow()}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))


class PromotionOverrideController:
    """Controls privileged promotion overrides with audit trail.

    FR-016 requirements:
    - Override requires privileged-role verification
    - Override requires audit-ledger justification
    - Low-confidence override requires multi-party approval when configured
    - Override preserves provenance and override reason
    - Automated import code paths CANNOT set override flags
    """

    def __init__(
        self,
        require_multi_party_for_low_confidence: bool = True,
        multi_party_threshold: int = 2,
    ):
        self._require_multi_party = require_multi_party_for_low_confidence
        self._multi_party_threshold = multi_party_threshold
        self._pending_overrides: Dict[str, OverrideRequest] = {}
        self._audit_log: List[OverrideAuditEntry] = []

    def request_override(
        self,
        candidate_id: str,
        candidate_type: str,
        original_blocked_reason: str,
        justification: str,
        requestor_id: str,
        requestor_role: str,
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        is_automated: bool = False,
    ) -> OverrideRequest:
        """Request a promotion override for a blocked candidate.

        Args:
            candidate_id: The blocked candidate's ID
            candidate_type: Type of candidate
            original_blocked_reason: Why the candidate was blocked
            justification: Human-readable justification for override
            requestor_id: Who is requesting the override
            requestor_role: Role of the requestor
            workspace_id: Scope workspace
            agent_id: Scope agent
            is_automated: Whether this comes from an automated code path

        Raises:
            PermissionError: If requestor lacks privilege or is automated
            ValueError: If justification is empty
        """
        # HARD GATE: Automated import code paths CANNOT request overrides
        if is_automated:
            self._record_audit(
                override_id="BLOCKED",
                candidate_id=candidate_id,
                action="denied_automated",
                actor_id=requestor_id,
                actor_role=requestor_role,
                justification="Automated import paths cannot request overrides",
            )
            raise PermissionError(
                "FR-016: Automated import code paths must never set override flags"
            )

        # Verify privileged role
        try:
            role = PrivilegedRole(requestor_role)
        except ValueError:
            self._record_audit(
                override_id="BLOCKED",
                candidate_id=candidate_id,
                action="denied_unprivileged",
                actor_id=requestor_id,
                actor_role=requestor_role,
                justification=f"Role {requestor_role!r} is not a privileged role",
            )
            raise PermissionError(
                f"FR-016: Role {requestor_role!r} is not authorized for promotion overrides"
            )

        if role not in OVERRIDE_PERMITTED_ROLES:
            self._record_audit(
                override_id="BLOCKED",
                candidate_id=candidate_id,
                action="denied_unprivileged",
                actor_id=requestor_id,
                actor_role=requestor_role,
                justification=f"Role {requestor_role} not in permitted override roles",
            )
            raise PermissionError(
                f"FR-016: Role {requestor_role} is not authorized for promotion overrides"
            )

        # Require justification
        if not justification or not justification.strip():
            raise ValueError("FR-016: Override requires audit-ledger justification")

        # Determine if multi-party approval is needed
        requires_multi_party = (
            self._require_multi_party
            and original_blocked_reason in {"LOW_CONFIDENCE", "CONTRADICTED"}
        )

        override_id = _generate_override_id(candidate_id, requestor_id)
        request = OverrideRequest(
            candidate_id=candidate_id,
            candidate_type=candidate_type,
            original_blocked_reason=original_blocked_reason,
            justification=justification,
            requestor_id=requestor_id,
            requestor_role=requestor_role,
            workspace_id=workspace_id,
            agent_id=agent_id,
            requires_multi_party=requires_multi_party,
            created_at=_utcnow(),
            override_id=override_id,
        )

        # If multi-party not required and role is sufficient, auto-approve
        if not requires_multi_party:
            request.status = OverrideStatus.APPROVED
            request.resolved_at = _utcnow()
            request.approvals.append({
                "approver_id": requestor_id,
                "approver_role": requestor_role,
                "approved_at": _utcnow(),
            })
            self._record_audit(
                override_id=override_id,
                candidate_id=candidate_id,
                action="approved",
                actor_id=requestor_id,
                actor_role=requestor_role,
                justification=justification,
            )
        else:
            # Multi-party: first approval recorded, needs more
            request.approvals.append({
                "approver_id": requestor_id,
                "approver_role": requestor_role,
                "approved_at": _utcnow(),
            })
            self._record_audit(
                override_id=override_id,
                candidate_id=candidate_id,
                action="requested",
                actor_id=requestor_id,
                actor_role=requestor_role,
                justification=justification,
                metadata={"requires_approvals": self._multi_party_threshold},
            )

        self._pending_overrides[override_id] = request
        return request

    def approve_override(
        self,
        override_id: str,
        approver_id: str,
        approver_role: str,
    ) -> OverrideRequest:
        """Add an approval to a pending multi-party override.

        Raises:
            KeyError: If override not found
            PermissionError: If approver lacks privilege
            ValueError: If override is not pending
        """
        request = self._pending_overrides.get(override_id)
        if request is None:
            raise KeyError(f"Override {override_id} not found")

        if request.status != OverrideStatus.PENDING:
            raise ValueError(f"Override {override_id} is {request.status.value}, not pending")

        try:
            role = PrivilegedRole(approver_role)
        except ValueError:
            raise PermissionError(f"Role {approver_role!r} cannot approve overrides")

        if role not in LOW_CONFIDENCE_APPROVAL_ROLES:
            raise PermissionError(f"Role {approver_role} cannot approve low-confidence overrides")

        # Prevent same actor from approving twice
        existing_approvers = {a["approver_id"] for a in request.approvals}
        if approver_id in existing_approvers:
            raise ValueError(f"Approver {approver_id} has already approved this override")

        request.approvals.append({
            "approver_id": approver_id,
            "approver_role": approver_role,
            "approved_at": _utcnow(),
        })

        self._record_audit(
            override_id=override_id,
            candidate_id=request.candidate_id,
            action="approval_added",
            actor_id=approver_id,
            actor_role=approver_role,
            justification=f"Multi-party approval ({len(request.approvals)}/{self._multi_party_threshold})",
        )

        # Check if threshold met
        if len(request.approvals) >= self._multi_party_threshold:
            request.status = OverrideStatus.APPROVED
            request.resolved_at = _utcnow()
            self._record_audit(
                override_id=override_id,
                candidate_id=request.candidate_id,
                action="approved",
                actor_id=approver_id,
                actor_role=approver_role,
                justification="Multi-party threshold met",
            )

        return request

    def deny_override(
        self,
        override_id: str,
        actor_id: str,
        actor_role: str,
        reason: str = "",
    ) -> OverrideRequest:
        """Deny a pending override request."""
        request = self._pending_overrides.get(override_id)
        if request is None:
            raise KeyError(f"Override {override_id} not found")

        request.status = OverrideStatus.DENIED
        request.resolved_at = _utcnow()

        self._record_audit(
            override_id=override_id,
            candidate_id=request.candidate_id,
            action="denied",
            actor_id=actor_id,
            actor_role=actor_role,
            justification=reason or "Override denied",
        )

        return request

    def is_approved(self, override_id: str) -> bool:
        """Check if an override has been approved."""
        request = self._pending_overrides.get(override_id)
        return request is not None and request.status == OverrideStatus.APPROVED

    def get_audit_log(self, candidate_id: Optional[str] = None) -> List[OverrideAuditEntry]:
        """Get audit log entries, optionally filtered by candidate."""
        if candidate_id:
            return [e for e in self._audit_log if e.candidate_id == candidate_id]
        return list(self._audit_log)

    def _record_audit(
        self,
        override_id: str,
        candidate_id: str,
        action: str,
        actor_id: str,
        actor_role: str,
        justification: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._audit_log.append(
            OverrideAuditEntry(
                override_id=override_id,
                candidate_id=candidate_id,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                justification=justification,
                timestamp=_utcnow(),
                metadata=metadata or {},
            )
        )
