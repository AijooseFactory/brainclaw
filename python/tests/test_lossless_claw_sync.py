"""Behavior tests for BrainClaw's Lossless-Claw sync engine."""

from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path


def _seed_lcm_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE conversations (
              conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL
            );
            CREATE TABLE messages (
              message_id INTEGER PRIMARY KEY AUTOINCREMENT,
              conversation_id INTEGER NOT NULL,
              seq INTEGER NOT NULL,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              token_count INTEGER NOT NULL,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE summaries (
              summary_id TEXT PRIMARY KEY,
              conversation_id INTEGER NOT NULL,
              kind TEXT NOT NULL,
              depth INTEGER NOT NULL DEFAULT 0,
              content TEXT NOT NULL,
              token_count INTEGER NOT NULL,
              earliest_at TEXT,
              latest_at TEXT,
              descendant_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              file_ids TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE message_parts (
              part_id TEXT PRIMARY KEY,
              message_id INTEGER NOT NULL,
              session_id TEXT NOT NULL,
              part_type TEXT NOT NULL,
              ordinal INTEGER NOT NULL
            );
            CREATE TABLE summary_messages (
              summary_id TEXT NOT NULL,
              message_id INTEGER NOT NULL,
              ordinal INTEGER NOT NULL
            );
            CREATE TABLE summary_parents (
              summary_id TEXT NOT NULL,
              parent_summary_id TEXT NOT NULL,
              ordinal INTEGER NOT NULL
            );
            CREATE TABLE context_items (
              conversation_id INTEGER NOT NULL,
              ordinal INTEGER NOT NULL,
              item_type TEXT NOT NULL,
              message_id INTEGER,
              summary_id TEXT
            );
            CREATE TABLE large_files (
              file_id TEXT PRIMARY KEY,
              conversation_id INTEGER NOT NULL,
              storage_uri TEXT NOT NULL,
              exploration_summary TEXT
            );
            """
        )

        conn.executemany(
            "INSERT INTO conversations (conversation_id, session_id) VALUES (?, ?)",
            [
                (1, "stateful-session-1"),
                (2, "stateless-session-1"),
                (3, "tmp-session-1"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO summaries (
              summary_id, conversation_id, kind, depth, content, token_count,
              earliest_at, latest_at, descendant_count, created_at, file_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "sum-stateful",
                    1,
                    "conversation",
                    0,
                    "We decided to use PostgreSQL for BrainClaw. Never treat Lossless-Claw as canonical durable memory.",
                    32,
                    "2026-03-18T10:00:00Z",
                    "2026-03-18T10:10:00Z",
                    0,
                    "2026-03-18T10:10:00Z",
                    "[]",
                ),
                (
                    "sum-stateless",
                    2,
                    "conversation",
                    0,
                    "Procedure: 1. Restart ajf-openclaw. 2. Run migrations. 3. Verify the logs are healthy.",
                    24,
                    "2026-03-18T11:00:00Z",
                    "2026-03-18T11:10:00Z",
                    0,
                    "2026-03-18T11:10:00Z",
                    "[]",
                ),
                (
                    "sum-ignored",
                    3,
                    "conversation",
                    0,
                    "This ignored session should never be imported.",
                    12,
                    "2026-03-18T12:00:00Z",
                    "2026-03-18T12:05:00Z",
                    0,
                    "2026-03-18T12:05:00Z",
                    "[]",
                ),
            ],
        )
        conn.executemany(
            "INSERT INTO messages (message_id, conversation_id, seq, role, content, token_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (10, 1, 1, "assistant", "We decided to use PostgreSQL for BrainClaw.", 12, "2026-03-18T10:01:00Z"),
                (20, 2, 1, "assistant", "Procedure: Restart ajf-openclaw.", 8, "2026-03-18T11:01:00Z"),
            ],
        )
        conn.executemany(
            "INSERT INTO summary_messages (summary_id, message_id, ordinal) VALUES (?, ?, ?)",
            [
                ("sum-stateful", 10, 0),
                ("sum-stateless", 20, 0),
            ],
        )
        conn.executemany(
            "INSERT INTO message_parts (part_id, message_id, session_id, part_type, ordinal) VALUES (?, ?, ?, ?, ?)",
            [
                ("part-10", 10, "stateful-session-1", "text", 0),
                ("part-20", 20, "stateless-session-1", "text", 0),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _build_engine(tmp_path: Path):
    from openclaw_memory.integration.lossless_adapter import (
        LosslessClawAdapter,
        OpenClawRuntimeSnapshot,
    )
    from openclaw_memory.integration.lossless_sync import (
        InMemoryLosslessRepository,
        LosslessClawSyncEngine,
    )

    db_path = tmp_path / "lossless.db"
    _seed_lcm_db(db_path)

    adapter = LosslessClawAdapter(
        runtime=OpenClawRuntimeSnapshot(
            openclaw_version="2026.3.14",
            memory_slot="brainclaw",
            context_engine_slot="lossless-claw",
            plugin_enabled=True,
            plugin_installed=True,
            plugin_version="0.4.0",
            plugin_install_path=str(tmp_path),
            tool_names=["lcm_grep", "lcm_describe", "lcm_expand_query"],
        ),
        db_path=str(db_path),
        plugin_config={
            "dbPath": str(db_path),
            "ignoreSessionPatterns": ["^tmp-"],
            "statelessSessionPatterns": ["^stateless-"],
        },
    )
    repo = InMemoryLosslessRepository(source_id="lossless-claw", source_type="context_engine")
    engine = LosslessClawSyncEngine(adapter=adapter, repository=repo)
    return engine, repo


def test_sync_engine_persists_state_imports_stateful_artifacts_and_blocks_stateless_promotion(tmp_path):
    from openclaw_memory.integration.lossless_adapter import CompatibilityState, ReasonCode

    engine, repo = _build_engine(tmp_path)

    result = engine.sync(mode="bootstrap")

    assert result["status"] == "completed"
    assert result["compatibility_state"] == CompatibilityState.INSTALLED_COMPATIBLE.value
    assert result["source_artifact_count"] == 2
    assert result["promoted_count"] >= 1
    assert repo.integration_state["compatibility_state"] == CompatibilityState.INSTALLED_COMPATIBLE.value
    assert repo.checkpoint["last_artifact_id"] == "sum-stateless"
    assert all(artifact["source_artifact_id"] != "sum-ignored" for artifact in repo.source_artifacts.values())

    stateless_candidates = [
        candidate
        for candidate in repo.memory_candidates.values()
        if candidate["source_artifact_id"] == repo.source_artifact_index["sum-stateless"]
    ]
    assert stateless_candidates
    assert all(candidate["promotion_status"] == "blocked" for candidate in stateless_candidates)
    assert {candidate["blocked_reason_code"] for candidate in stateless_candidates} == {
        ReasonCode.STATELESS_SESSION.value
    }

    promoted_sessions = {memory["source_session_id"] for memory in repo.memory_items.values()}
    assert "stateless-session-1" not in promoted_sessions


def test_sync_engine_replay_is_deterministic_and_does_not_duplicate_promotions(tmp_path):
    engine, repo = _build_engine(tmp_path)

    first = engine.sync(mode="bootstrap")
    second = engine.sync(mode="repair")

    assert first["source_artifact_count"] == len(repo.source_artifacts)
    assert second["source_artifact_count"] == 0
    assert second["duplicate_artifact_count"] == len(repo.source_artifacts)
    assert len(repo.source_artifacts) == first["source_artifact_count"]
    assert len(repo.memory_items) == first["promoted_count"]


def test_repair_mode_reprocesses_existing_artifacts_without_duplicate_source_rows(tmp_path):
    engine, repo = _build_engine(tmp_path)

    first = engine.sync(mode="bootstrap")

    def patched_extract(summary, source_artifact_ref):
        if summary["source_artifact_id"] != "sum-stateful":
            return []
        return [
            {
                "source_artifact_id": source_artifact_ref,
                "candidate_type": "ProcedureCandidate",
                "memory_class_target": "procedural",
                "memory_type_target": "procedure",
                "content": "Procedure: restart ajf-openclaw and verify logs",
                "structured_payload": {"kind": summary["kind"], "label": "procedure"},
                "raw_extraction_confidence": 0.9,
                "interpretive_confidence": 0.0,
                "topic_hint_match_score": 0.8,
                "interpretation_flag": "EXTRACTIVE",
                "extractor_version": "lossless-sync-v2",
                "derivation_path": ["lcm_summary", "procedure"],
                "topic_hints": list(summary["topic_hints"]),
                "original_message_ids": list(summary["original_message_ids"]),
                "source_session_id": summary["source_session_id"],
            }
        ]

    engine._extract_candidates = patched_extract  # type: ignore[method-assign]

    second = engine.sync(mode="repair")

    assert first["source_artifact_count"] == len(repo.source_artifacts)
    assert second["source_artifact_count"] == 0
    assert second["duplicate_artifact_count"] == len(repo.source_artifacts)
    assert second["promoted_count"] == 1
    assert any(
        candidate["candidate_type"] == "ProcedureCandidate"
        and candidate["extractor_version"] == "lossless-sync-v2"
        for candidate in repo.memory_candidates.values()
    )


def test_sync_engine_blocks_contradicted_candidates_without_graph_edges(tmp_path):
    from openclaw_memory.integration.lossless_adapter import ReasonCode

    engine, repo = _build_engine(tmp_path)
    repo.seed_memory_item(
        content="We decided not to use PostgreSQL for BrainClaw.",
        memory_class="decision",
        memory_type="technical",
        source_session_id="prior-session",
    )

    result = engine.sync(mode="bootstrap")

    assert result["blocked_count"] >= 1
    blocked = [
        candidate
        for candidate in repo.memory_candidates.values()
        if candidate["blocked_reason_code"] == ReasonCode.CONTRADICTED.value
    ]
    assert blocked
    assert not any(
        memory["content"] == blocked_candidate["content"]
        for blocked_candidate in blocked
        for memory in repo.memory_items.values()
    )


def test_build_postgres_repository_from_env_constructs_repository_when_driver_is_installed(monkeypatch):
    from openclaw_memory.integration.lossless_sync import (
        PostgresLosslessRepository,
        build_postgres_repository_from_env,
    )

    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.__path__ = []  # Mark as package so submodule imports work.
    fake_extras = types.ModuleType("psycopg2.extras")

    class _Json:
        def __init__(self, value):
            self.value = value

    fake_extras.Json = _Json
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake_extras)

    monkeypatch.setenv(
        "POSTGRES_URL",
        "postgresql://brainclaw:brainclaw_secret@postgres:5432/brainclaw",
    )

    repository = build_postgres_repository_from_env()

    assert isinstance(repository, PostgresLosslessRepository)


def test_build_memory_item_preserves_non_uuid_lcm_ids_in_metadata_and_not_uuid_columns(tmp_path):
    engine, _repo = _build_engine(tmp_path)

    summaries = list(engine.adapter.iter_summary_artifacts())
    summary = next(item for item in summaries if item["source_artifact_id"] == "sum-stateful")
    report = engine.adapter.detect().to_dict()
    artifact = engine._build_source_artifact(summary, report, "stateful")
    candidate = engine._extract_candidates(summary, artifact["source_artifact_id"])[0]
    candidate["visibility_scope"] = artifact["visibility_scope"]
    candidate["access_control"] = dict(artifact["access_control"])
    memory_item = engine._build_memory_item(candidate, summary, artifact)

    assert memory_item["source_session_id"] is None
    assert memory_item["source_message_id"] is None
    assert memory_item["metadata"]["source_session_id"] == "stateful-session-1"
    assert memory_item["metadata"]["original_message_ids"] == ["10"]


def test_extract_candidates_emits_relationship_and_procedure_candidates_for_operational_lcm_summary(tmp_path):
    engine, _repo = _build_engine(tmp_path)

    summary = {
        "source_artifact_id": "sum-operational",
        "source_session_id": "stateful-session-ops",
        "source_conversation_id": 99,
        "kind": "conversation",
        "summary_depth": 0,
        "content": (
            "1. Restart ajf-openclaw. "
            "2. Run BrainClaw migrations. "
            "3. Verify the logs are healthy. "
            "BrainClaw uses PostgreSQL for canonical storage."
        ),
        "source_created_at": "2026-03-18T13:00:00Z",
        "earliest_source_timestamp": "2026-03-18T12:55:00Z",
        "latest_source_timestamp": "2026-03-18T13:00:00Z",
        "file_ids": [],
        "source_parent_summary_id": None,
        "topic_hints": ["brainclaw", "postgresql", "procedure"],
        "original_message_ids": ["1001"],
    }

    candidates = engine._extract_candidates(summary, "artifact-operational")
    candidate_types = {candidate["candidate_type"] for candidate in candidates}
    relationship_candidate = next(
        candidate for candidate in candidates if candidate["candidate_type"] == "RelationshipCandidate"
    )

    assert "ProcedureCandidate" in candidate_types
    assert "RelationshipCandidate" in candidate_types
    assert relationship_candidate["structured_payload"]["source_entity_name"] == "BrainClaw"
    assert relationship_candidate["structured_payload"]["target_entity_name"] == "PostgreSQL"


def test_graph_records_from_promoted_candidates_links_relationships_by_stable_names():
    from openclaw_memory.integration.lossless_sync import _graph_records_from_candidates

    candidates = [
        {
            "candidate_type": "EntityCandidate",
            "source_artifact_id": "artifact-a",
            "content": "BrainClaw",
            "structured_payload": {
                "entity_type": "system",
                "canonical_name": "brainclaw",
                "extracted_entity_id": "entity-src-a",
            },
            "promoted_memory_item_id": "entity-brainclaw",
            "raw_extraction_confidence": 0.9,
            "interpretive_confidence": 0.0,
            "promotion_status": "promoted",
        },
        {
            "candidate_type": "EntityCandidate",
            "source_artifact_id": "artifact-a",
            "content": "PostgreSQL",
            "structured_payload": {
                "entity_type": "system",
                "canonical_name": "postgresql",
                "extracted_entity_id": "entity-src-b",
            },
            "promoted_memory_item_id": "entity-postgresql",
            "raw_extraction_confidence": 0.9,
            "interpretive_confidence": 0.0,
            "promotion_status": "promoted",
        },
        {
            "candidate_type": "RelationshipCandidate",
            "source_artifact_id": "artifact-a",
            "content": "BrainClaw uses PostgreSQL",
            "structured_payload": {
                "relationship_type": "uses",
                "source_entity_id": "entity-src-a",
                "target_entity_id": "entity-src-b",
                "source_entity_name": "BrainClaw",
                "target_entity_name": "PostgreSQL",
                "source_entity_canonical_name": "brainclaw",
                "target_entity_canonical_name": "postgresql",
                "evidence": "BrainClaw uses PostgreSQL",
            },
            "promoted_memory_item_id": "rel-brainclaw-postgresql",
            "raw_extraction_confidence": 0.0,
            "interpretive_confidence": 0.72,
            "promotion_status": "promoted",
        },
    ]

    entities, relationships = _graph_records_from_candidates(candidates)

    assert {entity.id for entity in entities} == {"entity-brainclaw", "entity-postgresql"}
    assert len(relationships) == 1
    assert relationships[0].source_entity_id == "entity-brainclaw"
    assert relationships[0].target_entity_id == "entity-postgresql"
    assert relationships[0].relationship_type == "uses"


def test_graph_records_from_promoted_candidates_respects_artifact_scoped_entity_identity():
    from openclaw_memory.integration.lossless_sync import _graph_records_from_candidates

    candidates = [
        {
            "candidate_type": "EntityCandidate",
            "source_artifact_id": "artifact-a",
            "content": "BrainClaw",
            "structured_payload": {
                "entity_type": "system",
                "canonical_name": "brainclaw",
                "extracted_entity_id": "artifact-a-brainclaw",
            },
            "promoted_memory_item_id": "entity-a-brainclaw",
            "promotion_status": "promoted",
        },
        {
            "candidate_type": "EntityCandidate",
            "source_artifact_id": "artifact-b",
            "content": "BrainClaw",
            "structured_payload": {
                "entity_type": "system",
                "canonical_name": "brainclaw",
                "extracted_entity_id": "artifact-b-brainclaw",
            },
            "promoted_memory_item_id": "entity-b-brainclaw",
            "promotion_status": "promoted",
        },
        {
            "candidate_type": "EntityCandidate",
            "source_artifact_id": "artifact-b",
            "content": "Lossless-Claw",
            "structured_payload": {
                "entity_type": "system",
                "canonical_name": "lossless-claw",
                "extracted_entity_id": "artifact-b-lossless",
            },
            "promoted_memory_item_id": "entity-b-lossless",
            "promotion_status": "promoted",
        },
        {
            "candidate_type": "RelationshipCandidate",
            "source_artifact_id": "artifact-b",
            "content": "BrainClaw collaborates_with Lossless-Claw",
            "structured_payload": {
                "relationship_type": "collaborates_with",
                "source_entity_id": "artifact-b-brainclaw",
                "target_entity_id": "artifact-b-lossless",
                "source_entity_name": "BrainClaw",
                "target_entity_name": "Lossless-Claw",
                "source_entity_canonical_name": "brainclaw",
                "target_entity_canonical_name": "lossless-claw",
            },
            "promoted_memory_item_id": "rel-b",
            "promotion_status": "promoted",
        },
    ]

    _entities, relationships = _graph_records_from_candidates(candidates)

    assert len(relationships) == 1
    assert relationships[0].source_entity_id == "entity-b-brainclaw"
    assert relationships[0].target_entity_id == "entity-b-lossless"


def test_rebuild_marks_backfill_targets_from_canonical_records(tmp_path, monkeypatch):
    from openclaw_memory.integration import lossless_sync

    engine, repo = _build_engine(tmp_path)
    engine.sync(mode="bootstrap")

    captured: dict[str, int] = {}

    def fake_rebuild(entities, relationships):
        captured["entity_count"] = len(entities)
        captured["relationship_count"] = len(relationships)
        return {
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "synced_count": len(entities) + len(relationships),
        }

    monkeypatch.setattr(lossless_sync, "_rebuild_neo4j_from_candidates", fake_rebuild)

    result = engine.rebuild("neo4j")

    assert result["status"] == "completed"
    assert result["target"] == "neo4j"
    assert result["memory_item_count"] == len(repo.memory_items)
    assert result["entity_count"] == captured["entity_count"]
    assert result["relationship_count"] == captured["relationship_count"]
    assert result["synced_count"] == captured["entity_count"] + captured["relationship_count"]
    assert repo.rebuild_checkpoints["neo4j"]["status"] == "completed"
    assert (
        repo.rebuild_checkpoints["neo4j"]["last_validated_target_state"]["relationship_count"]
        == captured["relationship_count"]
    )
    assert sum(
        1 for state in repo.derived_backfill_state.values() if state["target"] == "neo4j"
    ) == len(repo.memory_items)


def test_rebuild_neo4j_from_candidates_replaces_entity_graph_in_batched_writes(monkeypatch):
    from openclaw_memory.integration import lossless_sync
    from openclaw_memory.pipeline.extraction import Entity, Relationship

    calls: list[tuple[str, dict[str, object]]] = []
    captured_database: dict[str, str | None] = {"name": None}

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, params=None):
            calls.append((query, params or {}))

    class FakeDriver:
        def session(self, *, database=None):
            captured_database["name"] = database
            return FakeSession()

        def close(self):
            return None

    fake_driver = FakeDriver()
    fake_neo4j = types.ModuleType("neo4j")
    fake_neo4j.GraphDatabase = types.SimpleNamespace(driver=lambda url, auth: fake_driver)
    monkeypatch.setitem(sys.modules, "neo4j", fake_neo4j)
    monkeypatch.setenv("NEO4J_DATABASE", "brainclaw-test")

    result = lossless_sync._rebuild_neo4j_from_candidates(
        [
            Entity(id="entity-1", entity_type="system", name="BrainClaw", canonical_name="brainclaw", confidence=0.9),
            Entity(
                id="entity-2",
                entity_type="system",
                name="Lossless-Claw",
                canonical_name="lossless-claw",
                confidence=0.88,
            ),
        ],
        [
            Relationship(
                id="rel-1",
                source_entity_id="entity-1",
                target_entity_id="entity-2",
                relationship_type="integrates_with",
                confidence=0.72,
                evidence="BrainClaw integrates with Lossless-Claw",
            )
        ],
    )

    assert captured_database["name"] == "brainclaw-test"
    assert len(calls) == 3
    assert "MATCH (n:Entity)" in calls[0][0]
    assert "DETACH DELETE n" in calls[0][0]
    assert "UNWIND $entities AS entity" in calls[1][0]
    assert calls[1][1]["entities"][0]["id"] == "entity-1"
    assert "UNWIND $relationships AS relationship" in calls[2][0]
    assert calls[2][1]["relationships"][0]["id"] == "rel-1"
    assert result == {"entity_count": 2, "relationship_count": 1, "synced_count": 3}
