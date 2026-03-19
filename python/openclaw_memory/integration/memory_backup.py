"""Agent-specific MEMORY.md backup helpers for BrainClaw writes."""

from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from pathlib import Path


DEFAULT_STATE_DIR = Path(os.getenv("OPENCLAW_STATE_DIR", "/home/node/.openclaw"))
MIRROR_START = "<!-- brainclaw:memory-mirror:start -->"
MIRROR_END = "<!-- brainclaw:memory-mirror:end -->"
ENTRY_START_TEMPLATE = "<!-- brainclaw:entry:start id={record_id} class={memory_class} -->"
ENTRY_END_TEMPLATE = "<!-- brainclaw:entry:end id={record_id} -->"
MIRROR_HEADER = "## BrainClaw Memory Backup Mirror"
MIRROR_DESCRIPTION = (
    "This section is maintained by BrainClaw. It mirrors canonical Hybrid GraphRAG memories into "
    "`MEMORY.md` so the file backup and BrainClaw memory stay synchronized."
)

CURRENT_ENTRY_RE = re.compile(
    r"(?ms)^<!-- brainclaw:entry:start id=(?P<id>[^ ]+) class=(?P<class>[^ ]+) -->\n"
    r"(?P<body>.*?)\n"
    r"<!-- brainclaw:entry:end id=(?P=id) -->\s*"
)
LEGACY_ENTRY_BLOCK_RE = re.compile(
    r"(?ms)^## .*?\n<!-- brainclaw:id=(?P<id>[^ ]+)\s+class=(?P<class>[^ ]+) -->\n"
    r"(?P<body>.*?)(?=^## .*?\n<!-- brainclaw:id=|\Z)"
)
MIRROR_BLOCK_RE = re.compile(
    rf"(?ms){re.escape(MIRROR_START)}\n(?P<body>.*?){re.escape(MIRROR_END)}\n?"
)


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
    record_id = str(memory_record.get("id", "unknown"))
    content = (memory_record.get("content") or "").strip()
    metadata = dict(memory_record.get("metadata") or {})
    provenance = dict(memory_record.get("provenance") or {})
    timestamp = provenance.get("extraction_timestamp") or memory_record.get("created_at") or "unknown"
    memory_class = str(metadata.get("memory_class") or "semantic")

    header = metadata.get("decision_summary") or content.splitlines()[0] if content else "BrainClaw Memory"
    lines = [
        ENTRY_START_TEMPLATE.format(record_id=record_id, memory_class=memory_class),
        f"## {header}",
        f"<!-- brainclaw:id={record_id} class={memory_class} -->",
        f"- BrainClaw ID: `{record_id}`",
        f"- Memory Class: `{memory_class}`",
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

    lines.extend(
        [
            "",
            content,
            ENTRY_END_TEMPLATE.format(record_id=record_id),
        ]
    )
    return "\n".join(lines)


def _default_memory_header(path: Path) -> str:
    stem = path.parent.name.replace("-", " ").title()
    return f"# {stem} Memory\n"


def _parse_entry_content(entry_body: str) -> str:
    normalized = entry_body.strip()
    if not normalized:
        return ""
    parts = normalized.split("\n\n", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return normalized


def _parse_mirror_entries(raw_text: str) -> "OrderedDict[str, dict]":
    entries: "OrderedDict[str, dict]" = OrderedDict()
    for match in CURRENT_ENTRY_RE.finditer(raw_text):
        entry_id = match.group("id")
        entries[entry_id] = {
            "id": entry_id,
            "memory_class": match.group("class"),
            "content": _parse_entry_content(match.group("body")),
            "rendered": match.group(0).strip(),
        }
    return entries


def _parse_legacy_entries(raw_text: str) -> "OrderedDict[str, dict]":
    entries: "OrderedDict[str, dict]" = OrderedDict()
    for match in LEGACY_ENTRY_BLOCK_RE.finditer(raw_text):
        entry_id = match.group("id")
        entries[entry_id] = {
            "id": entry_id,
            "memory_class": match.group("class"),
            "content": _parse_entry_content(match.group("body")),
            "rendered": match.group(0).strip(),
        }
    return entries


def _split_memory_document(raw_text: str) -> tuple[str, "OrderedDict[str, dict]"]:
    managed_match = MIRROR_BLOCK_RE.search(raw_text)
    if managed_match:
        base_text = MIRROR_BLOCK_RE.sub("", raw_text).rstrip()
        return base_text, _parse_mirror_entries(managed_match.group("body"))

    legacy_entries = _parse_legacy_entries(raw_text)
    base_text = LEGACY_ENTRY_BLOCK_RE.sub("", raw_text).rstrip()
    return base_text, legacy_entries


def _render_mirror_section(entries: "OrderedDict[str, dict]") -> str:
    rendered_entries = [entry["rendered"].strip() for entry in entries.values()]
    lines = [
        MIRROR_START,
        MIRROR_HEADER,
        "",
        MIRROR_DESCRIPTION,
    ]
    if rendered_entries:
        lines.extend(["", *rendered_entries])
    lines.append(MIRROR_END)
    return "\n".join(lines)


def _compose_memory_document(base_text: str, entries: "OrderedDict[str, dict]") -> str:
    managed_section = _render_mirror_section(entries)
    if base_text.strip():
        return f"{base_text.rstrip()}\n\n{managed_section}\n"
    return f"{managed_section}\n"


def parse_memory_backup_entries(raw_text: str) -> list[dict]:
    _, entries = _split_memory_document(raw_text)
    return [
        {
            "id": entry["id"],
            "memory_class": entry["memory_class"],
            "content": entry["content"],
        }
        for entry in entries.values()
        if entry["content"]
    ]


def upsert_memory_backup(
    agent_id: str,
    memory_record: dict,
    state_dir: Path | None = None,
    config_path: Path | None = None,
) -> str:
    target = resolve_agent_memory_md(agent_id, state_dir=state_dir, config_path=config_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = target.read_text(encoding="utf-8") if target.exists() else _default_memory_header(target)
    base_text, entries = _split_memory_document(existing)
    record_id = str(memory_record.get("id") or "unknown")
    entries[record_id] = {
        "id": record_id,
        "memory_class": str(memory_record.get("metadata", {}).get("memory_class") or "semantic"),
        "content": (memory_record.get("content") or "").strip(),
        "rendered": _render_backup_entry(memory_record),
    }

    updated = _compose_memory_document(base_text, entries)
    if updated != existing:
        target.write_text(updated, encoding="utf-8")
    return str(target)


def append_memory_backup(
    agent_id: str,
    memory_record: dict,
    state_dir: Path | None = None,
    config_path: Path | None = None,
) -> str:
    return upsert_memory_backup(
        agent_id=agent_id,
        memory_record=memory_record,
        state_dir=state_dir,
        config_path=config_path,
    )
