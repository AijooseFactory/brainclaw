"""
Access Control and Identity Verification for BrainClaw.
Enforces multi-agent isolation and verifies identity tokens from the bridge.
"""
import hmac
import hashlib
import json
import base64
import os
import time
from typing import Dict, Any, Optional

# Global session context (per-thread in production; per-process in tests)
_CURRENT_CONTEXT: Dict[str, Any] = {}


def verify_identity_token(token_b64: str, secret: str) -> Dict[str, Any]:
    """
    Verifies the HMAC-signed identity token from the TypeScript bridge.

    Args:
        token_b64: Base64 encoded JSON string with identity and signature.
        secret: Shared secret for HMAC-SHA256.

    Returns:
        Verified agent context dictionary.

    Raises:
        ValueError: If token is missing, invalid, or signature doesn't match.
    """
    if not token_b64:
        raise ValueError("Security Block: Missing BRAINCLAW_IDENTITY_TOKEN")
    if not secret:
        raise ValueError("Security Block: Missing BRAINCLAW_SECRET for verification")

    try:
        decoded = base64.b64decode(token_b64).decode("utf-8")
        data = json.loads(decoded)
    except Exception as e:
        raise ValueError(f"Security Block: Invalid token format: {e}")

    signature = data.pop("signature", None)
    if not signature:
        raise ValueError("Security Block: Missing signature in identity token")

    # Canonicalize and verify using stable string concatenation
    message = (
        f"{data.get('agentId')}:{data.get('agentName')}:"
        f"{data.get('teamId')}:{data.get('tenantId')}:{data.get('timestamp')}"
    )

    expected_hmac = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # timing-attack-safe comparison
    if not hmac.compare_digest(signature, expected_hmac):
        raise ValueError("Security Block: Identity token signature mismatch")

    # Expiry check (5-minute TTL)
    timestamp = data.get("timestamp", 0)
    if (time.time() * 1000) - timestamp > 300_000:
        raise ValueError("Security Block: Identity token expired")

    global _CURRENT_CONTEXT
    _CURRENT_CONTEXT = data
    return data


def get_current_agent_id() -> Optional[str]:
    """Returns the verified agent ID for the current request."""
    return _CURRENT_CONTEXT.get("agentId")


def get_current_team_id() -> Optional[str]:
    """Returns the verified team ID for the current request."""
    return _CURRENT_CONTEXT.get("teamId")


def get_current_tenant_id() -> Optional[str]:
    """Returns the verified tenant ID for the current request."""
    return _CURRENT_CONTEXT.get("tenantId")


async def set_db_session_context(conn, *, verify_team: bool = True):
    """
    Sets the session-level variables for PostgreSQL RLS.

    Verifies team membership via DB before setting app.current_team_id,
    preventing team-id spoofing via a crafted identity token.

    Must be called on every acquired connection.

    Args:
        conn:         asyncpg connection.
        verify_team:  If True (default), confirms team membership in DB
                      before trusting the teamId from the token.
    """
    agent_id = get_current_agent_id()
    tenant_id = get_current_tenant_id()
    team_id = get_current_team_id()

    if agent_id:
        await conn.execute(f"SET app.current_agent_id = '{agent_id}'")
    if tenant_id:
        await conn.execute(f"SET app.current_tenant_id = '{tenant_id}'")

    if team_id:
        if verify_team and agent_id:
            # Verify actual DB membership to prevent token spoofing
            from openclaw_memory.security.team_lookup import is_agent_in_team
            confirmed = await is_agent_in_team(agent_id, team_id)
            if not confirmed:
                # Deny team scope — treat as individual agent
                return
        await conn.execute(f"SET app.current_team_id = '{team_id}'")


