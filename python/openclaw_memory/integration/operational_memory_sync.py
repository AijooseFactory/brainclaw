"""Managed operational MEMORY.md sync helpers for BrainClaw."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


DEFAULT_PRIMARY_AGENT_ID = "albert"
SYNC_START = "<!-- brainclaw:operational-sync:start -->"
SYNC_END = "<!-- brainclaw:operational-sync:end -->"
LEGACY_OPERATIONAL_BLOCK_RE = re.compile(
    r"(?ms)^(#{2,3}\s+Operational\s+(?:Sync|Override)\s+\([^)]+\)\n.*?)(?=^#{2,3}\s+|^\-\-\-\s*$|\Z)"
)


def _load_configured_agents(config_path: Path) -> list[dict]:
    if not config_path.exists():
        return []
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    return config.get("agents", {}).get("list", [])


def resolve_root_memory_md(
    *,
    state_dir: Path,
    config_path: Path,
    primary_agent_id: str = DEFAULT_PRIMARY_AGENT_ID,
    root_memory_path: str | None = None,
) -> Path:
    if root_memory_path:
        return Path(root_memory_path)

    agents = _load_configured_agents(config_path)
    preferred = next((agent for agent in agents if agent.get("id") == primary_agent_id), None)

    candidates: list[Path] = []
    if preferred and preferred.get("workspace"):
        candidates.append(Path(preferred["workspace"]) / "MEMORY.md")
    if preferred and preferred.get("agentDir"):
        candidates.append(Path(preferred["agentDir"]) / "MEMORY.md")

    state_prefix = str(state_dir.resolve())
    for agent in agents:
        workspace = agent.get("workspace")
        if not workspace:
            continue
        workspace_path = Path(workspace)
        candidate = workspace_path / "MEMORY.md"
        if str(workspace_path.resolve()).startswith(state_prefix):
            continue
        candidates.append(candidate)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    if candidates:
        return candidates[0]

    return state_dir / "MEMORY.md"


def discover_memory_sync_targets(
    *,
    state_dir: Path,
    config_path: Path,
    primary_agent_id: str = DEFAULT_PRIMARY_AGENT_ID,
    root_memory_path: str | None = None,
) -> list[Path]:
    root_memory = resolve_root_memory_md(
        state_dir=state_dir,
        config_path=config_path,
        primary_agent_id=primary_agent_id,
        root_memory_path=root_memory_path,
    )

    targets: list[Path] = [root_memory]
    agents = _load_configured_agents(config_path)

    for agent in agents:
        agent_id = str(agent.get("id") or "").strip()
        agent_dir = agent.get("agentDir")
        if agent_dir:
            targets.append(Path(agent_dir) / "MEMORY.md")
        elif agent_id:
            targets.append(state_dir / "agents" / agent_id / "agent" / "MEMORY.md")
        workspace = agent.get("workspace")
        if workspace:
            targets.append(Path(workspace) / "MEMORY.md")

    deduped: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        deduped.append(target)
    return deduped


def _sorted_tool_names(tool_names: Iterable[str] | None) -> list[str]:
    return sorted({str(tool).strip() for tool in (tool_names or []) if str(tool).strip()})


def build_operational_sync_block(snapshot: dict, *, sync_date: str) -> str:
    compatibility_state = snapshot.get("compatibility_state", "unknown")
    if compatibility_state == "installed_compatible":
        integration_line = "BrainClaw + Lossless-Claw integration is implemented, live, and verified."
    elif compatibility_state == "not_installed":
        integration_line = "Lossless-Claw is not installed; BrainClaw remains active without upstream LCM integration."
    else:
        integration_line = (
            "BrainClaw detected Lossless-Claw integration issues; canonical BrainClaw memory remains active while the "
            "upstream context path is degraded or blocked."
        )

    lines = [
        SYNC_START,
        f"## Operational Sync ({sync_date})",
        "",
        "**Current live BrainClaw operational state:**",
        f"- {integration_line}",
        f"- OpenClaw runtime: `{snapshot.get('openclaw_version', 'unknown')}`",
        f"- `plugins.slots.memory = {snapshot.get('memory_slot', 'unknown')}`",
        f"- `plugins.slots.contextEngine = {snapshot.get('context_engine_slot', 'unknown')}`",
        f"- Lossless-Claw version: `{snapshot.get('plugin_version', 'unknown')}`",
        f"- BrainClaw LCM compatibility: `{compatibility_state}`",
    ]

    supported_profile = snapshot.get("supported_profile")
    if supported_profile:
        lines.append(f"- Supported profile: `{supported_profile}`")

    tool_names = _sorted_tool_names(snapshot.get("tool_names"))
    if tool_names:
        lines.append(f"- Tool surfaces available: `{', '.join(tool_names)}`")

    node_count = snapshot.get("node_count")
    edge_count = snapshot.get("edge_count")
    if node_count is not None and edge_count is not None:
        lines.append(f"- Canonical graph rebuild verified from PostgreSQL: `{node_count}` nodes / `{edge_count}` edges")

    control_ui_status = snapshot.get("control_ui_status")
    if control_ui_status == "healthy":
        lines.append("- Control UI preserved and healthy on port `3000`")
    elif control_ui_status:
        lines.append(f"- Control UI status: `{control_ui_status}`")

    lines.extend(
        [
            "",
            "**Operational rule:** Root `MEMORY.md` is the canonical human-readable operational state for Albert/Main Agent. Agent and workspace `MEMORY.md` files mirror this block and must not drift.",
            "",
            "**Interpretation rule:** Older notes that describe BrainClaw/Lossless-Claw as planning-only or independent systems are historical context, not current state.",
            SYNC_END,
        ]
    )
    return "\n".join(lines)


def _remove_legacy_operational_block(text: str) -> str:
    return LEGACY_OPERATIONAL_BLOCK_RE.sub("", text, count=1).strip("\n")


def _upsert_operational_block(existing_text: str, block: str) -> str:
    if SYNC_START in existing_text and SYNC_END in existing_text:
        start = existing_text.index(SYNC_START)
        end = existing_text.index(SYNC_END) + len(SYNC_END)
        updated = f"{existing_text[:start].rstrip()}\n\n{block}\n\n{existing_text[end:].lstrip()}"
        return updated.rstrip() + "\n"

    cleaned = _remove_legacy_operational_block(existing_text)
    separator = "\n---\n"
    if separator in cleaned:
        head, tail = cleaned.split(separator, 1)
        updated = f"{head.rstrip()}{separator}\n{block}\n\n{tail.lstrip()}"
        return updated.rstrip() + "\n"

    if cleaned.strip():
        return f"{block}\n\n{cleaned.lstrip()}".rstrip() + "\n"

    return f"{block}\n"


def _default_memory_header(path: Path) -> str:
    stem = path.parent.name.replace("-", " ").title()
    return f"# {stem} Memory\n"


def sync_operational_memory_files(
    *,
    snapshot: dict,
    state_dir: Path,
    config_path: Path,
    sync_date: str,
    primary_agent_id: str = DEFAULT_PRIMARY_AGENT_ID,
    root_memory_path: str | None = None,
) -> dict:
    targets = discover_memory_sync_targets(
        state_dir=state_dir,
        config_path=config_path,
        primary_agent_id=primary_agent_id,
        root_memory_path=root_memory_path,
    )
    root_memory = resolve_root_memory_md(
        state_dir=state_dir,
        config_path=config_path,
        primary_agent_id=primary_agent_id,
        root_memory_path=root_memory_path,
    )
    block = build_operational_sync_block(snapshot, sync_date=sync_date)

    updated_paths: list[str] = []
    unchanged_paths: list[str] = []

    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.exists() else _default_memory_header(target)
        updated = _upsert_operational_block(existing, block)
        if updated != existing:
            target.write_text(updated, encoding="utf-8")
            updated_paths.append(target.as_posix())
        else:
            unchanged_paths.append(target.as_posix())

    return {
        "root_memory_path": root_memory.as_posix(),
        "target_count": len(targets),
        "updated_paths": updated_paths,
        "unchanged_paths": unchanged_paths,
    }
