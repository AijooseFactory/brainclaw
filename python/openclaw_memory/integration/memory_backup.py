"""Agent-specific MEMORY.md backup helpers for BrainClaw writes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


DEFAULT_STATE_DIR = Path(os.getenv("OPENCLAW_STATE_DIR", "/home/node/.openclaw"))


def _load_configured_agents(config_path: Path) -> list[dict]:
    if not config_path.exists():
        return []
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    return config.get("agents", {}).get("list", [])


def resolve_agent_memory_md(
    agent_id: str,
    state_dir: Path | None = None,
    config_path: Path | None = None,
) -> Path:
    state_dir = Path(state_dir or DEFAULT_STATE_DIR)
    config_path = Path(config_path or (state_dir / "openclaw.json"))
    configured_agents = _load_configured_agents(config_path)
    agent = next((entry for entry in configured_agents if entry.get("id") == agent_id), None)

    if agent and agent.get("agentDir"):
        return Path(agent["agentDir"]) / "MEMORY.md"

    if agent and agent.get("workspace"):
        return Path(agent["workspace"]) / "MEMORY.md"

    return state_dir / "agents" / agent_id / "agent" / "MEMORY.md"


def _render_backup_entry(memory_record: dict) -> str:
    record_id = memory_record.get("id", "unknown")
    content = (memory_record.get("content") or "").strip()
    metadata = dict(memory_record.get("metadata") or {})
    provenance = dict(memory_record.get("provenance") or {})
    timestamp = provenance.get("extraction_timestamp") or memory_record.get("created_at") or "unknown"

    header = metadata.get("decision_summary") or content.splitlines()[0] if content else "BrainClaw Memory"
    lines = [
        "",
        f"## {header}",
        f"<!-- brainclaw:id={record_id} class={metadata.get('memory_class', 'semantic')} -->",
        f"- BrainClaw ID: `{record_id}`",
        f"- Memory Class: `{metadata.get('memory_class', 'semantic')}`",
        f"- Captured At: `{timestamp}`",
    ]

    if metadata.get("rationale"):
        lines.append(f"- Rationale: {metadata['rationale']}")

    alternatives = metadata.get("alternatives") or []
    if alternatives:
        lines.append(f"- Alternatives: {', '.join(alternatives)}")

    workflow_steps = metadata.get("workflow_steps") or []
    if workflow_steps:
        lines.append("- Workflow Steps:")
        for step in workflow_steps:
            lines.append(f"  - {step.get('step')}. {step.get('description')}")

    lines.extend(["", content, ""])
    return "\n".join(lines)


def append_memory_backup(
    agent_id: str,
    memory_record: dict,
    state_dir: Path | None = None,
    config_path: Path | None = None,
) -> str:
    target = resolve_agent_memory_md(agent_id, state_dir=state_dir, config_path=config_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    marker = f"brainclaw:id={memory_record.get('id')}"
    existing = target.read_text(encoding="utf-8") if target.exists() else "# BrainClaw Memory Backup\n"
    if marker in existing:
        return str(target)

    entry = _render_backup_entry(memory_record)
    if existing and not existing.endswith("\n"):
        existing += "\n"

    target.write_text(existing + entry, encoding="utf-8")
    return str(target)
