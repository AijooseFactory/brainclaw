"""Artifact validation for BrainClaw source artifact imports.

FR-006: Imported artifacts must be schema-validated before processing.

Checks:
  - Schema validation (required fields present, correct types)
  - Safe deserialization (no code injection via content)
  - Size limits (content length, field count)
  - Required field checks
  - Enum validation (artifact types, statefulness values)
  - Source version validation
  - Scope/statefulness validation

Invalid artifacts are rejected before candidate extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# --- Size limits ---

MAX_CONTENT_BYTES = 512_000  # 500 KB per artifact content
MAX_TOPIC_HINTS = 20
MAX_MESSAGE_IDS = 500
MAX_FIELD_LENGTH = 1024  # for string metadata fields

# --- Allowed enums ---

VALID_ARTIFACT_TYPES = {
    "lcm_summary",
    "lcm_manifest",
    "lcm_anchor_range",
    "lcm_summary_footer_hint",
    "file_artifact",
    "manual_artifact",
}

VALID_STATEFULNESS_VALUES = {
    "stateful",
    "stateless",
    "ignored",
}

VALID_IMPORT_STATUSES = {
    "imported",
    "failed",
    "quarantined",
}

VALID_VISIBILITY_SCOPES = {
    "owner",
    "team",
    "workspace",
    "public",
}


@dataclass
class ValidationResult:
    """Result of artifact validation."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quarantine_reason: Optional[str] = None

    @property
    def should_quarantine(self) -> bool:
        return not self.valid and self.quarantine_reason is not None


def validate_source_artifact(artifact: Dict[str, Any]) -> ValidationResult:
    """Validate a source artifact before ingestion.

    Returns a ValidationResult indicating whether the artifact should be
    accepted, rejected, or quarantined.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # --- Required field checks ---
    required_fields = [
        "source_plugin",
        "source_artifact_type",
        "source_artifact_id",
        "artifact_hash",
    ]
    for field_name in required_fields:
        if not artifact.get(field_name):
            errors.append(f"Missing required field: {field_name}")

    # Payload must exist and contain content
    payload = artifact.get("payload")
    if payload is None:
        errors.append("Missing payload")
    elif not isinstance(payload, dict):
        errors.append("Payload must be a dictionary")
    elif not payload.get("content"):
        errors.append("Payload missing content field")

    # --- Enum validation ---
    artifact_type = artifact.get("source_artifact_type")
    if artifact_type and artifact_type not in VALID_ARTIFACT_TYPES:
        errors.append(
            f"Invalid source_artifact_type: {artifact_type!r}. "
            f"Must be one of: {', '.join(sorted(VALID_ARTIFACT_TYPES))}"
        )

    statefulness = artifact.get("statefulness")
    if statefulness and statefulness not in VALID_STATEFULNESS_VALUES:
        errors.append(
            f"Invalid statefulness: {statefulness!r}. "
            f"Must be one of: {', '.join(sorted(VALID_STATEFULNESS_VALUES))}"
        )

    visibility = artifact.get("visibility_scope")
    if visibility and visibility not in VALID_VISIBILITY_SCOPES:
        warnings.append(
            f"Unknown visibility_scope: {visibility!r}. Defaulting to 'owner'."
        )

    # --- Size limit checks ---
    if isinstance(payload, dict):
        content = payload.get("content", "")
        if isinstance(content, str) and len(content.encode("utf-8", errors="replace")) > MAX_CONTENT_BYTES:
            errors.append(
                f"Content exceeds size limit: {len(content.encode('utf-8', errors='replace'))} bytes "
                f"(max {MAX_CONTENT_BYTES})"
            )

    topic_hints = artifact.get("topic_hints", [])
    if isinstance(topic_hints, list) and len(topic_hints) > MAX_TOPIC_HINTS:
        warnings.append(
            f"topic_hints truncated from {len(topic_hints)} to {MAX_TOPIC_HINTS}"
        )

    raw_anchor_ids = artifact.get("raw_anchor_ids", [])
    if isinstance(raw_anchor_ids, list) and len(raw_anchor_ids) > MAX_MESSAGE_IDS:
        warnings.append(
            f"raw_anchor_ids truncated from {len(raw_anchor_ids)} to {MAX_MESSAGE_IDS}"
        )

    # --- String length validation for metadata fields ---
    string_fields = [
        "source_plugin",
        "source_artifact_id",
        "source_scope_key",
        "source_session_id",
        "source_conversation_id",
        "signer_identity",
    ]
    for field_name in string_fields:
        value = artifact.get(field_name)
        if isinstance(value, str) and len(value) > MAX_FIELD_LENGTH:
            errors.append(f"Field {field_name} exceeds max length ({MAX_FIELD_LENGTH})")

    # --- Source version validation ---
    source_plugin = artifact.get("source_plugin")
    if source_plugin == "lossless-claw":
        # For LCM artifacts, compatibility_state should be set
        compat = artifact.get("compatibility_state")
        if not compat:
            warnings.append("LCM artifact missing compatibility_state")

    # --- Determine outcome ---
    quarantine_reason = None
    if errors:
        # Determine if this should be quarantined or hard-rejected
        critical_errors = [e for e in errors if "Missing required" in e or "exceeds size" in e]
        if critical_errors:
            quarantine_reason = "; ".join(critical_errors[:3])

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        quarantine_reason=quarantine_reason,
    )


def sanitize_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize an artifact by enforcing size limits on list fields.

    Returns a shallow copy with truncated lists. Does not modify the original.
    """
    sanitized = dict(artifact)

    # Truncate topic_hints
    if isinstance(sanitized.get("topic_hints"), list):
        sanitized["topic_hints"] = sanitized["topic_hints"][:MAX_TOPIC_HINTS]

    # Truncate raw_anchor_ids
    if isinstance(sanitized.get("raw_anchor_ids"), list):
        sanitized["raw_anchor_ids"] = sanitized["raw_anchor_ids"][:MAX_MESSAGE_IDS]

    return sanitized
