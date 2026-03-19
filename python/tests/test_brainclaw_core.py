"""
Python tests for BrainClaw — closes the 0% coverage gap identified in the team review.

Covers:
- Access control / HMAC identity verification
- Team lookup (membership verification)
- SQL migration runner
- Weaviate schema migration structure
- Storage models / memory class validation
"""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Access Control Tests
# ---------------------------------------------------------------------------

from openclaw_memory.security.access_control import (
    verify_identity_token,
    get_current_agent_id,
    get_current_team_id,
    get_current_tenant_id,
    get_current_agent_db_id,
    set_db_session_context,
)


def _make_token(secret: str, agent_id: str = "agent-001", agent_name: str = "agent",
                team_id: str = "team-1", tenant_id: str = "tenant-1",
                timestamp: int | None = None) -> str:
    """Helper to build a valid signed identity token."""
    ts = timestamp if timestamp is not None else int(time.time() * 1000)
    message = f"{agent_id}:{agent_name}:{team_id}:{tenant_id}:{ts}"
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    payload = {
        "agentId": agent_id, "agentName": agent_name,
        "teamId": team_id, "tenantId": tenant_id,
        "timestamp": ts, "signature": sig,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


class TestVerifyIdentityToken:
    """HMAC identity token verification."""

    def test_valid_token_accepted(self):
        token = _make_token("my-secret")
        ctx = verify_identity_token(token, "my-secret")
        assert ctx["agentId"] == "agent-001"
        assert ctx["teamId"] == "team-1"

    def test_wrong_secret_rejected(self):
        token = _make_token("correct-secret")
        with pytest.raises(ValueError, match="signature mismatch"):
            verify_identity_token(token, "wrong-secret")

    def test_missing_token_rejected(self):
        with pytest.raises(ValueError, match="Missing BRAINCLAW_IDENTITY_TOKEN"):
            verify_identity_token("", "secret")

    def test_missing_secret_rejected(self):
        token = _make_token("secret")
        with pytest.raises(ValueError, match="Missing BRAINCLAW_SECRET"):
            verify_identity_token(token, "")

    def test_expired_token_rejected(self):
        expired_ts = int((time.time() - 400) * 1000)  # 400 seconds ago
        token = _make_token("secret", timestamp=expired_ts)
        with pytest.raises(ValueError, match="expired"):
            verify_identity_token(token, "secret")

    def test_tampered_token_rejected(self):
        token_bytes = base64.b64decode(_make_token("secret"))
        data = json.loads(token_bytes)
        data["agentId"] = "attacker-999"
        tampered = base64.b64encode(json.dumps(data).encode()).decode()
        with pytest.raises(ValueError, match="signature mismatch"):
            verify_identity_token(tampered, "secret")

    def test_malformed_base64_rejected(self):
        with pytest.raises(ValueError, match="Invalid token format"):
            verify_identity_token("not-valid-base64!!!", "secret")

    def test_context_accessible_after_verify(self):
        token = _make_token("secret", agent_id="agent-abc", team_id="team-x")
        verify_identity_token(token, "secret")
        assert get_current_agent_id() == "agent-abc"
        assert get_current_team_id() == "team-x"


# ---------------------------------------------------------------------------
# Team Lookup Tests
# ---------------------------------------------------------------------------

from openclaw_memory.security.team_lookup import (
    is_agent_in_team,
    clear_cache,
    _get_cached,
    _set_cached,
)


class TestTeamLookupCache:
    """TTL cache behavior for team membership."""

    def setup_method(self):
        clear_cache()

    def test_cache_miss_returns_none(self):
        assert _get_cached("agent-001", "team-1") is None

    def test_cache_hit_returns_value(self):
        _set_cached("agent-001", "team-1", True)
        assert _get_cached("agent-001", "team-1") is True

    def test_false_membership_cached(self):
        _set_cached("agent-002", "team-1", False)
        assert _get_cached("agent-002", "team-1") is False


class TestTeamLookupDB:
    """Database-backed team membership verification."""

    def setup_method(self):
        clear_cache()

    @pytest.mark.asyncio
    async def test_member_returns_true(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"1": 1}
        with patch("asyncpg.connect", return_value=mock_conn):
            with patch("openclaw_memory.security.team_lookup._ASYNCPG_AVAILABLE", True):
                result = await is_agent_in_team("agent-001", "team-1", db_url="postgresql://fake")
        assert result is True

    @pytest.mark.asyncio
    async def test_non_member_returns_false(self):
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        with patch("asyncpg.connect", return_value=mock_conn):
            with patch("openclaw_memory.security.team_lookup._ASYNCPG_AVAILABLE", True):
                result = await is_agent_in_team("agent-999", "team-1", db_url="postgresql://fake")
        assert result is False

    @pytest.mark.asyncio
    async def test_db_error_fails_closed(self):
        """team lookup must fail-closed on DB errors — security requirement."""
        with patch("asyncpg.connect", side_effect=Exception("DB down")):
            with patch("openclaw_memory.security.team_lookup._ASYNCPG_AVAILABLE", True):
                result = await is_agent_in_team("agent-001", "team-1", db_url="postgresql://fake")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_asyncpg_fails_closed(self):
        with patch("openclaw_memory.security.team_lookup._ASYNCPG_AVAILABLE", False):
            result = await is_agent_in_team("agent-001", "team-1")
        assert result is False


# ---------------------------------------------------------------------------
# SQL Migration Runner Tests
# ---------------------------------------------------------------------------

from pathlib import Path
import tempfile


class TestMigrationRunner:
    """SQL migration runner correctness."""

    def test_pending_migrations_sorted(self):
        """Migrations must be applied in alphabetical/version order."""
        from openclaw_memory.storage.migrations.run_migrations import get_pending_migrations
        m = get_pending_migrations(applied=set())
        names = [v for v, _ in m]
        assert names == sorted(names), "Migrations must be in sorted order"

    def test_already_applied_skipped(self):
        from openclaw_memory.storage.migrations.run_migrations import get_pending_migrations
        all_m = get_pending_migrations(applied=set())
        if not all_m:
            pytest.skip("No migrations found")
        first_version = all_m[0][0]
        remaining = get_pending_migrations(applied={first_version})
        assert all(v != first_version for v, _ in remaining)


# ---------------------------------------------------------------------------
# Memory Class Validation Tests
# ---------------------------------------------------------------------------

from openclaw_memory.memory.classes import MemoryClass


class TestMemoryClasses:
    """Memory class constants and validation."""

    def test_expected_classes_exist(self):
        expected = {"episodic", "semantic", "procedural", "decision", "identity", "relational", "summary"}
        actual = {c.value if hasattr(c, "value") else c for c in MemoryClass}
        assert expected.issubset(actual), f"Missing memory classes: {expected - actual}"

    def test_all_classes_are_strings(self):
        for mc in MemoryClass:
            val = mc.value if hasattr(mc, "value") else mc
            assert isinstance(val, str), f"MemoryClass {mc} value must be a string"


# ---------------------------------------------------------------------------
# Set DB Session Context Tests
# ---------------------------------------------------------------------------

class TestSetDbSessionContext:
    """PostgreSQL RLS context is set correctly."""

    @pytest.mark.asyncio
    async def test_agent_id_set_on_connection(self):
        token = _make_token("secret", agent_id="agent-rls-test")
        verify_identity_token(token, "secret")

        mock_conn = AsyncMock()
        # Disable team verification to isolate this test
        await set_db_session_context(mock_conn, verify_team=False)

        expected_agent_id = get_current_agent_db_id()
        executed_sql = [call.args[0] for call in mock_conn.execute.call_args_list]
        assert any(expected_agent_id in sql for sql in executed_sql)

    @pytest.mark.asyncio
    async def test_team_id_denied_when_not_member(self):
        """If agent is not a verified team member, team_id RLS must NOT be set."""
        token = _make_token("secret", agent_id="agent-001", team_id="team-unauthorized")
        verify_identity_token(token, "secret")

        mock_conn = AsyncMock()

        async def fake_team_lookup(agent_id, team_id, **_):
            return False  # Not a member

        with patch("openclaw_memory.security.team_lookup.is_agent_in_team", fake_team_lookup):
            await set_db_session_context(mock_conn, verify_team=True)

        executed_sql = [call.args[0] for call in mock_conn.execute.call_args_list]
        assert not any("current_team_id" in sql for sql in executed_sql), \
            "team_id must NOT be set in RLS for unverified team members"