import json
from pathlib import Path


def _write_openclaw_config(config_path: Path, root_workspace: Path, state_dir: Path) -> None:
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "list": [
                        {
                            "id": "albert",
                            "workspace": root_workspace.as_posix(),
                        },
                        {
                            "id": "einstein",
                            "agentDir": (state_dir / "agents" / "einstein" / "agent").as_posix(),
                            "workspace": (state_dir / "workspace-einstein").as_posix(),
                        },
                        {
                            "id": "lore",
                            "agentDir": (state_dir / "agents" / "lore" / "agent").as_posix(),
                            "workspace": (state_dir / "workspace-lore").as_posix(),
                        },
                    ]
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_operational_memory_sync_uses_albert_workspace_root_memory_as_canonical_source(tmp_path):
    state_dir = tmp_path / "state"
    root_workspace = tmp_path / "factory"
    root_workspace.mkdir(parents=True)
    (root_workspace / "MEMORY.md").write_text("# Factory Memory\n", encoding="utf-8")

    for relative in [
        state_dir / "agents" / "albert" / "agent",
        state_dir / "agents" / "einstein" / "agent",
        state_dir / "agents" / "lore" / "agent",
        state_dir / "workspace-einstein",
        state_dir / "workspace-lore",
    ]:
        relative.mkdir(parents=True, exist_ok=True)

    config_path = state_dir / "openclaw.json"
    _write_openclaw_config(config_path, root_workspace, state_dir)

    from openclaw_memory.integration.operational_memory_sync import (
        discover_memory_sync_targets,
        resolve_root_memory_md,
    )

    root_memory = resolve_root_memory_md(state_dir=state_dir, config_path=config_path)
    targets = discover_memory_sync_targets(state_dir=state_dir, config_path=config_path)

    assert root_memory == root_workspace / "MEMORY.md"
    assert targets[0] == root_workspace / "MEMORY.md"
    assert state_dir / "agents" / "albert" / "agent" / "MEMORY.md" in targets
    assert state_dir / "agents" / "einstein" / "agent" / "MEMORY.md" in targets
    assert state_dir / "workspace-einstein" / "MEMORY.md" in targets
    assert len(targets) == len(set(targets))


def test_operational_memory_sync_rewrites_managed_block_and_is_idempotent(tmp_path):
    state_dir = tmp_path / "state"
    root_workspace = tmp_path / "factory"
    root_workspace.mkdir(parents=True)

    root_memory = root_workspace / "MEMORY.md"
    root_memory.write_text("# Factory Memory\n\n---\n\nLegacy root context.\n", encoding="utf-8")

    albert_agent_memory = state_dir / "agents" / "albert" / "agent" / "MEMORY.md"
    agent_memory = state_dir / "agents" / "einstein" / "agent" / "MEMORY.md"
    workspace_memory = state_dir / "workspace-einstein" / "MEMORY.md"
    lore_memory = state_dir / "agents" / "lore" / "agent" / "MEMORY.md"

    for memory_path in [albert_agent_memory, agent_memory, workspace_memory, lore_memory]:
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text("# Agent Memory\n\nExisting notes.\n", encoding="utf-8")

    config_path = state_dir / "openclaw.json"
    _write_openclaw_config(config_path, root_workspace, state_dir)

    from openclaw_memory.integration.operational_memory_sync import sync_operational_memory_files

    snapshot = {
        "openclaw_version": "2026.3.14",
        "memory_slot": "brainclaw",
        "context_engine_slot": "lossless-claw",
        "plugin_version": "0.4.0",
        "compatibility_state": "installed_compatible",
        "supported_profile": "lossless-claw-v0.4.0-core",
        "tool_names": ["lcm_grep", "lcm_describe", "lcm_expand_query", "lcm_expand"],
        "node_count": 577,
        "edge_count": 26,
        "control_ui_status": "healthy",
    }

    first = sync_operational_memory_files(
        snapshot=snapshot,
        state_dir=state_dir,
        config_path=config_path,
        sync_date="2026-03-19",
    )
    second = sync_operational_memory_files(
        snapshot=snapshot,
        state_dir=state_dir,
        config_path=config_path,
        sync_date="2026-03-19",
    )

    assert first["target_count"] == 6
    assert second["target_count"] == 6
    assert root_memory.as_posix() == first["root_memory_path"]

    synced_root = root_memory.read_text(encoding="utf-8")
    synced_albert_agent = albert_agent_memory.read_text(encoding="utf-8")
    synced_agent = agent_memory.read_text(encoding="utf-8")

    assert synced_root.count("brainclaw:operational-sync:start") == 1
    assert synced_root.count("brainclaw:operational-sync:end") == 1
    assert "Root `MEMORY.md` is the canonical human-readable operational state for Albert/Main Agent." in synced_root
    assert "BrainClaw + Lossless-Claw integration is implemented, live, and verified." in synced_root
    assert "`577` nodes / `26` edges" in synced_root
    assert synced_root == root_memory.read_text(encoding="utf-8")
    assert synced_albert_agent.count("brainclaw:operational-sync:start") == 1
    assert synced_agent.count("brainclaw:operational-sync:start") == 1
    assert "Older notes that describe BrainClaw/Lossless-Claw as planning-only or independent systems are historical context, not current state." in synced_agent


def test_detect_control_ui_status_falls_back_to_internal_gateway_port(monkeypatch):
    from openclaw_memory import bridge_entrypoints

    attempts = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(url, timeout=0):
        attempts.append(url)
        if url == "http://127.0.0.1:3000/__openclaw__/control/":
            raise OSError("connection refused")
        if url == "http://127.0.0.1:18789/__openclaw__/control/":
            return _Response()
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(bridge_entrypoints.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("BRAINCLAW_CONTROL_UI_URL", raising=False)

    status = bridge_entrypoints._detect_control_ui_status()

    assert status == "healthy"
    assert attempts == [
        "http://127.0.0.1:3000/__openclaw__/control/",
        "http://127.0.0.1:18789/__openclaw__/control/",
    ]
