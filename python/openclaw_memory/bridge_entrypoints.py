"""Bridge-compatible entry points for BrainClaw Python backend.

The TypeScript bridge calls Python functions as:
    from openclaw_memory.<module> import <function>
    result = <function>(**json.loads(sys.argv[1]))

All functions here are:
  - Synchronous (bridge uses subprocess, not asyncio)
  - Self-contained (build own DB clients from env vars)
  - Gracefully degrading (return error dict, not crash)
"""
import os
import asyncio
import json
import logging
import uuid
import datetime
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Namespace UUID for deterministic agent UUIDs (must match migrate_memory_md.py)
# ---------------------------------------------------------------------------
BRAINCLAW_NS = uuid.UUID("b4a1bc1a-0000-4000-a000-b4a1bc1ab000")


def _postgres_url() -> Optional[str]:
    return os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL") or os.getenv("DATABASE_URL")


def _parse_postgres_url(url: str) -> dict:
    """Parse PostgreSQL URL into connection parameters.
    
    Args:
        url: PostgreSQL connection URL (postgresql://user:pass@host:port/db)
        
    Returns:
        Dictionary with host, port, database, user, password
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
        "user": parsed.username or "openclaw",
        "password": parsed.password or "",
    }


def _run_async(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _stringify_uuid(value):
    return str(value) if value is not None else None


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "items"):
        return dict(row.items())
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def _coerce_json_container(value, *, default):
    if value is None:
        return default.copy() if isinstance(default, (dict, list)) else default

    parsed = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default.copy() if isinstance(default, (dict, list)) else default
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return default.copy() if isinstance(default, (dict, list)) else default

    if isinstance(default, dict):
        return dict(parsed) if isinstance(parsed, dict) else {}
    if isinstance(default, list):
        return list(parsed) if isinstance(parsed, list) else []
    return parsed


def _format_memory_record(row: dict) -> dict:
    """Normalize a Postgres row into the bridge memory record shape."""
    row = _row_to_dict(row)
    metadata = _coerce_json_container(row.get("metadata"), default={})
    metadata.setdefault("memory_class", row.get("memory_class"))
    metadata.setdefault("memory_type", row.get("memory_type"))
    metadata.setdefault("status", row.get("status"))
    metadata.setdefault("visibility_scope", row.get("visibility_scope"))
    metadata.setdefault("confidence", row.get("confidence"))
    metadata.setdefault("agent_id", _stringify_uuid(row.get("agent_id")))
    metadata.setdefault("tenant_id", _stringify_uuid(row.get("tenant_id")))

    provenance = {
        "source_message_id": _stringify_uuid(row.get("source_message_id")),
        "source_session_id": _stringify_uuid(row.get("source_session_id")),
        "source_tool_call_id": _stringify_uuid(row.get("source_tool_call_id")),
        "extracted_by": row.get("extracted_by"),
        "extractor_name": row.get("extractor_name"),
        "extractor_version": row.get("extractor_version"),
        "extraction_timestamp": row.get("extraction_timestamp").isoformat()
        if row.get("extraction_timestamp")
        else None,
        "extraction_confidence": row.get("extraction_confidence"),
        "extraction_metadata": _coerce_json_container(row.get("extraction_metadata"), default={}),
        "superseded_by": _stringify_uuid(row.get("superseded_by")),
        "supersession_reason": row.get("supersession_reason"),
    }

    return {
        "id": _stringify_uuid(row.get("id")),
        "content": row.get("content", ""),
        "metadata": metadata,
        "provenance": provenance,
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


def _coerce_identity_uuid(value: Optional[object]) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value

    text = str(value).strip()
    if not text:
        return None

    try:
        return uuid.UUID(text)
    except ValueError:
        return uuid.uuid5(BRAINCLAW_NS, text)


def _safe_uuid(value: Optional[object]) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _db_uuid_text(value: Optional[object]) -> Optional[str]:
    parsed = _safe_uuid(value)
    return str(parsed) if parsed else None


def _parse_alternatives(content: str) -> list[str]:
    import re

    match = re.search(r"alternatives?\s+considered\s*:\s*(.+?)(?:\.\s|$)", content, re.IGNORECASE)
    if not match:
        return []
    candidates = re.split(r",|;|\n| or ", match.group(1))
    return [candidate.strip(" .") for candidate in candidates if candidate.strip(" .")]


def _extract_workflow_steps(content: str) -> list[dict]:
    import re

    numbered = re.findall(r"(?:^|\s)(\d+)\.\s*(.*?)(?=(?:\s+\d+\.\s)|$)", content, re.DOTALL)
    if numbered:
        return [
            {"step": int(number), "description": description.strip()}
            for number, description in numbered
            if description.strip()
        ]

    steps = []
    for index, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("- ", "* ")):
            steps.append({"step": len(steps) + 1, "description": line[2:].strip()})
        elif line.lower().startswith("step "):
            cleaned = re.sub(r"^step\s+\d+\s*[:.-]?\s*", "", line, flags=re.IGNORECASE)
            if cleaned:
                steps.append({"step": len(steps) + 1, "description": cleaned})
    return steps


def infer_memory_semantics(
    content: str,
    event_type: str = "message",
    role: str = "",
    metadata: Optional[dict] = None,
) -> dict:
    metadata = dict(metadata or {})
    content = (content or "").strip()
    content_lower = content.lower()

    explicit_class = str(metadata.get("memory_class") or "").strip().lower()
    explicit_type = str(metadata.get("memory_type") or "").strip().lower()

    decision_phrases = (
        "we decided",
        "decided to",
        "let's go with",
        "agreed on",
        "agreed to",
        "the decision was",
        "we will use",
        "we'll use",
        "chose to",
        "selected",
    )
    procedure_markers = (
        "procedure:",
        "runbook:",
        "playbook:",
        "steps:",
        "workflow:",
        "how to",
    )
    success_markers = ("worked", "successful", "successfully", "resolved", "fixed")

    memory_class = "semantic"
    memory_type = explicit_type or "fact"
    confidence = float(metadata.get("confidence") or 0.78)
    structured_metadata: dict = {}

    if explicit_class and explicit_class not in {"general", "unknown"}:
        memory_class = explicit_class
        if not explicit_type:
            memory_type = {
                "decision": "technical",
                "procedural": "procedure",
                "identity": "preference",
                "relational": "project",
                "episodic": event_type or "event",
                "summary": "session",
            }.get(memory_class, "fact")
    elif any(phrase in content_lower for phrase in decision_phrases):
        memory_class = "decision"
        memory_type = explicit_type or "technical"
    elif any(marker in content_lower for marker in procedure_markers) or _extract_workflow_steps(content):
        memory_class = "procedural"
        memory_type = explicit_type or "procedure"
    elif event_type == "tool_call":
        memory_class = "episodic"
        memory_type = explicit_type or "tool_run"
    elif role == "system":
        memory_class = "identity"
        memory_type = explicit_type or "guardrail"

    if memory_class == "decision":
        import re

        rationale_match = re.search(r"because\s+(.+?)(?:\.\s|$)", content, re.IGNORECASE)
        structured_metadata.update(
            {
                "decision_summary": content.splitlines()[0].strip(),
                "rationale": rationale_match.group(1).strip() if rationale_match else "",
                "alternatives": _parse_alternatives(content),
                "decision_status": str(metadata.get("decision_status") or "accepted"),
                "supporting_evidence": metadata.get("supporting_evidence") or [],
            }
        )
        confidence = max(confidence, 0.9)

    if memory_class == "procedural":
        workflow_steps = _extract_workflow_steps(content)
        success = bool(metadata.get("success")) or any(marker in content_lower for marker in success_markers)
        failure = bool(metadata.get("failure")) or "failed" in content_lower
        structured_metadata.update(
            {
                "workflow_steps": workflow_steps,
                "success_count": 1 if success else 0,
                "failure_count": 1 if failure and not success else 0,
                "last_successful_execution": datetime.datetime.utcnow().isoformat() if success else None,
            }
        )
        confidence = max(confidence, 0.88 if success else 0.74)

    if memory_class == "identity":
        confidence = max(confidence, 0.82)

    return {
        "memory_class": memory_class,
        "memory_type": memory_type,
        "status": structured_metadata.get("decision_status", "active"),
        "confidence": min(confidence, 1.0),
        "metadata": structured_metadata,
    }


def detect_pairwise_contradictions(memories: list[dict]) -> list[dict]:
    from openclaw_memory.memory.write_policy import WritePolicy
    import re

    policy = WritePolicy()
    contradictions = []
    ignore_tokens = {
        "brainclaw",
        "openclaw",
        "running",
        "memory",
        "system",
        "plugin",
        "using",
        "current",
        "active",
    }

    for left_index in range(len(memories)):
        left = memories[left_index]
        left_content = (left.get("content") or "").strip()
        if not left_content:
            continue
        left_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", left_content.lower())
            if len(token) > 3 and token not in ignore_tokens
        }

        for right_index in range(left_index + 1, len(memories)):
            right = memories[right_index]
            right_content = (right.get("content") or "").strip()
            if not right_content:
                continue
            right_tokens = {
                token
                for token in re.findall(r"[a-z0-9]+", right_content.lower())
                if len(token) > 3 and token not in ignore_tokens
            }
            if not (left_tokens & right_tokens):
                continue

            reason = policy.detect_contradiction(left_content, [right_content]) or policy.detect_contradiction(
                right_content,
                [left_content],
            )
            if not reason:
                continue

            contradictions.append(
                {
                    "memory_ids": [str(left.get("id")), str(right.get("id"))],
                    "reason": reason,
                    "contents": [left_content, right_content],
                }
            )

    return contradictions


def summarize_audit_health(
    audit_rows: int,
    memory_event_rows: int,
    retrieval_rows: int,
    provenance_gap_count: int,
) -> dict:
    status = "HEALTHY" if provenance_gap_count == 0 else "DEGRADED"
    return {
        "status": status,
        "tables": {
            "audit_log": audit_rows,
            "memory_events": memory_event_rows,
            "retrieval_logs": retrieval_rows,
        },
        "provenance_gap_count": provenance_gap_count,
    }


def _json_safe(value):
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _safe_repository_state_snapshot(repository):
    checkpoint_state = None
    integration_state = None
    backfill_required_state = {"pending": 0, "failed": 0, "completed": 0}
    rebuild_status: dict = {}
    errors: list[str] = []

    try:
        checkpoint_state = repository.get_checkpoint()
    except Exception as exc:  # pragma: no cover - defensive in live runtime
        errors.append(str(exc))
    try:
        integration_state = repository.get_integration_state()
    except Exception as exc:  # pragma: no cover - defensive in live runtime
        errors.append(str(exc))
    try:
        backfill_required_state = repository.summarize_backfill_state()
    except Exception as exc:  # pragma: no cover - defensive in live runtime
        errors.append(str(exc))
    try:
        rebuild_status = repository.get_rebuild_status()
    except Exception as exc:  # pragma: no cover - defensive in live runtime
        errors.append(str(exc))

    repository_error = "; ".join(errors) if errors else None
    return (
        _json_safe(checkpoint_state),
        _json_safe(integration_state),
        _json_safe(backfill_required_state),
        _json_safe(rebuild_status),
        repository_error,
    )


def lcm_status(runtime: Optional[dict] = None, plugin_config: Optional[dict] = None, **kwargs) -> dict:
    from openclaw_memory.integration.lossless_adapter import (
        LosslessClawAdapter,
        OpenClawRuntimeSnapshot,
    )
    from openclaw_memory.integration.lossless_sync import build_postgres_repository_from_env

    adapter = LosslessClawAdapter(
        runtime=OpenClawRuntimeSnapshot.from_dict(runtime),
        db_path=(plugin_config or {}).get("losslessClawDbPath") or (plugin_config or {}).get("dbPath"),
        plugin_config=plugin_config or {},
    )
    report = adapter.detect().to_dict()
    repository = build_postgres_repository_from_env()
    checkpoint_state = None
    integration_state = None
    backfill_required_state = {"pending": 0, "failed": 0, "completed": 0}
    rebuild_status = {}
    repository_error = None

    if repository is not None:
        try:
            repository.upsert_integration_state(report)
        except Exception as exc:  # pragma: no cover - defensive in live runtime
            repository_error = str(exc)
            repository = None
        if repository is not None:
            (
                checkpoint_state,
                integration_state,
                backfill_required_state,
                rebuild_status,
                snapshot_error,
            ) = _safe_repository_state_snapshot(repository)
            repository_error = snapshot_error

    response = {
        **report,
        "integration_state": integration_state,
        "checkpoint_state": checkpoint_state,
        "degraded_state_details": {
            "reason_code": (integration_state or {}).get("reason_code") or report.get("reason_code"),
            "last_degraded_reason_code": (integration_state or {}).get("last_degraded_reason_code"),
            "last_degraded_transition_at": (integration_state or {}).get("last_degraded_transition_at"),
            "last_successful_supported_profile": (integration_state or {}).get("last_successful_supported_profile")
            or report.get("supported_profile"),
        },
        "replay_status": {
            "status": (checkpoint_state or {}).get("status"),
            "retry_count": (checkpoint_state or {}).get("retry_count"),
            "replay_marker": (checkpoint_state or {}).get("replay_marker"),
        },
        "backfill_required_state": backfill_required_state,
        "rebuild_status": rebuild_status,
    }
    if repository_error:
        response["repository_error"] = repository_error
    return response


def lcm_sync(
    runtime: Optional[dict] = None,
    plugin_config: Optional[dict] = None,
    mode: str = "incremental",
    **kwargs,
) -> dict:
    from openclaw_memory.integration.lossless_adapter import (
        LosslessClawAdapter,
        OpenClawRuntimeSnapshot,
    )
    from openclaw_memory.integration.lossless_sync import (
        LosslessClawSyncEngine,
        build_postgres_repository_from_env,
    )

    adapter = LosslessClawAdapter(
        runtime=OpenClawRuntimeSnapshot.from_dict(runtime),
        db_path=(plugin_config or {}).get("losslessClawDbPath") or (plugin_config or {}).get("dbPath"),
        plugin_config=plugin_config or {},
    )
    status = adapter.detect().to_dict()
    repository = build_postgres_repository_from_env()

    if repository is None:
        if status["compatibility_state"] != "installed_compatible":
            return {
                "status": "skipped",
                "mode": mode,
                "compatibility_state": status["compatibility_state"],
                "reason_code": status.get("reason_code"),
                "checkpoint_state": None,
                "replay_status": {"status": None, "retry_count": None, "replay_marker": None},
                "backfill_required_state": {"pending": 0, "failed": 0, "completed": 0},
                "degraded_state_details": {
                    "reason_code": status.get("reason_code"),
                    "last_degraded_reason_code": None,
                    "last_degraded_transition_at": None,
                    "last_successful_supported_profile": status.get("supported_profile"),
                },
                "rebuild_status": {},
            }
        return {
            "status": "failed",
            "mode": mode,
            "compatibility_state": status["compatibility_state"],
            "reason_code": status.get("reason_code"),
            "error": "Canonical PostgreSQL repository unavailable",
            "checkpoint_state": None,
            "replay_status": {"status": None, "retry_count": None, "replay_marker": None},
            "backfill_required_state": {"pending": 0, "failed": 0, "completed": 0},
            "degraded_state_details": {
                "reason_code": status.get("reason_code"),
                "last_degraded_reason_code": None,
                "last_degraded_transition_at": None,
                "last_successful_supported_profile": status.get("supported_profile"),
            },
            "rebuild_status": {},
        }

    checkpoint_state = None
    integration_state = None
    backfill_required_state = {"pending": 0, "failed": 0, "completed": 0}
    rebuild_status = {}
    repository_error = None
    try:
        engine = LosslessClawSyncEngine(adapter=adapter, repository=repository)
        result = engine.sync(mode=mode)
    except Exception as exc:
        result = {
            "status": "failed",
            "mode": mode,
            "compatibility_state": status["compatibility_state"],
            "reason_code": status.get("reason_code"),
            "error": "Canonical sync failure",
        }
        repository_error = str(exc)

    (
        checkpoint_state,
        integration_state,
        backfill_required_state,
        rebuild_status,
        snapshot_error,
    ) = _safe_repository_state_snapshot(repository)
    if snapshot_error:
        repository_error = "; ".join(
            [part for part in [repository_error, snapshot_error] if part]
        )

    response = {
        **result,
        "integration_state": integration_state,
        "checkpoint_state": checkpoint_state,
        "degraded_state_details": {
            "reason_code": (integration_state or {}).get("reason_code") or result.get("reason_code"),
            "last_degraded_reason_code": (integration_state or {}).get("last_degraded_reason_code"),
            "last_degraded_transition_at": (integration_state or {}).get("last_degraded_transition_at"),
            "last_successful_supported_profile": (integration_state or {}).get("last_successful_supported_profile")
            or status.get("supported_profile"),
        },
        "replay_status": {
            "status": (checkpoint_state or {}).get("status"),
            "retry_count": (checkpoint_state or {}).get("retry_count"),
            "replay_marker": (checkpoint_state or {}).get("replay_marker"),
        },
        "backfill_required_state": backfill_required_state,
        "rebuild_status": rebuild_status,
    }
    if repository_error:
        response["repository_error"] = repository_error
    return response


def lcm_rebuild(target: str = "", **kwargs) -> dict:
    from openclaw_memory.integration.lossless_sync import (
        LosslessClawSyncEngine,
        build_postgres_repository_from_env,
    )

    repository = build_postgres_repository_from_env()
    if repository is None:
        return {
            "status": "failed",
            "target": str(target or "").strip().lower(),
            "error": "Canonical PostgreSQL repository unavailable",
            "rebuild_checkpoint": None,
            "backfill_required_state": {"pending": 0, "failed": 0, "completed": 0},
        }

    repository_error = None
    try:
        engine = LosslessClawSyncEngine(adapter=None, repository=repository)
        result = engine.rebuild(target)
    except Exception as exc:
        result = {
            "status": "failed",
            "target": str(target or "").strip().lower(),
            "error": "Canonical rebuild failure",
        }
        repository_error = str(exc)

    (
        _checkpoint_state,
        _integration_state,
        backfill_required_state,
        rebuild_status,
        snapshot_error,
    ) = _safe_repository_state_snapshot(repository)
    if snapshot_error:
        repository_error = "; ".join(
            [part for part in [repository_error, snapshot_error] if part]
        )
    normalized_target = str(target or "").strip().lower()
    response = {
        **result,
        "rebuild_checkpoint": rebuild_status.get(normalized_target),
        "backfill_required_state": backfill_required_state,
    }
    if repository_error:
        response["repository_error"] = repository_error
    return response


def _detect_control_ui_status() -> str:
    configured_url = os.getenv("BRAINCLAW_CONTROL_UI_URL")
    urls = [configured_url] if configured_url else []
    urls.extend(
        [
            "http://127.0.0.1:3000/__openclaw__/control/",
            "http://127.0.0.1:18789/__openclaw__/control/",
        ]
    )
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return "healthy" if response.status == 200 else f"http_{response.status}"
        except Exception:
            continue
    return "unknown"


def sync_operational_memory_files(
    runtime: Optional[dict] = None,
    plugin_config: Optional[dict] = None,
    sync_date: Optional[str] = None,
    **kwargs,
) -> dict:
    from openclaw_memory.graph.health import get_health_stats
    from openclaw_memory.integration.lossless_adapter import (
        LosslessClawAdapter,
        OpenClawRuntimeSnapshot,
    )
    from openclaw_memory.integration.operational_memory_sync import (
        DEFAULT_PRIMARY_AGENT_ID,
        sync_operational_memory_files as sync_files,
    )

    plugin_config = plugin_config or {}
    runtime_snapshot = OpenClawRuntimeSnapshot.from_dict(runtime)
    adapter = LosslessClawAdapter(
        runtime=runtime_snapshot,
        db_path=plugin_config.get("losslessClawDbPath") or plugin_config.get("dbPath"),
        plugin_config=plugin_config,
    )
    status = adapter.detect().to_dict()
    graph_health = get_health_stats()

    tool_names = [
        tool_name
        for tool_name, available in (status.get("tool_availability") or {}).items()
        if available
    ]
    snapshot = {
        "openclaw_version": runtime_snapshot.openclaw_version or status.get("openclaw_version"),
        "memory_slot": runtime_snapshot.memory_slot,
        "context_engine_slot": runtime_snapshot.context_engine_slot,
        "plugin_version": status.get("plugin_version") or runtime_snapshot.plugin_version,
        "compatibility_state": status.get("compatibility_state", "unknown"),
        "supported_profile": status.get("supported_profile"),
        "tool_names": tool_names,
        "node_count": graph_health.get("node_count"),
        "edge_count": graph_health.get("edge_count"),
        "control_ui_status": _detect_control_ui_status(),
    }

    state_dir = Path(os.getenv("OPENCLAW_STATE_DIR", "/home/node/.openclaw"))
    config_path = Path(os.getenv("OPENCLAW_CONFIG_PATH", state_dir / "openclaw.json"))

    result = sync_files(
        snapshot=snapshot,
        state_dir=state_dir,
        config_path=config_path,
        sync_date=sync_date or datetime.date.today().isoformat(),
        primary_agent_id=plugin_config.get("operationalMemoryPrimaryAgentId", DEFAULT_PRIMARY_AGENT_ID),
        root_memory_path=plugin_config.get("operationalMemoryRootPath"),
    )
    result.update(
        {
            "status": "completed",
            "compatibility_state": snapshot["compatibility_state"],
            "control_ui_status": snapshot["control_ui_status"],
        }
    )
    return result


def _record_memory_event(cur, *, memory_item_id: uuid.UUID, event_type: str, agent_db_id: Optional[str], tenant_db_id: Optional[str], details: Optional[dict] = None) -> None:
    from psycopg2.extras import Json

    cur.execute(
        """
        INSERT INTO memory_events (
            memory_item_id,
            event_type,
            actor_agent_id,
            actor_tenant_id,
            details
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            str(memory_item_id),
            event_type,
            agent_db_id,
            tenant_db_id,
            Json(details or {}),
        ),
    )


def _record_retrieval_log(cur, *, agent_db_id: Optional[str], tenant_db_id: Optional[str], session_id: Optional[str], query_text: str, intent: str, query_plan: dict, results: list[dict]) -> None:
    from psycopg2.extras import Json

    evidence = [
        {
            "id": str(result.get("id") or ""),
            "memory_class": (result.get("metadata") or {}).get("memory_class"),
            "source": result.get("source") or "postgres",
        }
        for result in results
    ]
    cur.execute(
        """
        INSERT INTO retrieval_logs (
            tenant_id,
            agent_id,
            session_id,
            intent,
            query_text,
            query_plan,
            result_count,
            evidence
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            tenant_db_id,
            agent_db_id,
            session_id,
            intent,
            query_text,
            Json(query_plan),
            len(results),
            Json(evidence),
        ),
    )


def _record_audit_event(
    cur,
    *,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    before_state: Optional[dict] = None,
    after_state: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> None:
    from psycopg2.extras import Json

    cur.execute(
        """
        INSERT INTO audit_log (
            actor_id,
            action,
            resource_type,
            resource_id,
            before_state,
            after_state,
            correlation_id,
            metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor_id,
            action,
            resource_type,
            resource_id,
            Json(before_state) if before_state is not None else None,
            Json(after_state) if after_state is not None else None,
            str(uuid.uuid4()),
            Json(metadata or {}),
        ),
    )


# ---------------------------------------------------------------------------
# Async client factories (using actual API: connect/disconnect)
# ---------------------------------------------------------------------------

async def _pg_connect():
    from openclaw_memory.storage.postgres import PostgresClient
    url = _postgres_url()
    if not url:
        raise RuntimeError("POSTGRES_URL not set")
    # Parse URL into connection parameters
    params = _parse_postgres_url(url)
    client = PostgresClient(**params)
    await client.connect()
    return client


async def _neo4j_connect():
    try:
        from openclaw_memory.storage.neo4j_client import Neo4jClient
        client = Neo4jClient(
            uri=os.getenv("NEO4J_URL", "bolt://neo4j-proxy:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", ""),
            database=os.getenv("NEO4J_DATABASE", "neo4j"),
        )
        await client.connect()
        return client
    except Exception as e:
        logger.warning("Neo4j connect failed: %s", e)
        return None


def _weaviate_connect():
    try:
        import weaviate
        url = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
        host = url.replace("http://", "").replace("https://", "").split(":")[0]
        port = int(url.rsplit(":", 1)[-1]) if ":" in url.split("//", 1)[-1] else 8080
        client = weaviate.connect_to_custom(
            http_host=host, http_port=port,
            http_secure=url.startswith("https"),
            grpc_host=host, grpc_port=50051, grpc_secure=False,
        )
        return client
    except Exception as e:
        logger.warning("Weaviate connect failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# ingest_event — bridge entry point
# ---------------------------------------------------------------------------

def ingest_event(event: dict = None, **kwargs) -> dict:
    """Ingest a memory event using MEMORY.md-first backup, then BrainClaw upsert."""
    if event is None:
        event = kwargs

    try:
        import psycopg2
        import psycopg2.extras
        from openclaw_memory.integration.memory_backup import append_memory_backup
        from openclaw_memory.security.access_control import get_current_agent_id, get_current_tenant_id

        content = (event.get("content") or "").strip()
        if not content:
            return {"error": "content is required", "status": "failed"}

        metadata = dict(event.get("metadata") or {})
        event_type = str(metadata.get("event_type") or event.get("event_type") or "message")
        role = str(metadata.get("role") or event.get("role") or "assistant")

        current_agent_id = get_current_agent_id()
        current_tenant_id = get_current_tenant_id()
        agent_id = current_agent_id or event.get("agent_id") or "system"
        tenant_id = current_tenant_id or event.get("tenant_id") or "default"
        agent_uuid = _coerce_identity_uuid(agent_id)
        tenant_uuid = _coerce_identity_uuid(tenant_id)
        agent_db_id = str(agent_uuid) if agent_uuid else None
        tenant_db_id = str(tenant_uuid) if tenant_uuid else None

        if event.get("memory_class") and "memory_class" not in metadata:
            metadata["memory_class"] = event.get("memory_class")
        if event.get("memory_type") and "memory_type" not in metadata:
            metadata["memory_type"] = event.get("memory_type")

        inferred = infer_memory_semantics(
            content=content,
            event_type=event_type,
            role=role,
            metadata=metadata,
        )
        user_confirmed = bool(
            metadata.get("user_confirmed")
            or metadata.get("remember_this")
            or metadata.get("memory_class") not in {None, "", "general", "unknown"}
        )
        should_promote = (
            (inferred["memory_class"] != "episodic" and user_confirmed)
            or inferred["memory_class"] in {"decision", "procedural", "identity"}
        )
        now = datetime.datetime.utcnow()
        raw_id = uuid.uuid4()
        promoted_id = uuid.uuid4() if should_promote else None

        promoted_metadata = {
            **metadata,
            **inferred["metadata"],
            "memory_class": inferred["memory_class"],
            "memory_type": inferred["memory_type"],
            "backup_mode": "memory-md-first",
            "raw_memory_id": str(raw_id),
        }

        backup_path = None
        if promoted_id:
            backup_path = append_memory_backup(
                agent_id=str(agent_id),
                memory_record={
                    "id": str(promoted_id),
                    "content": content,
                    "metadata": promoted_metadata,
                    "provenance": {
                        "source_session_id": metadata.get("session_id"),
                        "source_message_id": metadata.get("message_id"),
                        "extraction_timestamp": now.isoformat(),
                    },
                    "created_at": now.isoformat(),
                },
            )
            promoted_metadata["backup_path"] = backup_path

        conn = psycopg2.connect(_postgres_url())
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO memory_items (
                            id, tenant_id, agent_id, memory_class, memory_type, status,
                            content, source_message_id, source_session_id,
                            extracted_by, extraction_method, extraction_timestamp,
                            extractor_name, extractor_version, extraction_confidence,
                            extraction_metadata, confidence, user_confirmed,
                            valid_from, is_current, visibility_scope, access_control,
                            retention_policy, metadata, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s
                        )
                        """,
                        (
                            str(raw_id),
                            tenant_db_id,
                            agent_db_id,
                            "episodic",
                            event_type,
                            "raw",
                            content,
                            _db_uuid_text(metadata.get("message_id")),
                            _db_uuid_text(metadata.get("session_id")),
                            "brainclaw",
                            "memory_md_backup",
                            now,
                            "brainclaw",
                            "1.3.0",
                            1.0,
                            psycopg2.extras.Json({"role": role, **metadata}),
                            1.0,
                            True,
                            now,
                            False,
                            metadata.get("visibility_scope") or "agent",
                            psycopg2.extras.Json(metadata.get("access_control") or {}),
                            "default",
                            psycopg2.extras.Json({"raw_event": True, **metadata}),
                            now,
                            now,
                        ),
                    )
                    _record_memory_event(
                        cur,
                        memory_item_id=raw_id,
                        event_type="created_raw",
                        agent_db_id=agent_db_id,
                        tenant_db_id=tenant_db_id,
                        details={"event_type": event_type, "role": role},
                    )
                    _record_audit_event(
                        cur,
                        actor_id=str(agent_id),
                        action="CREATE",
                        resource_type="memory_item",
                        resource_id=str(raw_id),
                        after_state={"memory_class": "episodic", "status": "raw"},
                        metadata={"phase": "backup-first-raw"},
                    )

                    if promoted_id:
                        cur.execute(
                            """
                            INSERT INTO memory_items (
                                id, tenant_id, agent_id, memory_class, memory_type, status,
                                content, source_message_id, source_session_id,
                                extracted_by, extraction_method, extraction_timestamp,
                                extractor_name, extractor_version, extraction_confidence,
                                extraction_metadata, confidence, user_confirmed,
                                valid_from, is_current, visibility_scope, access_control,
                                retention_policy, metadata, created_at, updated_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s,
                                %s, %s, %s,
                                %s, %s, %s,
                                %s, %s, %s,
                                %s, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s, %s
                            )
                            ON CONFLICT (id) DO UPDATE SET
                                content = EXCLUDED.content,
                                status = EXCLUDED.status,
                                confidence = EXCLUDED.confidence,
                                user_confirmed = EXCLUDED.user_confirmed,
                                extraction_timestamp = EXCLUDED.extraction_timestamp,
                                extraction_metadata = EXCLUDED.extraction_metadata,
                                metadata = EXCLUDED.metadata,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (
                                str(promoted_id),
                                tenant_db_id,
                                agent_db_id,
                                inferred["memory_class"],
                                inferred["memory_type"],
                                inferred["status"],
                                content,
                                _db_uuid_text(metadata.get("message_id")),
                                _db_uuid_text(metadata.get("session_id")),
                                "brainclaw",
                                "heuristic_upsert",
                                now,
                                "brainclaw",
                                "1.3.0",
                                inferred["confidence"],
                                psycopg2.extras.Json(inferred["metadata"]),
                                inferred["confidence"],
                                user_confirmed,
                                now,
                                True,
                                metadata.get("visibility_scope") or "agent",
                                psycopg2.extras.Json(metadata.get("access_control") or {}),
                                "default",
                                psycopg2.extras.Json(promoted_metadata),
                                now,
                                now,
                            ),
                        )
                        _record_memory_event(
                            cur,
                            memory_item_id=promoted_id,
                            event_type="promoted",
                            agent_db_id=agent_db_id,
                            tenant_db_id=tenant_db_id,
                            details={"memory_class": inferred["memory_class"], "backup_path": backup_path},
                        )
                        _record_audit_event(
                            cur,
                            actor_id=str(agent_id),
                            action="PROMOTE",
                            resource_type="memory_item",
                            resource_id=str(promoted_id),
                            before_state={"memory_class": "episodic", "status": "raw"},
                            after_state={
                                "memory_class": inferred["memory_class"],
                                "memory_type": inferred["memory_type"],
                                "status": inferred["status"],
                            },
                            metadata={"backup_path": backup_path, "raw_memory_id": str(raw_id)},
                        )

            # Determine searchable status:
            # - For PROMOTED items: queued for async indexing to Weaviate (not immediately searchable)
            # - For CAPTURED_RAW: only stored in PostgreSQL, searchable via fallback only
            # The actual Weaviate sync happens asynchronously via sync_memory_item in the pipeline
            is_promoted = bool(promoted_id)
            return {
                "id": str(promoted_id or raw_id),
                "raw_id": str(raw_id),
                "promoted_id": str(promoted_id) if promoted_id else None,
                "status": "PROMOTED" if is_promoted else "CAPTURED_RAW",
                "memory_class": inferred["memory_class"] if is_promoted else "episodic",
                "memory_type": inferred["memory_type"] if is_promoted else event_type,
                "backup_path": backup_path,
                "promoted_count": 1 if is_promoted else 0,
                "method": "memory_md_first_upsert",
                # Searchable fields - content is NOT immediately searchable after ingestion
                # because async sync to Weaviate happens separately via the pipeline
                "searchable": False,
                # Estimate in milliseconds for when content will become searchable in Weaviate
                # This accounts for async pipeline processing time
                "searchableAfterMs": 5000 if is_promoted else None,
            }
        finally:
            conn.close()
    except Exception as error:
        logger.error("Canonical ingest failed: %s", error)
        return {"error": str(error), "status": "failed"}


# ---------------------------------------------------------------------------
# retrieve_sync — bridge entry point
# ---------------------------------------------------------------------------

def retrieve_sync(query: str = "", intent: str = "general", agent_id: str = "system",
                  tenant_id: str = "default", top_k: int = 8, limit: int = 0, **kwargs) -> dict:
    """Retrieve memories. Falls back to PG text search on full pipeline error."""
    top_k = limit or top_k  # handle both param names from different callers

    # Try full async pipeline
    try:
        async def _run():
            # Initialize storage clients
            pg = await _pg_connect()
            wv = _weaviate_connect()
            neo = await _neo4j_connect()

            try:
                # Create ResultFusion instance and set clients directly
                from openclaw_memory.retrieval.fusion import ResultFusion
                fusion = ResultFusion()
                fusion._postgres = pg
                fusion._weaviate = wv
                fusion._neo4j = neo
                
                # Try Weaviate vector/hybrid search first
                if wv:
                    try:
                        wv_results = await fusion.query_weaviate(
                            query=query,
                            limit=top_k,
                            tenant_id=tenant_id,
                        )
                        if wv_results:
                            return wv_results
                    except Exception as e:
                        logger.warning("Weaviate search failed, falling back to PostgreSQL: %s", e)
                
                # Fallback to PostgreSQL text search using pool directly
                import uuid
                BRAINCLAW_NS = uuid.UUID("b4a1bc1a-0000-4000-a000-b4a1bc1ab000")
                agent_uuid = str(uuid.uuid5(BRAINCLAW_NS, agent_id)) if agent_id else None
                
                # Build the query - simple text search on content
                sql = """
                    SELECT DISTINCT ON (agent_id, content)
                           id, content, visibility_scope, agent_id,
                           created_at, metadata
                    FROM memory_items
                    WHERE content ILIKE $1
                    ORDER BY agent_id, content, created_at DESC
                    LIMIT $2
                """
                
                async with pg._pool.acquire() as conn:
                    rows = await conn.fetch(sql, f"%{query}%", top_k)
                    return [_row_to_dict(row) for row in rows] if rows else []
            finally:
                await pg.disconnect()
                if neo:
                    try:
                        await neo.disconnect()
                    except Exception:
                        pass
                if wv:
                    try:
                        wv.close()
                    except Exception:
                        pass

        results = _run_async(_run())
        lst = results if isinstance(results, list) else list(results)
        # Format results for response
        formatted = []
        for r in lst:
            metadata = _coerce_json_container(r.get("metadata"), default={})
            formatted.append({
                "id": str(r.get("id", "")),
                "content": r.get("content", ""),
                "source": r.get("source", "postgres"),
                "relevance": r.get("confidence", 0.5),
                "metadata": metadata,
            })
        try:
            import psycopg2

            from openclaw_memory.security.access_control import (
                get_current_agent_db_id,
                get_current_tenant_db_id,
            )

            conn = psycopg2.connect(_postgres_url())
            try:
                with conn:
                    with conn.cursor() as cur:
                        _record_retrieval_log(
                            cur,
                            agent_db_id=get_current_agent_db_id(),
                            tenant_db_id=get_current_tenant_db_id(),
                            session_id=str(_safe_uuid(kwargs.get("session_id"))) if _safe_uuid(kwargs.get("session_id")) else None,
                            query_text=query,
                            intent=intent,
                            query_plan={"mode": "retrieve_sync", "top_k": top_k},
                            results=formatted,
                        )
            finally:
                conn.close()
        except Exception as log_error:
            logger.warning("Failed to record retrieval log: %s", log_error)
        return {"results": formatted, "total": len(formatted)}

    except Exception as e:
        logger.warning("Full retrieval failed (%s) — using PG text search", e)

    # Fallback: PG text search (actual columns)
    try:
        import psycopg2
        import psycopg2.extras
        from openclaw_memory.security.access_control import (
            get_current_agent_db_id,
            get_current_tenant_db_id,
        )

        agent_uuid = str(uuid.uuid5(BRAINCLAW_NS, agent_id))
        conn = psycopg2.connect(_postgres_url())
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT DISTINCT ON (agent_id, content)
                      id, content, metadata, created_at
               FROM memory_items
               WHERE agent_id = %s AND content ILIKE %s
               ORDER BY agent_id, content, created_at DESC LIMIT %s""",
            (agent_uuid, f"%{query}%", top_k),
        )
        rows = [dict(r) for r in cur.fetchall()]
        _record_retrieval_log(
            cur,
            agent_db_id=get_current_agent_db_id(),
            tenant_db_id=get_current_tenant_db_id(),
            session_id=str(_safe_uuid(kwargs.get("session_id"))) if _safe_uuid(kwargs.get("session_id")) else None,
            query_text=query,
            intent=intent,
            query_plan={"mode": "pg_text_search", "top_k": top_k},
            results=rows,
        )
        conn.commit()
        conn.close()
        return {"results": rows, "total": len(rows), "method": "pg_text_search"}
    except Exception as e2:
        logger.error("PG text search also failed: %s", e2)
        return {"results": [], "total": 0, "error": str(e2)}


def get_memory(memory_id: str = "", **kwargs) -> dict:
    """Get a single memory record by id with provenance and metadata."""
    if not memory_id:
        return {"error": "memory_id is required"}

    try:
        memory_uuid = uuid.UUID(memory_id)
    except ValueError:
        return {"error": f"Invalid memory_id: {memory_id}"}

    try:
        async def _run():
            pg = await _pg_connect()
            try:
                from openclaw_memory.security.access_control import set_db_session_context

                sql = """
                    SELECT id, tenant_id, agent_id, memory_class, memory_type, status,
                           content, metadata, source_message_id, source_session_id,
                           source_tool_call_id, extracted_by, extraction_method,
                           extraction_timestamp, extractor_name, extractor_version,
                           extraction_confidence, extraction_metadata, confidence,
                           visibility_scope, superseded_by, supersession_reason,
                           created_at, updated_at
                    FROM memory_items
                    WHERE id = $1
                    LIMIT 1
                """
                async with pg._pool.acquire() as conn:
                    await set_db_session_context(conn)
                    row = await conn.fetchrow(sql, memory_uuid)
                    return _format_memory_record(_row_to_dict(row)) if row else None
            finally:
                await pg.disconnect()

        record = _run_async(_run())
        if record:
            try:
                import psycopg2

                from openclaw_memory.security.access_control import get_current_agent_id

                conn = psycopg2.connect(_postgres_url())
                try:
                    with conn:
                        with conn.cursor() as cur:
                            _record_audit_event(
                                cur,
                                actor_id=str(get_current_agent_id() or "system"),
                                action="READ",
                                resource_type="memory_item",
                                resource_id=memory_id,
                                after_state={"path": f"brainclaw://memory/{memory_id}"},
                                metadata={"via": "get_memory"},
                            )
                finally:
                    conn.close()
            except Exception as log_error:
                logger.warning("Failed to record memory read audit event: %s", log_error)
            return record
        return {"error": f"Memory record not found: {memory_id}"}
    except Exception as e:
        logger.warning("Async get_memory failed (%s) — using PG fallback", e)

    try:
        import psycopg2
        import psycopg2.extras
        from openclaw_memory.security.access_control import (
            get_current_agent_id,
            get_current_agent_db_id,
            get_current_tenant_db_id,
        )

        conn = psycopg2.connect(_postgres_url())
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT id, tenant_id, agent_id, memory_class, memory_type, status,
                   content, metadata, source_message_id, source_session_id,
                   source_tool_call_id, extracted_by, extraction_method,
                   extraction_timestamp, extractor_name, extractor_version,
                   extraction_confidence, extraction_metadata, confidence,
                   visibility_scope, superseded_by, supersession_reason,
                   created_at, updated_at
            FROM memory_items
            WHERE id = %s
              AND (
                agent_id::text = %s
                OR visibility_scope IN ('tenant', 'public')
                OR (%s IS NOT NULL AND tenant_id::text = %s AND visibility_scope = 'team')
              )
            LIMIT 1
            """,
            (
                str(memory_uuid),
                get_current_agent_db_id(),
                get_current_tenant_db_id(),
                get_current_tenant_db_id(),
            ),
        )
        row = cur.fetchone()
        if row:
            _record_audit_event(
                cur,
                actor_id=str(get_current_agent_id() or "system"),
                action="READ",
                resource_type="memory_item",
                resource_id=memory_id,
                after_state={"path": f"brainclaw://memory/{memory_id}"},
                metadata={"via": "get_memory"},
            )
            conn.commit()
        conn.close()
        if not row:
            return {"error": f"Memory record not found: {memory_id}"}
        return _format_memory_record(dict(row))
    except Exception as e2:
        logger.error("PG get_memory fallback also failed: %s", e2)
        return {"error": str(e2)}


# ---------------------------------------------------------------------------
# check_contradictions / verify_audit_integrity — bridge entry points
# ---------------------------------------------------------------------------

def check_contradictions(
    entity_name: str = "",
    tenant_id: str = "",
    limit: int = 50,
    **kwargs,
) -> dict:
    try:
        import psycopg2
        import psycopg2.extras
        from openclaw_memory.security.access_control import (
            get_current_agent_db_id,
            get_current_tenant_db_id,
        )

        search_term = entity_name.strip()
        conn = psycopg2.connect(_postgres_url())
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        params = [get_current_agent_db_id(), get_current_tenant_db_id(), get_current_tenant_db_id()]
        query = """
            SELECT id, content, metadata, memory_class, memory_type
            FROM memory_items
            WHERE is_current = TRUE
              AND (
                agent_id::text = %s
                OR visibility_scope IN ('tenant', 'public')
                OR (%s IS NOT NULL AND tenant_id::text = %s AND visibility_scope = 'team')
              )
        """
        if search_term:
            query += " AND content ILIKE %s"
            params.append(f"%{search_term}%")
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        cur.execute(query, params)
        rows = [dict(row) for row in cur.fetchall()]
        contradictions = detect_pairwise_contradictions(rows)
        _record_retrieval_log(
            cur,
            agent_db_id=get_current_agent_db_id(),
            tenant_db_id=get_current_tenant_db_id(),
            session_id=None,
            query_text=search_term or "contradiction scan",
            intent="contradiction_check",
            query_plan={"mode": "pairwise_contradiction_scan", "limit": limit},
            results=rows,
        )
        conn.commit()
        conn.close()
        return {
            "status": "CONTRADICTIONS_FOUND" if contradictions else "NO_CONTRADICTIONS_FOUND",
            "checked_entities": [search_term] if search_term else ["global"],
            "checked_count": len(rows),
            "evidence_count": len(rows),
            "contradictions": contradictions,
        }
    except Exception as error:
        logger.error("Contradiction scan failed: %s", error)
        return {
            "status": "ERROR",
            "checked_entities": [entity_name] if entity_name else ["global"],
            "checked_count": 0,
            "evidence_count": 0,
            "contradictions": [],
            "error": str(error),
        }


def verify_audit_integrity(**kwargs) -> dict:
    try:
        import psycopg2

        conn = psycopg2.connect(_postgres_url())
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM audit_log")
                    audit_rows = int(cur.fetchone()[0])
                    cur.execute("SELECT COUNT(*) FROM memory_events")
                    memory_event_rows = int(cur.fetchone()[0])
                    cur.execute("SELECT COUNT(*) FROM retrieval_logs")
                    retrieval_rows = int(cur.fetchone()[0])
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM memory_items
                        WHERE extractor_name IS NULL
                           OR confidence IS NULL
                           OR visibility_scope IS NULL
                           OR status IS NULL
                        """
                    )
                    provenance_gap_count = int(cur.fetchone()[0])
        finally:
            conn.close()

        return summarize_audit_health(
            audit_rows=audit_rows,
            memory_event_rows=memory_event_rows,
            retrieval_rows=retrieval_rows,
            provenance_gap_count=provenance_gap_count,
        )
    except Exception as error:
        logger.error("Audit integrity verification failed: %s", error)
        return {
            "status": "ERROR",
            "tables": {
                "audit_log": 0,
                "memory_events": 0,
                "retrieval_logs": 0,
            },
            "provenance_gap_count": 0,
            "error": str(error),
        }


# ---------------------------------------------------------------------------
# classify — bridge entry point (no DB needed, already sync)
# ---------------------------------------------------------------------------

def classify(query: str = "", **kwargs) -> dict:
    """Synchronous intent classification."""
    try:
        from openclaw_memory.retrieval.intent import classify as _classify
        result = _classify(query=query)
        if hasattr(result, "primary_intent"):
            intent = result.primary_intent
            return {
                "intent": intent.value if hasattr(intent, "value") else str(intent),
                "confidence": getattr(result, "confidence", 0.0),
            }
        return {"intent": str(result), "confidence": 0.0}
    except Exception as e:
        return {"intent": "general", "confidence": 0.0, "error": str(e)}
