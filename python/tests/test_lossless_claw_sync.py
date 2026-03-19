"""Behavior tests for BrainClaw's Lossless-Claw sync engine."""

from __future__ import annotations

import sqlite3
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
            openclaw_version="2026.3.13",
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


def test_rebuild_marks_backfill_targets_from_canonical_records(tmp_path):
    engine, repo = _build_engine(tmp_path)
    engine.sync(mode="bootstrap")

    result = engine.rebuild("neo4j")

    assert result["status"] == "completed"
    assert result["target"] == "neo4j"
    assert result["memory_item_count"] == len(repo.memory_items)
    assert repo.rebuild_checkpoints["neo4j"]["status"] == "completed"
    assert sum(
        1 for state in repo.derived_backfill_state.values() if state["target"] == "neo4j"
    ) == len(repo.memory_items)
