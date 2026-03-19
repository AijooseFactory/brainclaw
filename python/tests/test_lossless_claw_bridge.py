"""Bridge entry point tests for Lossless-Claw integration."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _seed_minimal_lcm_db(db_path: Path) -> None:
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
            INSERT INTO conversations (conversation_id, session_id)
            VALUES (1, 'stateful-session-bridge');
            INSERT INTO messages (message_id, conversation_id, seq, role, content, token_count, created_at)
            VALUES (10, 1, 1, 'assistant', 'We decided to use PostgreSQL for BrainClaw.', 12, '2026-03-18T10:01:00Z');
            INSERT INTO summaries (
              summary_id, conversation_id, kind, depth, content, token_count,
              earliest_at, latest_at, descendant_count, created_at, file_ids
            ) VALUES (
              'sum-bridge', 1, 'conversation', 0,
              'We decided to use PostgreSQL for BrainClaw.',
              20, '2026-03-18T10:00:00Z', '2026-03-18T10:01:00Z', 0, '2026-03-18T10:01:00Z', '[]'
            );
            INSERT INTO summary_messages (summary_id, message_id, ordinal)
            VALUES ('sum-bridge', 10, 0);
            INSERT INTO message_parts (part_id, message_id, session_id, part_type, ordinal)
            VALUES ('part-bridge', 10, 'stateful-session-bridge', 'text', 0);
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_lcm_sync_bridge_uses_sync_engine_when_canonical_repository_is_available(tmp_path, monkeypatch):
    from openclaw_memory.bridge_entrypoints import lcm_sync
    from openclaw_memory.integration.lossless_sync import InMemoryLosslessRepository

    db_path = tmp_path / "lossless.db"
    _seed_minimal_lcm_db(db_path)
    repo = InMemoryLosslessRepository(source_id="lossless-claw", source_type="context_engine")

    monkeypatch.setattr(
        "openclaw_memory.integration.lossless_sync.build_postgres_repository_from_env",
        lambda *args, **kwargs: repo,
    )

    result = lcm_sync(
        runtime={
            "openclaw_version": "2026.3.14",
            "memory_slot": "brainclaw",
            "context_engine_slot": "lossless-claw",
            "plugin_enabled": True,
            "plugin_installed": True,
            "plugin_version": "0.4.0",
            "plugin_install_path": str(tmp_path),
            "tool_names": ["lcm_grep", "lcm_describe", "lcm_expand_query"],
        },
        plugin_config={"dbPath": str(db_path)},
        mode="bootstrap",
    )

    assert result["status"] == "completed"
    assert result["source_artifact_count"] == 1
    assert result["promoted_count"] >= 1
    assert repo.integration_state["compatibility_state"] == "installed_compatible"


def test_lcm_rebuild_bridge_uses_canonical_repository_when_available(monkeypatch):
    from openclaw_memory.bridge_entrypoints import lcm_rebuild
    from openclaw_memory.integration.lossless_sync import InMemoryLosslessRepository

    repo = InMemoryLosslessRepository(source_id="lossless-claw", source_type="context_engine")
    repo.seed_memory_item(
        content="Canonical memory",
        memory_class="semantic",
        memory_type="fact",
        source_session_id="seed-session",
    )
    monkeypatch.setattr(
        "openclaw_memory.integration.lossless_sync.build_postgres_repository_from_env",
        lambda *args, **kwargs: repo,
    )
    monkeypatch.setattr(
        "openclaw_memory.integration.lossless_sync._rebuild_neo4j_from_candidates",
        lambda entities, relationships: {
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "synced_count": len(entities) + len(relationships),
        },
    )

    result = lcm_rebuild(target="neo4j")

    assert result["status"] == "completed"
    assert result["target"] == "neo4j"
    assert repo.rebuild_checkpoints["neo4j"]["status"] == "completed"
