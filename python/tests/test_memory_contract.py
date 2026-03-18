"""Contract tests for BrainClaw's canonical memory ledger."""

from pathlib import Path
import re


def test_canonical_ledger_migration_exists_with_required_tables_and_columns():
    migrations_dir = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "storage"
        / "migrations"
    )
    migration = migrations_dir / "002_canonical_memory_ledger.sql"

    assert migration.exists(), "Canonical ledger migration is missing"

    sql = migration.read_text(encoding="utf-8")
    normalized_sql = " ".join(sql.split())

    required_fragments = [
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS tenant_id UUID",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS memory_class TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS memory_type TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS status TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS source_message_id UUID",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS source_session_id UUID",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS extraction_timestamp TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS extractor_name TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS extractor_version TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS user_confirmed BOOLEAN",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS valid_from TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS is_current BOOLEAN",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS superseded_by UUID",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS supersession_reason TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS access_control JSONB",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS retention_policy TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS weaviate_id TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS neo4j_id TEXT",
        "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS sync_version INTEGER",
        "CREATE TABLE IF NOT EXISTS memory_events",
        "CREATE TABLE IF NOT EXISTS retrieval_logs",
    ]

    for fragment in required_fragments:
        normalized_fragment = " ".join(fragment.split())
        assert normalized_fragment in normalized_sql, f"Missing canonical ledger fragment: {fragment}"


def test_decision_recall_uses_memory_items_not_nonexistent_decisions_table():
    policy_path = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "retrieval"
        / "policy.py"
    )
    policy = policy_path.read_text(encoding="utf-8")
    match = re.search(
        r"Intent\.DECISION_RECALL: RetrievalPlan\((?P<body>.*?)Intent\.",
        policy,
        re.DOTALL,
    )

    assert match, "Could not locate DECISION_RECALL retrieval plan"

    body = match.group("body")
    assert '"table": "memory_items"' in body
    assert '"memory_class": "decision"' in body
    assert '"is_current": True' in body


def test_supersede_memory_item_copies_agent_id_into_replacement_row():
    postgres_path = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "storage"
        / "postgres.py"
    )
    source = postgres_path.read_text(encoding="utf-8")
    match = re.search(
        r"async def supersede_memory_item\(.*?INSERT INTO memory_items \((?P<columns>.*?)\)\s*SELECT",
        source,
        re.DOTALL,
    )

    assert match, "Could not locate supersede INSERT statement"

    columns = {
        column.strip()
        for column in match.group("columns").replace("\n", " ").split(",")
        if column.strip()
    }

    assert "agent_id" in columns, "Superseding insert drops agent ownership"


def test_postgres_client_exposes_query_and_agent_memory_lookup_contracts():
    postgres_path = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "storage"
        / "postgres.py"
    )
    source = postgres_path.read_text(encoding="utf-8")

    assert "async def query(" in source
    assert "async def get_agent_memories(" in source


def test_result_fusion_uses_visibility_scope_column_for_memory_queries():
    fusion_path = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "retrieval"
        / "fusion.py"
    )
    source = fusion_path.read_text(encoding="utf-8")
    match = re.search(
        r"async def query_postgres\(.*?sql = \"\"\"(?P<sql>.*?)\"\"\"",
        source,
        re.DOTALL,
    )

    assert match, "Could not locate ResultFusion.query_postgres SQL"
    sql = " ".join(match.group("sql").split())
    assert "visibility_scope" in sql
    assert " visibility," not in sql


def test_memory_md_migration_uses_deterministic_ids_to_prevent_restart_duplicates():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "storage"
        / "migrations"
        / "migrate_memory_md.py"
    )
    source = migration_path.read_text(encoding="utf-8")
    body = source.split("def read_items_from_md", 1)[1].split("def pg_connection", 1)[0]

    assert "uuid.uuid5" in body
    assert "agent_uuid" in body
    assert "text" in body


def test_bridge_retrieval_queries_collapse_duplicate_memory_md_rows():
    bridge_path = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "bridge_entrypoints.py"
    )
    source = bridge_path.read_text(encoding="utf-8")

    assert "SELECT DISTINCT ON (agent_id, content)" in source


def test_advanced_audit_migration_exists():
    migrations_dir = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "storage"
        / "migrations"
    )
    migration = migrations_dir / "003_advanced_audit_and_semantics.sql"

    assert migration.exists(), "Advanced audit migration is missing"

    sql = " ".join(migration.read_text(encoding="utf-8").split())
    assert "CREATE TABLE IF NOT EXISTS audit_log" in sql


def test_infer_memory_semantics_extracts_decision_fields():
    from openclaw_memory.bridge_entrypoints import infer_memory_semantics

    payload = infer_memory_semantics(
        content=(
            "We decided to use PostgreSQL for BrainClaw because it is the canonical "
            "source of truth. Alternatives considered: SQLite, Neo4j-only."
        ),
        event_type="message",
        role="assistant",
        metadata={},
    )

    assert payload["memory_class"] == "decision"
    assert payload["memory_type"] == "technical"
    assert payload["metadata"]["decision_summary"].startswith("We decided to use PostgreSQL")
    assert payload["metadata"]["rationale"] == "it is the canonical source of truth"
    assert payload["metadata"]["alternatives"] == ["SQLite", "Neo4j-only"]


def test_infer_memory_semantics_extracts_procedural_fields():
    from openclaw_memory.bridge_entrypoints import infer_memory_semantics

    payload = infer_memory_semantics(
        content=(
            "Procedure: 1. Restart the container. 2. Run migrations. 3. Confirm the logs "
            "show healthy. This worked successfully."
        ),
        event_type="message",
        role="assistant",
        metadata={"success": True},
    )

    assert payload["memory_class"] == "procedural"
    assert payload["memory_type"] == "procedure"
    assert payload["metadata"]["success_count"] == 1
    assert len(payload["metadata"]["workflow_steps"]) == 3
    assert payload["metadata"]["workflow_steps"][0]["description"] == "Restart the container."


def test_detect_pairwise_contradictions_finds_conflicting_claims():
    from openclaw_memory.bridge_entrypoints import detect_pairwise_contradictions

    contradictions = detect_pairwise_contradictions(
        [
            {"id": "mem-1", "content": "PostgreSQL is running for BrainClaw."},
            {"id": "mem-2", "content": "PostgreSQL is not running for BrainClaw."},
            {"id": "mem-3", "content": "Neo4j is running for BrainClaw."},
        ]
    )

    assert len(contradictions) == 1
    assert contradictions[0]["memory_ids"] == ["mem-1", "mem-2"]
    assert contradictions[0]["reason"]


def test_summarize_audit_health_flags_missing_provenance():
    from openclaw_memory.bridge_entrypoints import summarize_audit_health

    summary = summarize_audit_health(
        audit_rows=4,
        memory_event_rows=2,
        retrieval_rows=3,
        provenance_gap_count=1,
    )

    assert summary["status"] == "DEGRADED"
    assert summary["tables"]["audit_log"] == 4
    assert summary["provenance_gap_count"] == 1


def test_memory_backup_appends_promoted_memory_to_agent_specific_memory_md_once(tmp_path):
    from openclaw_memory.integration.memory_backup import append_memory_backup

    state_dir = tmp_path / "state"
    agent_dir = state_dir / "agents" / "lore" / "agent"
    agent_dir.mkdir(parents=True)

    config_path = state_dir / "openclaw.json"
    config_path.write_text(
        """
        {
          "agents": {
            "list": [
              {
                "id": "lore",
                "agentDir": "%s"
              }
            ]
          }
        }
        """
        % agent_dir.as_posix(),
        encoding="utf-8",
    )

    memory_record = {
        "id": "mem-123",
        "content": "We decided to use PostgreSQL as the canonical ledger.",
        "metadata": {
            "memory_class": "decision",
            "decision_summary": "Use PostgreSQL as canonical ledger",
            "rationale": "rebuildability and provenance",
        },
        "provenance": {"source_session_id": "sess-1"},
    }

    first_path = append_memory_backup(
        agent_id="lore",
        memory_record=memory_record,
        state_dir=state_dir,
        config_path=config_path,
    )
    second_path = append_memory_backup(
        agent_id="lore",
        memory_record=memory_record,
        state_dir=state_dir,
        config_path=config_path,
    )

    assert first_path == second_path
    text = (agent_dir / "MEMORY.md").read_text(encoding="utf-8")
    assert "Use PostgreSQL as canonical ledger" in text
    assert text.count("brainclaw:id=mem-123") == 1


def test_ingest_event_stringifies_source_ids_before_psycopg_insert():
    bridge_path = (
        Path(__file__).resolve().parents[1]
        / "openclaw_memory"
        / "bridge_entrypoints.py"
    )
    source = bridge_path.read_text(encoding="utf-8")

    assert '_db_uuid_text(metadata.get("message_id"))' in source
    assert '_db_uuid_text(metadata.get("session_id"))' in source


def test_row_to_dict_handles_asyncpg_record_like_rows():
    from openclaw_memory.bridge_entrypoints import _row_to_dict

    class FakeAsyncpgRecord:
        def __init__(self, mapping):
            self._mapping = mapping

        def keys(self):
            return self._mapping.keys()

        def __getitem__(self, key):
            return self._mapping[key]

        def __iter__(self):
            return iter(self._mapping.values())

    row = FakeAsyncpgRecord(
        {
            "id": "mem-123",
            "content": "PostgreSQL is the canonical ledger.",
            "metadata": {"memory_class": "decision"},
        }
    )

    normalized = _row_to_dict(row)

    assert normalized["id"] == "mem-123"
    assert normalized["content"] == "PostgreSQL is the canonical ledger."
    assert normalized["metadata"]["memory_class"] == "decision"


def test_format_memory_record_accepts_json_string_fields():
    from openclaw_memory.bridge_entrypoints import _format_memory_record

    record = _format_memory_record(
        {
            "id": "mem-123",
            "content": "We decided to use PostgreSQL.",
            "metadata": '{"memory_class":"decision","memory_type":"technical"}',
            "source_message_id": None,
            "source_session_id": None,
            "source_tool_call_id": None,
            "extracted_by": "brainclaw",
            "extractor_name": "brainclaw",
            "extractor_version": "1.3.0",
            "extraction_timestamp": None,
            "extraction_confidence": 0.9,
            "extraction_metadata": '{"decision_status":"accepted"}',
            "memory_class": "decision",
            "memory_type": "technical",
            "status": "accepted",
            "visibility_scope": "agent",
            "confidence": 0.9,
            "agent_id": None,
            "tenant_id": None,
            "superseded_by": None,
            "supersession_reason": None,
            "created_at": None,
            "updated_at": None,
        }
    )

    assert record["metadata"]["memory_class"] == "decision"
    assert record["metadata"]["memory_type"] == "technical"
    assert record["provenance"]["extraction_metadata"]["decision_status"] == "accepted"


def test_ingest_event_writes_memory_md_before_postgres_upsert(monkeypatch):
    import sys
    import types

    from openclaw_memory import bridge_entrypoints
    from openclaw_memory.integration import memory_backup
    from openclaw_memory.security import access_control

    call_order = []

    def fake_append_memory_backup(*, agent_id, memory_record, state_dir=None, config_path=None):
        call_order.append(("backup", agent_id, memory_record["id"]))
        return "/tmp/lore/MEMORY.md"

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            call_order.append(("execute", sql.splitlines()[0].strip()))

    class FakeConnection:
        def __enter__(self):
            call_order.append(("conn_enter", None, None))
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def close(self):
            call_order.append(("close", None, None))

    fake_extras = types.SimpleNamespace(Json=lambda value: value)
    fake_psycopg2 = types.SimpleNamespace(
        connect=lambda _: call_order.append(("connect", None, None)) or FakeConnection(),
        extras=fake_extras,
    )

    monkeypatch.setattr(memory_backup, "append_memory_backup", fake_append_memory_backup)
    monkeypatch.setattr(access_control, "get_current_agent_id", lambda: "lore")
    monkeypatch.setattr(access_control, "get_current_tenant_id", lambda: "factory")
    monkeypatch.setattr(bridge_entrypoints, "_postgres_url", lambda: "postgresql://brainclaw-test")
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake_extras)

    result = bridge_entrypoints.ingest_event(
        {
            "content": "We decided to use PostgreSQL because it is rebuildable.",
            "metadata": {"user_confirmed": True},
        }
    )

    assert result["status"] == "PROMOTED"
    assert result["method"] == "memory_md_first_upsert"
    assert result["backup_path"] == "/tmp/lore/MEMORY.md"
    assert call_order[0][0] == "backup"
    assert call_order[1][0] == "connect"


def test_ingest_event_persists_decision_and_procedural_semantics(monkeypatch):
    import sys
    import types

    from openclaw_memory import bridge_entrypoints
    from openclaw_memory.integration import memory_backup
    from openclaw_memory.security import access_control

    promoted_rows = []

    def fake_append_memory_backup(*, agent_id, memory_record, state_dir=None, config_path=None):
        return f"/tmp/{agent_id}/MEMORY.md"

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            if "ON CONFLICT (id) DO UPDATE SET" in sql:
                promoted_rows.append(params)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    fake_extras = types.SimpleNamespace(Json=lambda value: value)
    fake_psycopg2 = types.SimpleNamespace(connect=lambda _: FakeConnection(), extras=fake_extras)

    monkeypatch.setattr(memory_backup, "append_memory_backup", fake_append_memory_backup)
    monkeypatch.setattr(access_control, "get_current_agent_id", lambda: "lore")
    monkeypatch.setattr(access_control, "get_current_tenant_id", lambda: "factory")
    monkeypatch.setattr(bridge_entrypoints, "_postgres_url", lambda: "postgresql://brainclaw-test")
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake_extras)

    bridge_entrypoints.ingest_event(
        {
            "content": (
                "We decided to use PostgreSQL for BrainClaw because it is rebuildable. "
                "Alternatives considered: SQLite, Neo4j-only."
            ),
            "metadata": {"user_confirmed": True},
        }
    )
    bridge_entrypoints.ingest_event(
        {
            "content": (
                "Procedure: 1. Restart the container. 2. Run migrations. 3. Confirm the logs "
                "show healthy. This worked successfully."
            ),
            "metadata": {"success": True},
        }
    )

    assert len(promoted_rows) == 2

    decision_row, procedural_row = promoted_rows

    assert decision_row[3] == "decision"
    assert decision_row[4] == "technical"
    assert decision_row[15]["alternatives"] == ["SQLite", "Neo4j-only"]
    assert decision_row[23]["decision_summary"].startswith("We decided to use PostgreSQL")
    assert decision_row[23]["backup_mode"] == "memory-md-first"
    assert decision_row[23]["backup_path"] == "/tmp/lore/MEMORY.md"

    assert procedural_row[3] == "procedural"
    assert procedural_row[4] == "procedure"
    assert procedural_row[15]["success_count"] == 1
    assert len(procedural_row[15]["workflow_steps"]) == 3
    assert procedural_row[15]["workflow_steps"][0]["description"] == "Restart the container."
    assert procedural_row[23]["backup_mode"] == "memory-md-first"
