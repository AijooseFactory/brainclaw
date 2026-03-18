#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-${1:-}}"
BRAINCLAW_AGENT_ID="${BRAINCLAW_AGENT_ID:-${2:-lore}}"
BRAINCLAW_TENANT_ID="${BRAINCLAW_TENANT_ID:-${3:-default}}"
BRAINCLAW_ACCEPTANCE_MARKER="${BRAINCLAW_ACCEPTANCE_MARKER:-brainclaw-acceptance-$(date +%s)}"

if [[ -z "${OPENCLAW_CONTAINER}" ]]; then
  echo "Usage: OPENCLAW_CONTAINER=<container> bash scripts/e2e_hybrid_contract.sh [agent_id] [tenant_id]" >&2
  exit 2
fi

echo "== BrainClaw plugin status =="
docker exec "${OPENCLAW_CONTAINER}" sh -lc 'openclaw plugins info brainclaw'

echo
echo "== BrainClaw live hybrid contract =="
docker exec -i \
  -e BRAINCLAW_AGENT_ID="${BRAINCLAW_AGENT_ID}" \
  -e BRAINCLAW_TENANT_ID="${BRAINCLAW_TENANT_ID}" \
  -e BRAINCLAW_ACCEPTANCE_MARKER="${BRAINCLAW_ACCEPTANCE_MARKER}" \
  "${OPENCLAW_CONTAINER}" \
  python3 - <<'PY'
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path


def load_brainclaw_backend() -> None:
    candidates = [
        Path("/home/node/.openclaw/extensions/brainclaw/python"),
        Path("/root/.openclaw/extensions/brainclaw/python"),
        Path("/home/node/.openclaw/extensions/brainclaw"),
        Path("/root/.openclaw/extensions/brainclaw"),
    ]
    for candidate in candidates:
        if (candidate / "openclaw_memory").exists():
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError("Could not locate installed BrainClaw Python backend in the container")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


load_brainclaw_backend()

from openclaw_memory.bridge_entrypoints import (
    check_contradictions,
    get_memory,
    ingest_event,
    retrieve_sync,
    verify_audit_integrity,
)
from openclaw_memory.security.access_control import verify_identity_token


agent_id = os.environ["BRAINCLAW_AGENT_ID"]
tenant_id = os.environ["BRAINCLAW_TENANT_ID"]
marker = os.environ["BRAINCLAW_ACCEPTANCE_MARKER"]
secret = os.environ.get("BRAINCLAW_SECRET")

assert_true(bool(secret), "BRAINCLAW_SECRET must be present in the container environment")

timestamp = int(time.time() * 1000)
payload = {
    "agentId": agent_id,
    "agentName": agent_id,
    "tenantId": tenant_id,
    "timestamp": timestamp,
}
message = f"{agent_id}:{agent_id}::{tenant_id}:{timestamp}"
payload["signature"] = hmac.new(
    secret.encode("utf-8"),
    message.encode("utf-8"),
    hashlib.sha256,
).hexdigest()
token = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
verify_identity_token(token, secret)

decision = ingest_event(
    event={
        "content": (
            f"[{marker}] We decided to use PostgreSQL for BrainClaw because it is rebuildable. "
            "Alternatives considered: SQLite, Neo4j-only."
        ),
        "metadata": {"user_confirmed": True, "visibility_scope": "agent"},
    }
)
procedure = ingest_event(
    event={
        "content": (
            f"[{marker}] Procedure: 1. Restart the container. 2. Run migrations. "
            "3. Confirm the logs show healthy. This worked successfully."
        ),
        "metadata": {"success": True, "visibility_scope": "agent"},
    }
)
contradiction_seed = ingest_event(
    event={
        "content": f"[{marker}] PostgreSQL is not the canonical ledger for BrainClaw.",
        "metadata": {"user_confirmed": True, "visibility_scope": "agent"},
    }
)

assert_true(decision.get("status") == "PROMOTED", f"Decision ingest failed: {decision}")
assert_true(procedure.get("status") == "PROMOTED", f"Procedure ingest failed: {procedure}")
assert_true(decision.get("method") == "memory_md_first_upsert", "Decision ingest did not use MEMORY.md-first mode")
assert_true(procedure.get("method") == "memory_md_first_upsert", "Procedure ingest did not use MEMORY.md-first mode")

decision_record = get_memory(decision["id"])
assert_true(decision_record.get("metadata", {}).get("memory_class") == "decision", f"Decision recall failed: {decision_record}")
assert_true(
    decision_record.get("metadata", {}).get("decision_summary", "").startswith(f"[{marker}] We decided to use PostgreSQL"),
    f"Decision summary missing: {decision_record}",
)
assert_true(
    decision_record.get("metadata", {}).get("backup_mode") == "memory-md-first",
    f"Backup mode missing from decision metadata: {decision_record}",
)

procedure_record = get_memory(procedure["id"])
workflow_steps = procedure_record.get("metadata", {}).get("workflow_steps") or []
assert_true(procedure_record.get("metadata", {}).get("memory_class") == "procedural", f"Procedure recall failed: {procedure_record}")
assert_true(len(workflow_steps) == 3, f"Procedure workflow steps missing: {procedure_record}")
assert_true(workflow_steps[0]["description"] == "Restart the container.", f"Unexpected first workflow step: {workflow_steps}")

retrieval = retrieve_sync(query=marker, intent="general", agent_id=agent_id, tenant_id=tenant_id, top_k=8)
results = retrieval.get("results", [])
assert_true(any(marker in item.get("content", "") for item in results), f"Marker not found in retrieval results: {retrieval}")

contradictions = check_contradictions(entity_name="PostgreSQL", limit=50)
assert_true(contradictions.get("status") == "CONTRADICTIONS_FOUND", f"Contradiction scan failed: {contradictions}")
assert_true(
    any(
        any(marker in content for content in contradiction.get("contents", []))
        for contradiction in contradictions.get("contradictions", [])
    ),
    f"Contradiction evidence did not include acceptance marker: {contradictions}",
)

audit = verify_audit_integrity()
assert_true(audit.get("status") == "HEALTHY", f"Audit integrity check failed: {audit}")

backup_path = Path(decision["backup_path"])
assert_true(backup_path.exists(), f"Backup file does not exist: {backup_path}")
backup_text = backup_path.read_text(encoding="utf-8")
assert_true(marker in backup_text, f"Acceptance marker missing from backup file: {backup_path}")
assert_true("brainclaw:id=" in backup_text, f"BrainClaw backup marker missing from file: {backup_path}")

print(
    json.dumps(
        {
            "container": os.environ.get("HOSTNAME", ""),
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "marker": marker,
            "decision_id": decision["id"],
            "procedure_id": procedure["id"],
            "contradiction_seed_id": contradiction_seed["id"],
            "backup_path": str(backup_path),
            "retrieval_total": retrieval.get("total", len(results)),
            "contradiction_count": len(contradictions.get("contradictions", [])),
            "audit": audit,
            "status": "ok",
        },
        indent=2,
    )
)
PY
