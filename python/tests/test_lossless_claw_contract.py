"""Contract tests for BrainClaw's Lossless-Claw integration surfaces."""

from pathlib import Path
import sqlite3


def test_lossless_claw_integration_migration_exists_with_required_tables_and_columns():
    migrations_dir = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "storage"
        / "migrations"
    )
    migration = migrations_dir / "004_lossless_claw_integration.sql"

    assert migration.exists(), "Lossless-Claw integration migration is missing"

    sql = " ".join(migration.read_text(encoding="utf-8").split())
    required_fragments = [
        "CREATE TABLE IF NOT EXISTS source_artifacts",
        "artifact_hash TEXT NOT NULL",
        "source_plugin TEXT NOT NULL",
        "source_artifact_type TEXT NOT NULL",
        "source_artifact_id TEXT NOT NULL",
        "compatibility_state TEXT NOT NULL",
        "reason_code TEXT",
        "workspace_id UUID",
        "agent_id UUID",
        "session_id UUID",
        "project_id UUID",
        "user_id UUID",
        "visibility_scope TEXT NOT NULL DEFAULT 'owner'",
        "statefulness TEXT NOT NULL DEFAULT 'stateful'",
        "CREATE TABLE IF NOT EXISTS memory_candidates",
        "candidate_type TEXT NOT NULL",
        "raw_extraction_confidence DOUBLE PRECISION",
        "interpretive_confidence DOUBLE PRECISION",
        "topic_hint_match_score DOUBLE PRECISION",
        "interpretation_flag TEXT",
        "blocked_reason_code TEXT",
        "CREATE TABLE IF NOT EXISTS source_sync_checkpoints",
        "CREATE TABLE IF NOT EXISTS integration_states",
        "last_successful_gate_evaluated_at TIMESTAMP WITH TIME ZONE",
        "last_degraded_reason_code TEXT",
        "CREATE TABLE IF NOT EXISTS promotion_overrides",
        "justification TEXT NOT NULL",
        "CREATE TABLE IF NOT EXISTS dead_letter_artifacts",
        "retry_count INTEGER NOT NULL DEFAULT 0",
        "CREATE TABLE IF NOT EXISTS rebuild_checkpoints",
        "CREATE TABLE IF NOT EXISTS derived_backfill_state",
    ]

    for fragment in required_fragments:
        assert fragment in sql, f"Missing Lossless-Claw integration fragment: {fragment}"


def test_lossless_adapter_contract_exposes_required_states_thresholds_and_reason_codes():
    from openclaw_memory.integration.lossless_adapter import (
        CompatibilityState,
        PromotionThresholds,
        ReasonCode,
    )

    assert {state.value for state in CompatibilityState} == {
        "not_installed",
        "installed_compatible",
        "installed_degraded",
        "installed_incompatible",
        "installed_unreachable",
    }
    assert PromotionThresholds.RAW_AUTO_PROMOTE == 0.85
    assert PromotionThresholds.INTERPRETIVE == 0.70
    assert PromotionThresholds.TOPIC_HINT_MATCH == 0.60
    assert {
        ReasonCode.SCHEMA_FINGERPRINT_UNKNOWN.value,
        ReasonCode.SCOPE_AMBIGUOUS.value,
        ReasonCode.STATELESS_SESSION.value,
        ReasonCode.TOOL_UNAVAILABLE.value,
        ReasonCode.ACL_DENIED.value,
        ReasonCode.LOW_CONFIDENCE.value,
        ReasonCode.CONTRADICTED.value,
        ReasonCode.SOURCE_UNREACHABLE.value,
    } == {
        "SCHEMA_FINGERPRINT_UNKNOWN",
        "SCOPE_AMBIGUOUS",
        "STATELESS_SESSION",
        "TOOL_UNAVAILABLE",
        "ACL_DENIED",
        "LOW_CONFIDENCE",
        "CONTRADICTED",
        "SOURCE_UNREACHABLE",
    }


def test_lossless_adapter_detects_supported_schema_and_session_policy(tmp_path):
    from openclaw_memory.integration.lossless_adapter import (
        CompatibilityState,
        LosslessClawAdapter,
        OpenClawRuntimeSnapshot,
    )

    db_path = tmp_path / "lcm.db"
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
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
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
        conn.commit()
    finally:
        conn.close()

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

    report = adapter.detect()

    assert report.compatibility_state is CompatibilityState.INSTALLED_COMPATIBLE
    assert report.db_path == str(db_path)
    assert report.supported_profile is not None
    assert report.tool_availability["lcm_expand_query"] is True
    assert adapter.classify_session_statefulness("tmp-session-1").import_allowed is False
    assert adapter.classify_session_statefulness("stateless-session-1").promotable is False

