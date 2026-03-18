"""
team_lookup.py — BrainClaw Team Verification Service

Verifies agent-to-team membership using the team_members PostgreSQL table
created by migration 001_agent_isolation.sql.

This prevents agent identity spoofing for team-scoped memory access.
"""

import asyncio
import hashlib
from functools import lru_cache
from typing import Optional, Set
from datetime import datetime, timedelta, timezone
import os

# Optional imports — degrade gracefully in test environments
try:
    import asyncpg
    _ASYNCPG_AVAILABLE = True
except ImportError:
    _ASYNCPG_AVAILABLE = False

try:
    from openclaw_memory.observability.logging import get_logger
    logger = get_logger("openclaw.security.team_lookup")
except ImportError:
    import logging
    logger = logging.getLogger("openclaw.security.team_lookup")


# ---------------------------------------------------------------------------
# In-process TTL cache to reduce DB round-trips
# ---------------------------------------------------------------------------
_CACHE: dict[str, tuple[bool, datetime]] = {}
_CACHE_TTL = timedelta(seconds=int(os.environ.get("BRAINCLAW_TEAM_CACHE_TTL", "30")))


def _cache_key(agent_id: str, team_id: str) -> str:
    return hashlib.sha256(f"{agent_id}:{team_id}".encode()).hexdigest()


def _get_cached(agent_id: str, team_id: str) -> Optional[bool]:
    key = _cache_key(agent_id, team_id)
    if key in _CACHE:
        result, cached_at = _CACHE[key]
        if datetime.now(timezone.utc) - cached_at < _CACHE_TTL:
            return result
        del _CACHE[key]
    return None


def _set_cached(agent_id: str, team_id: str, is_member: bool):
    key = _cache_key(agent_id, team_id)
    _CACHE[key] = (is_member, datetime.now(timezone.utc))


def clear_cache():
    """Clear the team membership cache (useful in tests)."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Core lookup — async
# ---------------------------------------------------------------------------

async def is_agent_in_team(
    agent_id: str,
    team_id: str,
    db_url: Optional[str] = None,
) -> bool:
    """
    Check if an agent is a member of the given team.

    Uses a TTL cache to minimize DB round-trips.
    Falls back to False if the DB is unavailable (fail-closed).

    Args:
        agent_id: UUID string of the agent.
        team_id:  Team identifier string.
        db_url:   PostgreSQL URL. Defaults to POSTGRESQL_URL env var.

    Returns:
        True if the agent is a verified member of the team.
    """
    cached = _get_cached(agent_id, team_id)
    if cached is not None:
        return cached

    if not _ASYNCPG_AVAILABLE:
        logger.warning(
            "asyncpg not available; team membership cannot be verified — denying."
        )
        return False

    url = db_url or os.environ.get("POSTGRESQL_URL") or os.environ.get("DATABASE_URL")
    if not url:
        logger.error("No PostgreSQL URL configured — denying team access.")
        return False

    try:
        conn = await asyncpg.connect(url)
        try:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM team_members
                WHERE agent_id = $1::uuid
                  AND team_id  = $2
                LIMIT 1;
                """,
                agent_id,
                team_id,
            )
            result = row is not None
        finally:
            await conn.close()
    except Exception as exc:
        logger.error(f"Team lookup DB error (fail-closed): {exc}")
        result = False

    _set_cached(agent_id, team_id, result)

    if not result:
        logger.warning(
            f"Team access denied: agent={agent_id} is not in team={team_id}"
        )

    return result


def is_agent_in_team_sync(
    agent_id: str,
    team_id: str,
    db_url: Optional[str] = None,
) -> bool:
    """Synchronous wrapper around is_agent_in_team for use in non-async contexts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # In async context — create a task (caller must await later)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run, is_agent_in_team(agent_id, team_id, db_url)
                )
                return future.result(timeout=5)
        else:
            return loop.run_until_complete(
                is_agent_in_team(agent_id, team_id, db_url)
            )
    except Exception as exc:
        logger.error(f"Team lookup sync wrapper error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------

async def add_agent_to_team(agent_id: str, team_id: str, db_url: Optional[str] = None):
    """Add an agent to a team (admin operation)."""
    url = db_url or os.environ.get("POSTGRESQL_URL") or os.environ.get("DATABASE_URL")
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            """
            INSERT INTO team_members (agent_id, team_id)
            VALUES ($1::uuid, $2)
            ON CONFLICT DO NOTHING;
            """,
            agent_id, team_id,
        )
        _set_cached(agent_id, team_id, True)
        logger.info(f"Added agent={agent_id} to team={team_id}")
    finally:
        await conn.close()


async def remove_agent_from_team(
    agent_id: str, team_id: str, db_url: Optional[str] = None
):
    """Remove an agent from a team (admin operation)."""
    url = db_url or os.environ.get("POSTGRESQL_URL") or os.environ.get("DATABASE_URL")
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "DELETE FROM team_members WHERE agent_id = $1::uuid AND team_id = $2;",
            agent_id, team_id,
        )
        # Invalidate cache
        key = _cache_key(agent_id, team_id)
        _CACHE.pop(key, None)
        logger.info(f"Removed agent={agent_id} from team={team_id}")
    finally:
        await conn.close()


async def list_team_members(team_id: str, db_url: Optional[str] = None) -> Set[str]:
    """Return the set of agent_ids for a given team."""
    url = db_url or os.environ.get("POSTGRESQL_URL") or os.environ.get("DATABASE_URL")
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT agent_id::text FROM team_members WHERE team_id = $1;", team_id
        )
        return {r["agent_id"] for r in rows}
    finally:
        await conn.close()
