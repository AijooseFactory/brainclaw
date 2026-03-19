"""Lossless-Claw detection, compatibility, and read-only source adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, Optional


class CompatibilityState(str, Enum):
    NOT_INSTALLED = "not_installed"
    INSTALLED_COMPATIBLE = "installed_compatible"
    INSTALLED_DEGRADED = "installed_degraded"
    INSTALLED_INCOMPATIBLE = "installed_incompatible"
    INSTALLED_UNREACHABLE = "installed_unreachable"


class ReasonCode(str, Enum):
    SCHEMA_FINGERPRINT_UNKNOWN = "SCHEMA_FINGERPRINT_UNKNOWN"
    SCOPE_AMBIGUOUS = "SCOPE_AMBIGUOUS"
    STATELESS_SESSION = "STATELESS_SESSION"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    ACL_DENIED = "ACL_DENIED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONTRADICTED = "CONTRADICTED"
    SOURCE_UNREACHABLE = "SOURCE_UNREACHABLE"
    OPENCLAW_VERSION_UNSUPPORTED = "OPENCLAW_VERSION_UNSUPPORTED"
    LOSSLESS_CLAW_VERSION_UNSUPPORTED = "LOSSLESS_CLAW_VERSION_UNSUPPORTED"
    SLOT_UNRESOLVED = "SLOT_UNRESOLVED"
    PLUGIN_DISABLED = "PLUGIN_DISABLED"


class PromotionThresholds:
    RAW_AUTO_PROMOTE = 0.85
    INTERPRETIVE = 0.70
    TOPIC_HINT_MATCH = 0.60


MIN_SUPPORTED_OPENCLAW_BASELINE = (2026, 3, 14)
SUPPORTED_LOSSLESS_CLAW_VERSIONS = {"0.4.0"}

REQUIRED_SCHEMA: Dict[str, set[str]] = {
    "conversations": {"conversation_id", "session_id"},
    "messages": {"message_id", "conversation_id", "seq", "role", "content", "token_count", "created_at"},
    "summaries": {
        "summary_id",
        "conversation_id",
        "kind",
        "depth",
        "content",
        "token_count",
        "earliest_at",
        "latest_at",
        "descendant_count",
        "created_at",
        "file_ids",
    },
    "message_parts": {"part_id", "message_id", "session_id", "part_type", "ordinal"},
    "summary_messages": {"summary_id", "message_id", "ordinal"},
    "summary_parents": {"summary_id", "parent_summary_id", "ordinal"},
    "context_items": {"conversation_id", "ordinal", "item_type"},
    "large_files": {"file_id", "conversation_id", "storage_uri", "exploration_summary"},
}


@dataclass
class OpenClawRuntimeSnapshot:
    openclaw_version: str
    memory_slot: Optional[str]
    context_engine_slot: Optional[str]
    plugin_enabled: bool
    plugin_installed: bool
    plugin_version: Optional[str]
    plugin_install_path: Optional[str]
    tool_names: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Optional[dict[str, Any]]) -> "OpenClawRuntimeSnapshot":
        data = payload or {}
        return cls(
            openclaw_version=str(data.get("openclaw_version") or "unknown"),
            memory_slot=data.get("memory_slot"),
            context_engine_slot=data.get("context_engine_slot"),
            plugin_enabled=bool(data.get("plugin_enabled")),
            plugin_installed=bool(data.get("plugin_installed")),
            plugin_version=data.get("plugin_version"),
            plugin_install_path=data.get("plugin_install_path"),
            tool_names=list(data.get("tool_names") or []),
        )


@dataclass
class SessionPolicyDecision:
    session_id: str
    statefulness: str
    import_allowed: bool
    promotable: bool
    reason_code: Optional[str] = None


@dataclass
class LosslessClawDetectionReport:
    compatibility_state: CompatibilityState
    reason_code: Optional[str]
    db_path: Optional[str]
    schema_fingerprint: Optional[str]
    supported_profile: Optional[str]
    tool_availability: dict[str, bool]
    openclaw_version: str
    plugin_version: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatibility_state": self.compatibility_state.value,
            "reason_code": self.reason_code,
            "db_path": self.db_path,
            "schema_fingerprint": self.schema_fingerprint,
            "supported_profile": self.supported_profile,
            "tool_availability": self.tool_availability,
            "openclaw_version": self.openclaw_version,
            "plugin_version": self.plugin_version,
        }


class LosslessClawAdapter:
    """Read-only adapter for detecting and interrogating a Lossless-Claw install."""

    def __init__(
        self,
        runtime: OpenClawRuntimeSnapshot,
        db_path: Optional[str] = None,
        plugin_config: Optional[dict[str, Any]] = None,
    ):
        self.runtime = runtime
        self.plugin_config = dict(plugin_config or {})
        self._explicit_db_path = db_path

    def resolve_db_path(self) -> Optional[str]:
        configured = (
            self._explicit_db_path
            or self.plugin_config.get("losslessClawDbPath")
            or self.plugin_config.get("dbPath")
            or os.getenv("LCM_DATABASE_PATH")
        )
        if configured:
            return str(configured)
        state_dir = os.getenv("OPENCLAW_STATE_DIR")
        if state_dir:
            return str(Path(state_dir).expanduser() / "lcm.db")
        return str(Path.home() / ".openclaw" / "lcm.db")

    def _compile_patterns(self, key: str, env_key: str) -> list[re.Pattern[str]]:
        configured = self.plugin_config.get(key)
        if configured is None:
            configured = os.getenv(env_key, "")
        if isinstance(configured, str):
            values = [value.strip() for value in configured.split(",") if value.strip()]
        else:
            values = [str(value).strip() for value in configured or [] if str(value).strip()]
        return [re.compile(value) for value in values]

    def classify_session_statefulness(self, session_id: str) -> SessionPolicyDecision:
        for pattern in self._compile_patterns("ignoreSessionPatterns", "LCM_IGNORE_SESSION_PATTERNS"):
            if pattern.search(session_id):
                return SessionPolicyDecision(
                    session_id=session_id,
                    statefulness="ignored",
                    import_allowed=False,
                    promotable=False,
                    reason_code=ReasonCode.SCOPE_AMBIGUOUS.value,
                )

        for pattern in self._compile_patterns(
            "statelessSessionPatterns",
            "LCM_STATELESS_SESSION_PATTERNS",
        ):
            if pattern.search(session_id):
                return SessionPolicyDecision(
                    session_id=session_id,
                    statefulness="stateless",
                    import_allowed=True,
                    promotable=False,
                    reason_code=ReasonCode.STATELESS_SESSION.value,
                )

        return SessionPolicyDecision(
            session_id=session_id,
            statefulness="stateful",
            import_allowed=True,
            promotable=True,
        )

    def _tool_availability(self) -> dict[str, bool]:
        known = set(self.runtime.tool_names)
        return {
            "lcm_grep": "lcm_grep" in known,
            "lcm_describe": "lcm_describe" in known,
            "lcm_expand_query": "lcm_expand_query" in known,
            "lcm_expand": "lcm_expand" in known,
        }

    def _connect_sqlite(self, db_path: str) -> sqlite3.Connection:
        uri = f"file:{Path(db_path).expanduser()}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def _inspect_schema(self, db_path: str) -> tuple[str, Optional[str]]:
        with self._connect_sqlite(db_path) as conn:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            discovered: dict[str, list[str]] = {}
            for table_name in tables:
                columns = [
                    row[1]
                    for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                ]
                discovered[table_name] = columns

        fingerprint_source = ";".join(
            f"{table}:{','.join(discovered[table])}" for table in sorted(discovered)
        )
        fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16]

        if not REQUIRED_SCHEMA.keys() <= discovered.keys():
            return fingerprint, None
        for table_name, required_columns in REQUIRED_SCHEMA.items():
            if not required_columns <= set(discovered.get(table_name, [])):
                return fingerprint, None
        return fingerprint, "lossless-claw-v0.4.0-core"

    @staticmethod
    def _parse_openclaw_version(version: str) -> Optional[tuple[int, int, int]]:
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version or "").strip())
        if not match:
            return None
        return tuple(int(group) for group in match.groups())

    @staticmethod
    def _load_json_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return list(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return []
            return list(parsed) if isinstance(parsed, list) else []
        return []

    def iter_summary_artifacts(
        self,
        *,
        last_created_at: Optional[str] = None,
        last_artifact_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        db_path = self.resolve_db_path()
        if not db_path:
            return []

        query = """
            SELECT
                s.summary_id,
                c.session_id,
                s.conversation_id,
                s.kind,
                s.depth,
                s.content,
                s.created_at,
                s.earliest_at,
                s.latest_at,
                s.file_ids,
                (
                    SELECT sp.parent_summary_id
                    FROM summary_parents sp
                    WHERE sp.summary_id = s.summary_id
                    ORDER BY sp.ordinal
                    LIMIT 1
                ) AS parent_summary_id,
                COALESCE((
                    SELECT json_group_array(sm.message_id)
                    FROM (
                        SELECT message_id, ordinal
                        FROM summary_messages
                        WHERE summary_id = s.summary_id
                        ORDER BY ordinal
                    ) sm
                ), '[]') AS original_message_ids
            FROM summaries s
            JOIN conversations c ON c.conversation_id = s.conversation_id
            WHERE (
                ? IS NULL
                OR s.created_at > ?
                OR (s.created_at = ? AND (? IS NULL OR s.summary_id > ?))
            )
            ORDER BY s.created_at, s.summary_id
        """

        with self._connect_sqlite(db_path) as conn:
            rows = conn.execute(
                query,
                (
                    last_created_at,
                    last_created_at,
                    last_created_at,
                    last_artifact_id,
                    last_artifact_id,
                ),
            ).fetchall()

        artifacts: list[dict[str, Any]] = []
        for row in rows:
            content = str(row[5] or "")
            topic_hints = [hint for hint in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", content)[:8]]
            artifacts.append(
                {
                    "source_artifact_id": row[0],
                    "source_session_id": row[1],
                    "source_conversation_id": row[2],
                    "kind": row[3],
                    "summary_depth": row[4],
                    "content": content,
                    "source_created_at": row[6],
                    "earliest_source_timestamp": row[7],
                    "latest_source_timestamp": row[8],
                    "file_ids": self._load_json_list(row[9]),
                    "source_parent_summary_id": row[10],
                    "original_message_ids": [str(item) for item in self._load_json_list(row[11])],
                    "topic_hints": topic_hints,
                }
            )
        return artifacts

    def detect(self) -> LosslessClawDetectionReport:
        tool_availability = self._tool_availability()

        if not self.runtime.plugin_installed:
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.NOT_INSTALLED,
                reason_code=None,
                db_path=None,
                schema_fingerprint=None,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        if not self.runtime.plugin_enabled:
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_DEGRADED,
                reason_code=ReasonCode.PLUGIN_DISABLED.value,
                db_path=self.resolve_db_path(),
                schema_fingerprint=None,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        if self.runtime.memory_slot != "brainclaw" or self.runtime.context_engine_slot != "lossless-claw":
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_INCOMPATIBLE,
                reason_code=ReasonCode.SLOT_UNRESOLVED.value,
                db_path=self.resolve_db_path(),
                schema_fingerprint=None,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        parsed_openclaw_version = self._parse_openclaw_version(self.runtime.openclaw_version)
        if (
            parsed_openclaw_version is None
            or parsed_openclaw_version < MIN_SUPPORTED_OPENCLAW_BASELINE
        ):
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_INCOMPATIBLE,
                reason_code=ReasonCode.OPENCLAW_VERSION_UNSUPPORTED.value,
                db_path=self.resolve_db_path(),
                schema_fingerprint=None,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        if (self.runtime.plugin_version or "") not in SUPPORTED_LOSSLESS_CLAW_VERSIONS:
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_INCOMPATIBLE,
                reason_code=ReasonCode.LOSSLESS_CLAW_VERSION_UNSUPPORTED.value,
                db_path=self.resolve_db_path(),
                schema_fingerprint=None,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        db_path = self.resolve_db_path()
        if not db_path:
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_UNREACHABLE,
                reason_code=ReasonCode.SOURCE_UNREACHABLE.value,
                db_path=None,
                schema_fingerprint=None,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        expanded_db_path = str(Path(db_path).expanduser())
        if not Path(expanded_db_path).exists():
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_UNREACHABLE,
                reason_code=ReasonCode.SOURCE_UNREACHABLE.value,
                db_path=expanded_db_path,
                schema_fingerprint=None,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        try:
            fingerprint, supported_profile = self._inspect_schema(expanded_db_path)
        except sqlite3.Error:
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_UNREACHABLE,
                reason_code=ReasonCode.SOURCE_UNREACHABLE.value,
                db_path=expanded_db_path,
                schema_fingerprint=None,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        if supported_profile is None:
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_INCOMPATIBLE,
                reason_code=ReasonCode.SCHEMA_FINGERPRINT_UNKNOWN.value,
                db_path=expanded_db_path,
                schema_fingerprint=fingerprint,
                supported_profile=None,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        if not tool_availability["lcm_grep"] or not tool_availability["lcm_describe"]:
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_DEGRADED,
                reason_code=ReasonCode.TOOL_UNAVAILABLE.value,
                db_path=expanded_db_path,
                schema_fingerprint=fingerprint,
                supported_profile=supported_profile,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        if not (tool_availability["lcm_expand_query"] or tool_availability["lcm_expand"]):
            return LosslessClawDetectionReport(
                compatibility_state=CompatibilityState.INSTALLED_DEGRADED,
                reason_code=ReasonCode.TOOL_UNAVAILABLE.value,
                db_path=expanded_db_path,
                schema_fingerprint=fingerprint,
                supported_profile=supported_profile,
                tool_availability=tool_availability,
                openclaw_version=self.runtime.openclaw_version,
                plugin_version=self.runtime.plugin_version,
            )

        return LosslessClawDetectionReport(
            compatibility_state=CompatibilityState.INSTALLED_COMPATIBLE,
            reason_code=None,
            db_path=expanded_db_path,
            schema_fingerprint=fingerprint,
            supported_profile=supported_profile,
            tool_availability=tool_availability,
            openclaw_version=self.runtime.openclaw_version,
            plugin_version=self.runtime.plugin_version,
        )
