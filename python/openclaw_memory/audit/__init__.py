"""Audit logging module for immutable audit trail.

This module provides:
- AuditLogger: Append-only audit log for state transitions
- Query capabilities for compliance (GDPR, SOC2)

The audit log is immutable: no UPDATE or DELETE operations are permitted.
"""

from .audit_log import AuditLogger, AuditEvent

__all__ = ["AuditLogger", "AuditEvent"]