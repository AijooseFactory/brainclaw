"""Canonical Lossless-Claw sync engine and repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Protocol
import uuid

from openclaw_memory.integration.lossless_adapter import (
    CompatibilityState,
    LosslessClawAdapter,
    ReasonCode,
)
from openclaw_memory.pipeline.extraction import extract_all


BRAINCLAW_NS = uuid.UUID("b4a1bc1a-0000-4000-a000-b4a1bc1ab000")
NEGATION_WORDS = {"no", "not", "never", "without", "cannot", "can't", "dont", "don't"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "for",
    "the",
    "to",
    "of",
    "is",
    "are",
    "we",
    "it",
    "this",
    "that",
    "be",
    "in",
    "on",
    "or",
    "with",
}

CANDIDATE_MAPPING = {
    "EntityCandidate": ("semantic", "fact"),
    "RelationshipCandidate": ("relational", "relationship"),
    "DecisionCandidate": ("decision", "technical"),
    "ProcedureCandidate": ("procedural", "procedure"),
    "PreferenceCandidate": ("semantic", "preference"),
    "IssueCandidate": ("episodic", "issue"),
    "EventCandidate": ("episodic", "event"),
    "ConstraintCandidate": ("semantic", "rule"),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _deterministic_uuid(*parts: object) -> str:
    material = "::".join(str(part) for part in parts)
    return str(uuid.uuid5(BRAINCLAW_NS, material))


def _artifact_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _polarity_signature(content: str) -> tuple[set[str], bool]:
    tokens = _normalize_text(content)
    filtered = {token for token in tokens if token not in STOPWORDS and token not in NEGATION_WORDS}
    negated = any(token in NEGATION_WORDS for token in tokens)
    return filtered, negated


def _topic_hints(content: str, kind: str, extraction) -> list[str]:
    hints: list[str] = []
    if kind:
        hints.append(kind)
    lowered = content.lower()
    for marker in [
        "postgresql",
        "neo4j",
        "weaviate",
        "lossless-claw",
        "brainclaw",
        "decision",
        "procedure",
        "constraint",
        "policy",
    ]:
        if marker in lowered:
            hints.append(marker)
    hints.extend(entity.name.lower() for entity in extraction.entities[:4])
    deduped: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        cleaned = hint.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped[:8]


def _candidate_targets(candidate_type: str, structured_payload: dict[str, Any]) -> tuple[str, str]:
    memory_class, memory_type = CANDIDATE_MAPPING[candidate_type]
    if candidate_type == "EntityCandidate":
        entity_type = str(structured_payload.get("entity_type") or "").lower()
        if entity_type in {"person", "agent"}:
            return ("identity", entity_type or "preference")
        if entity_type in {"project", "system", "repository", "file", "resource", "environment", "policy"}:
            return ("semantic", entity_type or "fact")
    if candidate_type == "RelationshipCandidate":
        return ("relational", str(structured_payload.get("relationship_type") or "relationship"))
    return (memory_class, memory_type)


def _candidate_content(summary_content: str, prefix: str | None = None) -> str:
    first_sentence = summary_content.strip().split(".")[0].strip()
    if prefix:
        return f"{prefix}: {first_sentence}".strip()
    return first_sentence or summary_content.strip()


class CanonicalLosslessRepository(Protocol):
    source_id: str
    source_type: str

    def upsert_integration_state(self, report: dict[str, Any]) -> None: ...

    def get_checkpoint(self) -> dict[str, Any] | None: ...

    def upsert_checkpoint(self, checkpoint: dict[str, Any]) -> None: ...

    def upsert_source_artifact(self, artifact: dict[str, Any]) -> tuple[str, bool]: ...

    def upsert_memory_candidate(self, candidate: dict[str, Any]) -> str: ...

    def list_memory_items(self) -> list[dict[str, Any]]: ...

    def upsert_memory_item(self, memory_item: dict[str, Any]) -> tuple[str, bool]: ...

    def mark_backfill(self, memory_item_id: str, target: str, status: str = "pending") -> None: ...

    def record_dead_letter(self, artifact: dict[str, Any]) -> None: ...

    def update_rebuild_checkpoint(self, target: str, payload: dict[str, Any]) -> None: ...


class InMemoryLosslessRepository:
    """Test repository that mimics canonical persistence behavior."""

    def __init__(self, source_id: str, source_type: str):
        self.source_id = source_id
        self.source_type = source_type
        self.integration_state: dict[str, Any] = {}
        self.checkpoint: dict[str, Any] | None = None
        self.source_artifacts: dict[str, dict[str, Any]] = {}
        self.source_artifact_keys: dict[str, str] = {}
        self.source_artifact_index: dict[str, str] = {}
        self.memory_candidates: dict[str, dict[str, Any]] = {}
        self.memory_items: dict[str, dict[str, Any]] = {}
        self.derived_backfill_state: dict[str, dict[str, Any]] = {}
        self.dead_letter_artifacts: dict[str, dict[str, Any]] = {}
        self.rebuild_checkpoints: dict[str, dict[str, Any]] = {}

    def upsert_integration_state(self, report: dict[str, Any]) -> None:
        now = _utcnow().isoformat()
        existing = dict(self.integration_state)
        compatibility_state = report["compatibility_state"]
        reason_code = report.get("reason_code")
        self.integration_state = {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "compatibility_state": compatibility_state,
            "reason_code": reason_code,
            "last_successful_gate_evaluated_at": now if compatibility_state == CompatibilityState.INSTALLED_COMPATIBLE.value else existing.get("last_successful_gate_evaluated_at"),
            "last_degraded_reason_code": reason_code if compatibility_state == CompatibilityState.INSTALLED_DEGRADED.value else existing.get("last_degraded_reason_code"),
            "last_degraded_transition_at": now if compatibility_state == CompatibilityState.INSTALLED_DEGRADED.value else existing.get("last_degraded_transition_at"),
            "last_successful_supported_profile": report.get("supported_profile") or existing.get("last_successful_supported_profile"),
            "updated_at": now,
        }

    def get_checkpoint(self) -> dict[str, Any] | None:
        return dict(self.checkpoint) if self.checkpoint else None

    def upsert_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self.checkpoint = dict(checkpoint)

    def upsert_source_artifact(self, artifact: dict[str, Any]) -> tuple[str, bool]:
        key = "::".join(
            [
                artifact["source_plugin"],
                artifact["source_scope_key"],
                artifact["source_artifact_type"],
                artifact["source_artifact_id"],
                str(artifact.get("source_created_at") or ""),
                artifact["artifact_hash"],
            ]
        )
        if key in self.source_artifact_keys:
            artifact_id = self.source_artifact_keys[key]
            self.source_artifacts[artifact_id].update(dict(artifact))
            return artifact_id, False

        artifact_id = _deterministic_uuid("source_artifact", key)
        stored = dict(artifact)
        stored["id"] = artifact_id
        self.source_artifacts[artifact_id] = stored
        self.source_artifact_keys[key] = artifact_id
        self.source_artifact_index[artifact["source_artifact_id"]] = artifact_id
        return artifact_id, True

    def upsert_memory_candidate(self, candidate: dict[str, Any]) -> str:
        candidate_id = candidate.get("id") or _deterministic_uuid(
            "candidate",
            candidate["source_artifact_id"],
            candidate["candidate_type"],
            candidate["content"],
        )
        stored = dict(candidate)
        stored["id"] = candidate_id
        self.memory_candidates[candidate_id] = stored
        return candidate_id

    def list_memory_items(self) -> list[dict[str, Any]]:
        return list(self.memory_items.values())

    def seed_memory_item(self, **memory_item: Any) -> str:
        memory_id = _deterministic_uuid("seed", memory_item.get("content"))
        stored = {"id": memory_id, **memory_item}
        self.memory_items[memory_id] = stored
        return memory_id

    def upsert_memory_item(self, memory_item: dict[str, Any]) -> tuple[str, bool]:
        memory_id = memory_item.get("id") or _deterministic_uuid(
            "memory_item",
            memory_item["source_artifact_ref"],
            memory_item["candidate_type"],
            memory_item["content"],
        )
        created = memory_id not in self.memory_items
        stored = dict(memory_item)
        stored["id"] = memory_id
        self.memory_items[memory_id] = stored
        return memory_id, created

    def mark_backfill(self, memory_item_id: str, target: str, status: str = "pending") -> None:
        key = f"{memory_item_id}:{target}"
        self.derived_backfill_state[key] = {
            "memory_item_id": memory_item_id,
            "target": target,
            "status": status,
            "updated_at": _utcnow().isoformat(),
        }

    def record_dead_letter(self, artifact: dict[str, Any]) -> None:
        dead_letter_id = _deterministic_uuid(
            "dead_letter",
            artifact.get("source_artifact_id"),
            artifact.get("artifact_hash"),
            artifact.get("reason_code"),
        )
        stored = dict(artifact)
        stored["id"] = dead_letter_id
        self.dead_letter_artifacts[dead_letter_id] = stored

    def update_rebuild_checkpoint(self, target: str, payload: dict[str, Any]) -> None:
        self.rebuild_checkpoints[target] = {
            "target": target,
            **dict(payload),
        }


class LosslessClawSyncEngine:
    """Orchestrates canonical import, candidate extraction, and replay-safe promotion."""

    def __init__(self, adapter: LosslessClawAdapter | None, repository: CanonicalLosslessRepository):
        self.adapter = adapter
        self.repository = repository

    def sync(self, mode: str = "incremental") -> dict[str, Any]:
        if self.adapter is None:
            raise ValueError("LosslessClawSyncEngine requires an adapter for sync operations")
        report = self.adapter.detect().to_dict()
        self.repository.upsert_integration_state(report)

        if report["compatibility_state"] != CompatibilityState.INSTALLED_COMPATIBLE.value:
            return {
                "status": "skipped",
                "mode": mode,
                "compatibility_state": report["compatibility_state"],
                "reason_code": report.get("reason_code"),
                "source_artifact_count": 0,
                "promoted_count": 0,
                "blocked_count": 0,
                "duplicate_artifact_count": 0,
            }

        checkpoint = None if mode in {"bootstrap", "repair"} else self.repository.get_checkpoint()
        last_created_at = checkpoint.get("last_created_at") if checkpoint else None
        last_artifact_id = checkpoint.get("last_artifact_id") if checkpoint else None

        source_artifact_count = 0
        promoted_count = 0
        blocked_count = 0
        duplicate_artifact_count = 0

        for summary in self.adapter.iter_summary_artifacts(
            last_created_at=last_created_at,
            last_artifact_id=last_artifact_id,
        ):
            policy = self.adapter.classify_session_statefulness(summary["source_session_id"])
            if policy.statefulness == "ignored":
                continue

            artifact = self._build_source_artifact(summary, report, policy.statefulness)
            artifact_id, created = self.repository.upsert_source_artifact(artifact)
            if not created:
                duplicate_artifact_count += 1
                continue

            source_artifact_count += 1

            candidates = self._extract_candidates(summary, artifact_id)
            for candidate in candidates:
                candidate["statefulness"] = policy.statefulness
                candidate["visibility_scope"] = artifact["visibility_scope"]
                candidate["owner_id"] = artifact.get("owner_id")
                candidate["access_control"] = dict(artifact["access_control"])
                candidate["promotion_status"] = "pending"
                candidate["blocked_reason_code"] = None
                candidate["contradiction_detected"] = False
                candidate["promoted_memory_item_id"] = None

                blocked_reason = self._blocked_reason(candidate, promotable=policy.promotable)
                if blocked_reason is not None:
                    candidate["promotion_status"] = "blocked"
                    candidate["blocked_reason_code"] = blocked_reason
                    if blocked_reason == ReasonCode.CONTRADICTED.value:
                        candidate["contradiction_detected"] = True
                    blocked_count += 1
                else:
                    memory_item = self._build_memory_item(candidate, summary, artifact)
                    memory_item_id, created_memory = self.repository.upsert_memory_item(memory_item)
                    candidate["promotion_status"] = "promoted"
                    candidate["promoted_memory_item_id"] = memory_item_id
                    if created_memory:
                        promoted_count += 1
                        for target in self._derived_targets(candidate):
                            self.repository.mark_backfill(memory_item_id, target)

                self.repository.upsert_memory_candidate(candidate)

            self.repository.upsert_checkpoint(
                {
                    "source_id": self.repository.source_id,
                    "source_type": self.repository.source_type,
                    "last_created_at": summary["source_created_at"],
                    "last_artifact_id": summary["source_artifact_id"],
                    "last_successful_import_ref": artifact_id,
                    "status": "completed",
                    "retry_count": 0,
                    "replay_marker": f"{summary['source_created_at']}::{summary['source_artifact_id']}",
                }
            )

        return {
            "status": "completed",
            "mode": mode,
            "compatibility_state": report["compatibility_state"],
            "reason_code": report.get("reason_code"),
            "source_artifact_count": source_artifact_count,
            "promoted_count": promoted_count,
            "blocked_count": blocked_count,
            "duplicate_artifact_count": duplicate_artifact_count,
        }

    def rebuild(self, target: str) -> dict[str, Any]:
        normalized = str(target or "").strip().lower()
        if normalized not in {"weaviate", "neo4j"}:
            return {"status": "failed", "error": "target must be weaviate or neo4j"}

        memory_items = self.repository.list_memory_items()
        for memory_item in memory_items:
            self.repository.mark_backfill(memory_item["id"], normalized, status="pending")

        self.repository.update_rebuild_checkpoint(
            normalized,
            {
                "status": "completed",
                "checkpoint_ref": _deterministic_uuid("rebuild", normalized, len(memory_items)),
                "last_validated_at": _utcnow().isoformat(),
                "last_validated_target_state": {"memory_item_count": len(memory_items)},
            },
        )
        return {
            "status": "completed",
            "target": normalized,
            "memory_item_count": len(memory_items),
        }

    def _build_source_artifact(
        self,
        summary: dict[str, Any],
        report: dict[str, Any],
        statefulness: str,
    ) -> dict[str, Any]:
        payload = {
            "content": summary["content"],
            "kind": summary["kind"],
            "source_summary_id": summary["source_artifact_id"],
            "source_session_id": summary["source_session_id"],
            "source_conversation_id": summary["source_conversation_id"],
            "source_parent_summary_id": summary.get("source_parent_summary_id"),
            "summary_depth": summary.get("summary_depth"),
            "topic_hints": summary["topic_hints"],
            "original_message_ids": summary["original_message_ids"],
            "file_ids": summary.get("file_ids", []),
        }
        return {
            "source_plugin": "lossless-claw",
            "source_artifact_type": "lcm_summary",
            "source_artifact_id": summary["source_artifact_id"],
            "source_scope_key": f"session:{summary['source_session_id']}",
            "source_created_at": summary["source_created_at"],
            "source_session_id": summary["source_session_id"],
            "source_summary_id": summary["source_artifact_id"],
            "source_conversation_id": summary["source_conversation_id"],
            "source_parent_summary_id": summary.get("source_parent_summary_id"),
            "summary_depth": summary.get("summary_depth"),
            "artifact_hash": _artifact_hash(payload),
            "payload": payload,
            "topic_hints": list(summary["topic_hints"]),
            "raw_anchor_ids": list(summary["original_message_ids"]),
            "signer_identity": None,
            "plugin_hash": None,
            "runtime_hash": None,
            "verification_result": "unavailable",
            "compatibility_state": report["compatibility_state"],
            "reason_code": report.get("reason_code"),
            "workspace_id": None,
            "agent_id": None,
            "session_id": summary["source_session_id"],
            "project_id": None,
            "user_id": None,
            "visibility_scope": "owner",
            "owner_id": None,
            "statefulness": statefulness,
            "access_control": {"write_policy": "owner_only"},
            "import_status": "imported",
            "import_error": None,
            "imported_at": _utcnow().isoformat(),
        }

    def _extract_candidates(self, summary: dict[str, Any], source_artifact_ref: str) -> list[dict[str, Any]]:
        content = summary["content"]
        extraction = extract_all(content)
        topic_hints = summary["topic_hints"]
        candidates: list[dict[str, Any]] = []

        for entity in extraction.entities:
            memory_class_target, memory_type_target = _candidate_targets(
                "EntityCandidate",
                {"entity_type": entity.entity_type},
            )
            candidates.append(
                {
                    "source_artifact_id": source_artifact_ref,
                    "candidate_type": "EntityCandidate",
                    "memory_class_target": memory_class_target,
                    "memory_type_target": memory_type_target,
                    "content": entity.name,
                    "structured_payload": {
                        "entity_type": entity.entity_type,
                        "canonical_name": entity.canonical_name,
                        "aliases": list(entity.aliases),
                    },
                    "raw_extraction_confidence": round(max(entity.confidence, 0.9), 2),
                    "interpretive_confidence": 0.0,
                    "topic_hint_match_score": 1.0 if entity.name.lower() in topic_hints else 0.65,
                    "interpretation_flag": "EXTRACTIVE",
                    "extractor_version": "lossless-sync-v1",
                    "derivation_path": ["lcm_summary", "entities"],
                    "topic_hints": list(topic_hints),
                    "original_message_ids": list(summary["original_message_ids"]),
                    "source_session_id": summary["source_session_id"],
                }
            )

        for relationship in extraction.relationships:
            memory_class_target, memory_type_target = _candidate_targets(
                "RelationshipCandidate",
                {"relationship_type": relationship.relationship_type},
            )
            candidates.append(
                {
                    "source_artifact_id": source_artifact_ref,
                    "candidate_type": "RelationshipCandidate",
                    "memory_class_target": memory_class_target,
                    "memory_type_target": memory_type_target,
                    "content": relationship.evidence or f"{relationship.source_entity_id} {relationship.relationship_type} {relationship.target_entity_id}",
                    "structured_payload": {
                        "relationship_type": relationship.relationship_type,
                        "source_entity_id": relationship.source_entity_id,
                        "target_entity_id": relationship.target_entity_id,
                    },
                    "raw_extraction_confidence": round(min(relationship.confidence, 0.69), 2),
                    "interpretive_confidence": 0.72,
                    "topic_hint_match_score": 0.65,
                    "interpretation_flag": "INTERPRETIVE",
                    "extractor_version": "lossless-sync-v1",
                    "derivation_path": ["lcm_summary", "relationships"],
                    "topic_hints": list(topic_hints),
                    "original_message_ids": list(summary["original_message_ids"]),
                    "source_session_id": summary["source_session_id"],
                }
            )

        heuristic_specs = [
            ("DecisionCandidate", ("decided to", "decision", "agreed to"), 0.9, 0.78, 0.8, "EXTRACTIVE", "decision"),
            ("ProcedureCandidate", ("procedure:", "steps:", "workflow:", "how to"), 0.88, 0.74, 0.75, "EXTRACTIVE", "procedure"),
            ("PreferenceCandidate", ("i prefer", "prefer", "preference"), 0.74, 0.72, 0.62, "INTERPRETIVE", "preference"),
            ("IssueCandidate", ("issue", "error", "failed", "problem", "bug"), 0.68, 0.71, 0.63, "INTERPRETIVE", "issue"),
            ("EventCandidate", ("session", "event", "happened", "observed"), 0.66, 0.68, 0.55, "INTERPRETIVE", "event"),
            ("ConstraintCandidate", ("must", "never", "do not", "required", "cannot"), 0.9, 0.78, 0.8, "EXTRACTIVE", "constraint"),
        ]
        lowered = content.lower()
        for candidate_type, markers, raw_conf, interpretive_conf, topic_score, interpretation_flag, label in heuristic_specs:
            if not any(marker in lowered for marker in markers):
                continue
            memory_class_target, memory_type_target = _candidate_targets(candidate_type, {})
            candidates.append(
                {
                    "source_artifact_id": source_artifact_ref,
                    "candidate_type": candidate_type,
                    "memory_class_target": memory_class_target,
                    "memory_type_target": memory_type_target,
                    "content": _candidate_content(content, label),
                    "structured_payload": {"kind": summary["kind"], "label": label},
                    "raw_extraction_confidence": raw_conf,
                    "interpretive_confidence": interpretive_conf,
                    "topic_hint_match_score": topic_score,
                    "interpretation_flag": interpretation_flag,
                    "extractor_version": "lossless-sync-v1",
                    "derivation_path": ["lcm_summary", label],
                    "topic_hints": list(topic_hints),
                    "original_message_ids": list(summary["original_message_ids"]),
                    "source_session_id": summary["source_session_id"],
                }
            )

        return candidates

    def _passes_thresholds(self, candidate: dict[str, Any]) -> bool:
        raw = float(candidate.get("raw_extraction_confidence") or 0.0)
        interpretive = float(candidate.get("interpretive_confidence") or 0.0)
        topic = float(candidate.get("topic_hint_match_score") or 0.0)
        if raw >= 0.85:
            return True
        return interpretive >= 0.70 and topic >= 0.60

    def _is_contradicted(self, candidate: dict[str, Any]) -> bool:
        candidate_terms, candidate_negated = _polarity_signature(candidate["content"])
        if not candidate_terms:
            return False
        for memory_item in self.repository.list_memory_items():
            existing_terms, existing_negated = _polarity_signature(str(memory_item.get("content") or ""))
            if len(candidate_terms & existing_terms) >= 3 and candidate_negated != existing_negated:
                return True
        return False

    def _blocked_reason(self, candidate: dict[str, Any], *, promotable: bool) -> str | None:
        if not promotable:
            return ReasonCode.STATELESS_SESSION.value
        if candidate.get("access_control", {}).get("write_policy") not in {None, "owner_only"}:
            return ReasonCode.ACL_DENIED.value
        if self._is_contradicted(candidate):
            return ReasonCode.CONTRADICTED.value
        if not self._passes_thresholds(candidate):
            return ReasonCode.LOW_CONFIDENCE.value
        return None

    def _build_memory_item(
        self,
        candidate: dict[str, Any],
        summary: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "source_artifact_ref": artifact["source_artifact_id"],
            "candidate_type": candidate["candidate_type"],
            "memory_class": candidate["memory_class_target"],
            "memory_type": candidate["memory_type_target"],
            "status": "active",
            "content": candidate["content"],
            "source_session_id": summary["source_session_id"],
            "source_message_id": summary["original_message_ids"][0] if summary["original_message_ids"] else None,
            "confidence": candidate.get("raw_extraction_confidence") or candidate.get("interpretive_confidence") or 0.5,
            "user_confirmed": False,
            "visibility_scope": candidate["visibility_scope"],
            "access_control": dict(candidate["access_control"]),
            "retention_policy": "default",
            "metadata": {
                "memory_class": candidate["memory_class_target"],
                "memory_type": candidate["memory_type_target"],
                "source_plugin": "lossless-claw",
                "source_summary_id": summary["source_artifact_id"],
                "source_artifact_ref": artifact["source_artifact_id"],
                "source_session_id": summary["source_session_id"],
                "original_message_ids": list(summary["original_message_ids"]),
                "topic_hints": list(candidate["topic_hints"]),
                "interpretation_flag": candidate["interpretation_flag"],
                "verification_result": artifact["verification_result"],
            },
            "extraction_metadata": {
                "source_artifact_ref": artifact["source_artifact_id"],
                "source_summary_id": summary["source_artifact_id"],
                "source_session_id": summary["source_session_id"],
                "original_message_ids": list(summary["original_message_ids"]),
                "import_timestamp": artifact["imported_at"],
                "extractor_version": candidate["extractor_version"],
                "raw_extraction_confidence": candidate["raw_extraction_confidence"],
                "interpretive_confidence": candidate["interpretive_confidence"],
                "topic_hint_match_score": candidate["topic_hint_match_score"],
                "topic_hints": list(candidate["topic_hints"]),
                "derivation_path": list(candidate["derivation_path"]),
                "interpretation_flag": candidate["interpretation_flag"],
                "user_confirmation_state": "unconfirmed",
                "supersession_id": None,
                "verification_result": artifact["verification_result"],
                "signer_identity": artifact["signer_identity"],
                "plugin_hash": artifact["plugin_hash"],
                "runtime_hash": artifact["runtime_hash"],
            },
        }

    def _derived_targets(self, candidate: dict[str, Any]) -> list[str]:
        targets = ["weaviate"]
        if candidate["candidate_type"] in {"EntityCandidate", "RelationshipCandidate", "DecisionCandidate"}:
            targets.append("neo4j")
        return targets


class PostgresLosslessRepository:
    """Synchronous PostgreSQL repository for bridge entry points."""

    def __init__(self, dsn: str, source_id: str, source_type: str):
        import psycopg2

        self._psycopg2 = psycopg2
        self._json = psycopg2.extras.Json
        self.dsn = dsn
        self.source_id = source_id
        self.source_type = source_type

    def _connect(self):
        return self._psycopg2.connect(self.dsn)

    def upsert_integration_state(self, report: dict[str, Any]) -> None:
        now = _utcnow()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO integration_states (
                        source_id,
                        source_type,
                        compatibility_state,
                        reason_code,
                        last_successful_gate_evaluated_at,
                        last_degraded_reason_code,
                        last_degraded_transition_at,
                        last_successful_supported_profile,
                        metadata,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_id, source_type) DO UPDATE SET
                        compatibility_state = EXCLUDED.compatibility_state,
                        reason_code = EXCLUDED.reason_code,
                        last_successful_gate_evaluated_at = COALESCE(EXCLUDED.last_successful_gate_evaluated_at, integration_states.last_successful_gate_evaluated_at),
                        last_degraded_reason_code = COALESCE(EXCLUDED.last_degraded_reason_code, integration_states.last_degraded_reason_code),
                        last_degraded_transition_at = COALESCE(EXCLUDED.last_degraded_transition_at, integration_states.last_degraded_transition_at),
                        last_successful_supported_profile = COALESCE(EXCLUDED.last_successful_supported_profile, integration_states.last_successful_supported_profile),
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        self.source_id,
                        self.source_type,
                        report["compatibility_state"],
                        report.get("reason_code"),
                        now if report["compatibility_state"] == CompatibilityState.INSTALLED_COMPATIBLE.value else None,
                        report.get("reason_code") if report["compatibility_state"] == CompatibilityState.INSTALLED_DEGRADED.value else None,
                        now if report["compatibility_state"] == CompatibilityState.INSTALLED_DEGRADED.value else None,
                        report.get("supported_profile"),
                        self._json(report),
                        now,
                    ),
                )

    def get_checkpoint(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=self._psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM source_sync_checkpoints
                    WHERE source_id = %s AND source_type = %s
                    """,
                    (self.source_id, self.source_type),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def upsert_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_sync_checkpoints (
                        source_id,
                        source_type,
                        checkpoint_position,
                        last_created_at,
                        last_artifact_id,
                        last_successful_import_ref,
                        status,
                        retry_count,
                        replay_marker,
                        failed_range,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_id, source_type) DO UPDATE SET
                        checkpoint_position = EXCLUDED.checkpoint_position,
                        last_created_at = EXCLUDED.last_created_at,
                        last_artifact_id = EXCLUDED.last_artifact_id,
                        last_successful_import_ref = EXCLUDED.last_successful_import_ref,
                        status = EXCLUDED.status,
                        retry_count = EXCLUDED.retry_count,
                        replay_marker = EXCLUDED.replay_marker,
                        failed_range = EXCLUDED.failed_range,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        self.source_id,
                        self.source_type,
                        checkpoint.get("replay_marker"),
                        checkpoint.get("last_created_at"),
                        checkpoint.get("last_artifact_id"),
                        checkpoint.get("last_successful_import_ref"),
                        checkpoint.get("status", "completed"),
                        checkpoint.get("retry_count", 0),
                        checkpoint.get("replay_marker"),
                        self._json(checkpoint.get("failed_range") or {}),
                        _utcnow(),
                    ),
                )

    def upsert_source_artifact(self, artifact: dict[str, Any]) -> tuple[str, bool]:
        artifact_id = _deterministic_uuid(
            "source_artifact",
            artifact["source_plugin"],
            artifact["source_scope_key"],
            artifact["source_artifact_type"],
            artifact["source_artifact_id"],
            artifact.get("source_created_at"),
            artifact["artifact_hash"],
        )
        created = False
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM source_artifacts WHERE id = %s", (artifact_id,))
                created = cur.fetchone() is None
                cur.execute(
                    """
                    INSERT INTO source_artifacts (
                        id,
                        source_plugin,
                        source_artifact_type,
                        source_artifact_id,
                        source_scope_key,
                        source_created_at,
                        source_session_id,
                        source_summary_id,
                        source_conversation_id,
                        source_parent_summary_id,
                        summary_depth,
                        artifact_hash,
                        payload,
                        topic_hints,
                        raw_anchor_ids,
                        signer_identity,
                        plugin_hash,
                        runtime_hash,
                        verification_result,
                        compatibility_state,
                        reason_code,
                        workspace_id,
                        agent_id,
                        session_id,
                        project_id,
                        user_id,
                        visibility_scope,
                        owner_id,
                        statefulness,
                        access_control,
                        import_status,
                        import_error,
                        imported_at,
                        updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        payload = EXCLUDED.payload,
                        topic_hints = EXCLUDED.topic_hints,
                        raw_anchor_ids = EXCLUDED.raw_anchor_ids,
                        compatibility_state = EXCLUDED.compatibility_state,
                        reason_code = EXCLUDED.reason_code,
                        import_status = EXCLUDED.import_status,
                        import_error = EXCLUDED.import_error,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        artifact_id,
                        artifact["source_plugin"],
                        artifact["source_artifact_type"],
                        artifact["source_artifact_id"],
                        artifact["source_scope_key"],
                        artifact.get("source_created_at"),
                        artifact.get("source_session_id"),
                        artifact.get("source_summary_id"),
                        artifact.get("source_conversation_id"),
                        artifact.get("source_parent_summary_id"),
                        artifact.get("summary_depth"),
                        artifact["artifact_hash"],
                        self._json(artifact["payload"]),
                        self._json(artifact["topic_hints"]),
                        self._json(artifact["raw_anchor_ids"]),
                        artifact.get("signer_identity"),
                        artifact.get("plugin_hash"),
                        artifact.get("runtime_hash"),
                        artifact.get("verification_result"),
                        artifact["compatibility_state"],
                        artifact.get("reason_code"),
                        artifact.get("workspace_id"),
                        artifact.get("agent_id"),
                        artifact.get("session_id"),
                        artifact.get("project_id"),
                        artifact.get("user_id"),
                        artifact.get("visibility_scope"),
                        artifact.get("owner_id"),
                        artifact.get("statefulness"),
                        self._json(artifact["access_control"]),
                        artifact.get("import_status"),
                        artifact.get("import_error"),
                        artifact.get("imported_at"),
                        _utcnow(),
                    ),
                )
        return artifact_id, created

    def upsert_memory_candidate(self, candidate: dict[str, Any]) -> str:
        candidate_id = _deterministic_uuid(
            "candidate",
            candidate["source_artifact_id"],
            candidate["candidate_type"],
            candidate["content"],
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memory_candidates (
                        id,
                        source_artifact_id,
                        candidate_type,
                        memory_class_target,
                        memory_type_target,
                        content,
                        structured_payload,
                        raw_extraction_confidence,
                        interpretive_confidence,
                        topic_hint_match_score,
                        interpretation_flag,
                        contradiction_detected,
                        blocked_reason_code,
                        promotion_status,
                        promoted_memory_item_id,
                        extractor_version,
                        derivation_path,
                        topic_hints,
                        original_message_ids,
                        supersession_id,
                        workspace_id,
                        agent_id,
                        session_id,
                        project_id,
                        user_id,
                        visibility_scope,
                        owner_id,
                        statefulness,
                        access_control,
                        updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        contradiction_detected = EXCLUDED.contradiction_detected,
                        blocked_reason_code = EXCLUDED.blocked_reason_code,
                        promotion_status = EXCLUDED.promotion_status,
                        promoted_memory_item_id = EXCLUDED.promoted_memory_item_id,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        candidate_id,
                        candidate["source_artifact_id"],
                        candidate["candidate_type"],
                        candidate["memory_class_target"],
                        candidate.get("memory_type_target"),
                        candidate["content"],
                        self._json(candidate["structured_payload"]),
                        candidate.get("raw_extraction_confidence"),
                        candidate.get("interpretive_confidence"),
                        candidate.get("topic_hint_match_score"),
                        candidate.get("interpretation_flag"),
                        candidate.get("contradiction_detected", False),
                        candidate.get("blocked_reason_code"),
                        candidate["promotion_status"],
                        candidate.get("promoted_memory_item_id"),
                        candidate.get("extractor_version"),
                        self._json(candidate["derivation_path"]),
                        self._json(candidate["topic_hints"]),
                        self._json(candidate["original_message_ids"]),
                        candidate.get("supersession_id"),
                        candidate.get("workspace_id"),
                        candidate.get("agent_id"),
                        candidate.get("source_session_id"),
                        candidate.get("project_id"),
                        candidate.get("user_id"),
                        candidate.get("visibility_scope"),
                        candidate.get("owner_id"),
                        candidate.get("statefulness"),
                        self._json(candidate["access_control"]),
                        _utcnow(),
                    ),
                )
        return candidate_id

    def list_memory_items(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=self._psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT id, content FROM memory_items WHERE is_current = TRUE")
                return [dict(row) for row in cur.fetchall()]

    def upsert_memory_item(self, memory_item: dict[str, Any]) -> tuple[str, bool]:
        memory_id = _deterministic_uuid(
            "memory_item",
            memory_item["source_artifact_ref"],
            memory_item["candidate_type"],
            memory_item["content"],
        )
        created = False
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM memory_items WHERE id = %s", (memory_id,))
                created = cur.fetchone() is None
                cur.execute(
                    """
                    INSERT INTO memory_items (
                        id,
                        memory_class,
                        memory_type,
                        status,
                        content,
                        source_session_id,
                        source_message_id,
                        extractor_name,
                        extractor_version,
                        extraction_timestamp,
                        extraction_confidence,
                        extraction_metadata,
                        confidence,
                        user_confirmed,
                        valid_from,
                        is_current,
                        visibility_scope,
                        access_control,
                        retention_policy,
                        metadata,
                        updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        extraction_confidence = EXCLUDED.extraction_confidence,
                        extraction_metadata = EXCLUDED.extraction_metadata,
                        confidence = EXCLUDED.confidence,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        memory_id,
                        memory_item["memory_class"],
                        memory_item["memory_type"],
                        memory_item["status"],
                        memory_item["content"],
                        memory_item.get("source_session_id"),
                        memory_item.get("source_message_id"),
                        "lossless-claw",
                        "lossless-sync-v1",
                        _utcnow(),
                        memory_item.get("confidence"),
                        self._json(memory_item["extraction_metadata"]),
                        memory_item.get("confidence"),
                        memory_item.get("user_confirmed", False),
                        _utcnow(),
                        True,
                        memory_item.get("visibility_scope", "owner"),
                        self._json(memory_item["access_control"]),
                        memory_item.get("retention_policy", "default"),
                        self._json(memory_item["metadata"]),
                        _utcnow(),
                    ),
                )
        return memory_id, created

    def mark_backfill(self, memory_item_id: str, target: str, status: str = "pending") -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO derived_backfill_state (memory_item_id, target, status, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (memory_item_id, target) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (memory_item_id, target, status, _utcnow()),
                )

    def record_dead_letter(self, artifact: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dead_letter_artifacts (
                        source_plugin,
                        source_artifact_type,
                        source_artifact_id,
                        artifact_hash,
                        reason_code,
                        error_message,
                        retry_count,
                        replay_eligible,
                        payload,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        artifact.get("source_plugin", "lossless-claw"),
                        artifact.get("source_artifact_type", "lcm_summary"),
                        artifact.get("source_artifact_id"),
                        artifact.get("artifact_hash"),
                        artifact.get("reason_code"),
                        artifact.get("error_message"),
                        artifact.get("retry_count", 0),
                        artifact.get("replay_eligible", True),
                        self._json(artifact.get("payload") or {}),
                        _utcnow(),
                    ),
                )

    def update_rebuild_checkpoint(self, target: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rebuild_checkpoints (
                        target,
                        checkpoint_ref,
                        last_validated_at,
                        last_validated_target_state,
                        status,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (target) DO UPDATE SET
                        checkpoint_ref = EXCLUDED.checkpoint_ref,
                        last_validated_at = EXCLUDED.last_validated_at,
                        last_validated_target_state = EXCLUDED.last_validated_target_state,
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        target,
                        payload.get("checkpoint_ref"),
                        payload.get("last_validated_at"),
                        self._json(payload.get("last_validated_target_state") or {}),
                        payload.get("status", "completed"),
                        _utcnow(),
                    ),
                )


def build_postgres_repository_from_env(
    source_id: str = "lossless-claw",
    source_type: str = "context_engine",
) -> PostgresLosslessRepository | None:
    dsn = os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        return None
    try:
        return PostgresLosslessRepository(dsn=dsn, source_id=source_id, source_type=source_type)
    except Exception:
        return None
