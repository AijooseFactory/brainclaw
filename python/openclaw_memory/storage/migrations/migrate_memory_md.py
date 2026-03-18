#!/usr/bin/env python3
"""
Migrate all MEMORY.md files for configured OpenClaw agents into BrainClaw
PostgreSQL `memory_items` table.

Agent list is read from the OpenClaw config file (openclaw.json → agents.list)
so only officially configured agents are included — nothing else.

Agent IDs use deterministic UUID v5 derived from the agent slug so they are
stable across runs.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values

# Stable namespace for deterministic UUID from agent slug
BRAINCLAW_NS = uuid.UUID("b4a1bc1a-0000-4000-a000-b4a1bc1ab000")

# Default openclaw config path (same as OPENCLAW_STATE_DIR)
DEFAULT_STATE_DIR = Path("/home/node/.openclaw")
DEFAULT_CONFIG = DEFAULT_STATE_DIR / "openclaw.json"


def slug_to_uuid(slug: str) -> uuid.UUID:
    """Deterministic UUID v5 from agent slug — stable across runs."""
    return uuid.uuid5(BRAINCLAW_NS, slug)


def load_configured_agents(config_path: Path) -> list[dict]:
    """Parse openclaw.json and return the agents.list entries."""
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    return config.get("agents", {}).get("list", [])


def find_memory_md(agent: dict, state_dir: Path) -> Optional[Path]:
    """
    Resolve the MEMORY.md path for a configured agent.

    OpenClaw stores the main agent's memory under:
      <agentDir>/MEMORY.md        (most agents)
      or inferred as <state_dir>/agents/<id>/agent/MEMORY.md

    The default agent (albert) uses the OpenClaw root state dir:
      <state_dir>/agents/<id>/agent/MEMORY.md
    """
    agent_id = agent["id"]

    # Explicit agentDir in config
    if "agentDir" in agent:
        candidate = Path(agent["agentDir"]) / "MEMORY.md"
        if candidate.exists():
            return candidate

    # Fallback: standard layout
    candidate = state_dir / "agents" / agent_id / "agent" / "MEMORY.md"
    if candidate.exists():
        return candidate

    # Workspace-level MEMORY.md (e.g. workspace-lore/MEMORY.md)
    if "workspace" in agent:
        candidate = Path(agent["workspace"]) / "MEMORY.md"
        if candidate.exists():
            return candidate

    return None


def read_items_from_md(md_path: Path, agent_uuid: uuid.UUID) -> list[dict]:
    """One memory_item row per non-empty line."""
    items = []
    with md_path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            items.append({
                "id": str(uuid.uuid5(agent_uuid, text)),
                "agent_id": str(agent_uuid),
                "visibility_scope": "agent",
                "content": text,
            })
    return items


def pg_connection():
    url = (os.getenv("POSTGRES_URL")
           or os.getenv("POSTGRESQL_URL")
           or os.getenv("DATABASE_URL"))
    if not url:
        raise RuntimeError("POSTGRES_URL (or DATABASE_URL) environment variable is required")
    return psycopg2.connect(url)


def insert_items(conn, items: list[dict]):
    if not items:
        return
    values = [(i["id"], i["agent_id"], i["visibility_scope"], i["content"])
              for i in items]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO memory_items (id, agent_id, visibility_scope, content)
            VALUES %s
            ON CONFLICT (id) DO NOTHING
            """,
            values,
        )
    conn.commit()


def run(state_dir: Path | None = None, config_path: Path | None = None,
        dry_run: bool = False):
    state_dir = state_dir or DEFAULT_STATE_DIR
    config_path = config_path or (state_dir / "openclaw.json")

    print(f"📋 Reading configured agents from {config_path}")
    agents = load_configured_agents(config_path)
    if not agents:
        print("⚠️  No configured agents found in openclaw.json")
        return

    print(f"Found {len(agents)} configured agent(s): {[a['id'] for a in agents]}\n")

    if dry_run:
        for agent in agents:
            md = find_memory_md(agent, state_dir)
            slug = agent["id"]
            uid = slug_to_uuid(slug)
            try:
                display = str(md.relative_to(state_dir))
            except ValueError:
                display = str(md)
            status = display if md else "❌ no MEMORY.md"
            print(f"  {slug} ({uid}) — {status}")
        print("\n⚠️  Dry-run mode – no data written.")
        return

    conn = pg_connection()
    total = 0
    try:
        for agent in agents:
            slug = agent["id"]
            agent_uuid = slug_to_uuid(slug)
            md = find_memory_md(agent, state_dir)
            if md is None:
                print(f"  ⏭️  {slug} — no MEMORY.md (skipping)")
                continue
            items = read_items_from_md(md, agent_uuid)
            try:
                md_display = str(md.relative_to(state_dir))
            except ValueError:
                md_display = str(md)
            print(f"  🚀 {slug} → {len(items)} item(s) from {md_display}")
            insert_items(conn, items)
            total += len(items)
            print(f"     ✅ Done")
    finally:
        conn.close()

    print(f"\n🎉 {total} memory items migrated for {len(agents)} configured agents.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate configured OpenClaw agent MEMORY.md files into BrainClaw"
    )
    parser.add_argument(
        "--state-dir",
        default="/home/node/.openclaw",
        help="OpenClaw state directory (default: /home/node/.openclaw)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to openclaw.json (default: <state-dir>/openclaw.json)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be migrated without writing")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    config_path = Path(args.config) if args.config else None
    run(state_dir, config_path, dry_run=args.dry_run)
