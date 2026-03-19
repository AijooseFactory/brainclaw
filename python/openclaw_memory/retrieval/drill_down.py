"""Query-time drill-down from BrainClaw to Lossless-Claw.

FR-020: BrainClaw must remain the primary query and reasoning layer.
BrainClaw queries its own canonical memory first, then optionally calls
Lossless-Claw for expansion when:
  - The result is derived from LCM summary evidence and more detail is needed
  - Confidence is moderate and explanation is needed
  - Contradiction review is required
  - The user explicitly asks for detailed conversational context

Drill-down order (FR-020):
  1. lcm_expand_query if present and allowed
  2. lcm_expand if present and allowed
  3. Direct SQLite DAG traversal for supported schema fingerprints
  4. Return canonical BrainClaw evidence only + surface degraded state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import os
import sqlite3


class DrillDownMethod(Enum):
    LCM_EXPAND_QUERY = "lcm_expand_query"
    LCM_EXPAND = "lcm_expand"
    SQLITE_DAG = "sqlite_dag"
    CANONICAL_ONLY = "canonical_only"


class DrillDownReason(Enum):
    NEED_MORE_DETAIL = "need_more_detail"
    MODERATE_CONFIDENCE = "moderate_confidence"
    CONTRADICTION_REVIEW = "contradiction_review"
    USER_REQUESTED = "user_requested"


@dataclass
class DrillDownResult:
    """Result of a drill-down operation."""

    method_used: DrillDownMethod
    success: bool
    expanded_content: List[Dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    degraded_reason: Optional[str] = None
    source_artifact_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class DrillDownCapability:
    """Detected drill-down capabilities."""

    lcm_expand_query_available: bool = False
    lcm_expand_available: bool = False
    sqlite_dag_available: bool = False
    schema_fingerprint_supported: bool = False


class DrillDownEngine:
    """Executes drill-down from BrainClaw into Lossless-Claw.

    Follows the strict drill-down order defined in FR-020.
    """

    def __init__(
        self,
        tool_registry: Optional[Dict[str, Any]] = None,
        lcm_db_path: Optional[str] = None,
        supported_fingerprints: Optional[set] = None,
    ):
        self._tools = tool_registry or {}
        self._lcm_db_path = lcm_db_path or os.getenv("LCM_DATABASE_PATH")
        self._supported_fingerprints = supported_fingerprints or set()
        self._invocation_count = 0

    def detect_capabilities(self) -> DrillDownCapability:
        """Detect which drill-down methods are available."""
        cap = DrillDownCapability()
        cap.lcm_expand_query_available = "lcm_expand_query" in self._tools
        cap.lcm_expand_available = "lcm_expand" in self._tools
        if self._lcm_db_path and os.path.exists(self._lcm_db_path):
            cap.sqlite_dag_available = True
            # Check schema fingerprint
            try:
                conn = sqlite3.connect(f"file:{self._lcm_db_path}?mode=ro", uri=True)
                cur = conn.cursor()
                cur.execute("SELECT value FROM lcm_meta WHERE key = 'schema_fingerprint'")
                row = cur.fetchone()
                conn.close()
                if row and row[0] in self._supported_fingerprints:
                    cap.schema_fingerprint_supported = True
            except Exception:
                pass
        return cap

    def should_drill_down(
        self,
        memory_result: Dict[str, Any],
        reason: Optional[DrillDownReason] = None,
    ) -> bool:
        """Determine if drill-down is warranted for a memory result.

        Drill-down is warranted when:
        - The result is LCM-derived and more detail is needed
        - Confidence is moderate (0.5–0.75) and explanation would help
        - Contradiction review requires source verification
        - User explicitly requested it
        """
        if reason == DrillDownReason.USER_REQUESTED:
            return True

        if reason == DrillDownReason.CONTRADICTION_REVIEW:
            return True

        # Check if result is LCM-derived
        metadata = memory_result.get("metadata", {}) or memory_result.get("extraction_metadata", {})
        source_plugin = metadata.get("source_plugin")
        if source_plugin != "lossless-claw":
            return False  # Not LCM-derived, no drill-down needed

        if reason == DrillDownReason.NEED_MORE_DETAIL:
            return True

        # Auto-assess: moderate confidence
        confidence = float(memory_result.get("confidence", 1.0))
        if 0.5 <= confidence <= 0.75:
            return True

        return False

    def drill_down(
        self,
        source_artifact_id: str,
        query: Optional[str] = None,
        reason: DrillDownReason = DrillDownReason.NEED_MORE_DETAIL,
    ) -> DrillDownResult:
        """Execute drill-down following FR-020 order.

        1. lcm_expand_query if present
        2. lcm_expand if present
        3. SQLite DAG traversal for supported fingerprints
        4. Canonical-only fallback with degraded state
        """
        self._invocation_count += 1
        cap = self.detect_capabilities()

        # Method 1: lcm_expand_query
        if cap.lcm_expand_query_available and query:
            result = self._try_lcm_expand_query(source_artifact_id, query)
            if result.success:
                return result

        # Method 2: lcm_expand
        if cap.lcm_expand_available:
            result = self._try_lcm_expand(source_artifact_id)
            if result.success:
                return result

        # Method 3: SQLite DAG traversal
        if cap.sqlite_dag_available and cap.schema_fingerprint_supported:
            result = self._try_sqlite_dag(source_artifact_id)
            if result.success:
                return result

        # Method 4: Canonical-only fallback
        return DrillDownResult(
            method_used=DrillDownMethod.CANONICAL_ONLY,
            success=True,
            degraded=True,
            degraded_reason="No Lossless-Claw drill-down available; returning canonical evidence only",
            source_artifact_id=source_artifact_id,
        )

    def _try_lcm_expand_query(self, source_artifact_id: str, query: str) -> DrillDownResult:
        """Attempt drill-down via lcm_expand_query tool."""
        try:
            tool = self._tools.get("lcm_expand_query")
            if tool and callable(tool):
                result = tool(query=query, source_id=source_artifact_id)
                return DrillDownResult(
                    method_used=DrillDownMethod.LCM_EXPAND_QUERY,
                    success=True,
                    expanded_content=result if isinstance(result, list) else [result],
                    source_artifact_id=source_artifact_id,
                )
        except Exception as e:
            return DrillDownResult(
                method_used=DrillDownMethod.LCM_EXPAND_QUERY,
                success=False,
                error=str(e),
                source_artifact_id=source_artifact_id,
            )
        return DrillDownResult(
            method_used=DrillDownMethod.LCM_EXPAND_QUERY,
            success=False,
            error="Tool not callable",
            source_artifact_id=source_artifact_id,
        )

    def _try_lcm_expand(self, source_artifact_id: str) -> DrillDownResult:
        """Attempt drill-down via lcm_expand tool."""
        try:
            tool = self._tools.get("lcm_expand")
            if tool and callable(tool):
                result = tool(source_id=source_artifact_id)
                return DrillDownResult(
                    method_used=DrillDownMethod.LCM_EXPAND,
                    success=True,
                    expanded_content=result if isinstance(result, list) else [result],
                    source_artifact_id=source_artifact_id,
                )
        except Exception as e:
            return DrillDownResult(
                method_used=DrillDownMethod.LCM_EXPAND,
                success=False,
                error=str(e),
                source_artifact_id=source_artifact_id,
            )
        return DrillDownResult(
            method_used=DrillDownMethod.LCM_EXPAND,
            success=False,
            error="Tool not callable",
            source_artifact_id=source_artifact_id,
        )

    def _try_sqlite_dag(self, source_artifact_id: str) -> DrillDownResult:
        """Attempt drill-down via direct SQLite DAG traversal (read-only)."""
        if not self._lcm_db_path:
            return DrillDownResult(
                method_used=DrillDownMethod.SQLITE_DAG,
                success=False,
                error="LCM database path not configured",
                source_artifact_id=source_artifact_id,
            )
        try:
            conn = sqlite3.connect(f"file:{self._lcm_db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Find the summary and its linked messages
            cur.execute(
                "SELECT * FROM summaries WHERE id = ? OR source_artifact_id = ?",
                (source_artifact_id, source_artifact_id),
            )
            summary = cur.fetchone()

            expanded = []
            if summary:
                summary_dict = dict(summary)
                # Fetch linked raw messages if table exists
                try:
                    cur.execute(
                        "SELECT * FROM messages WHERE summary_id = ? ORDER BY created_at ASC",
                        (summary_dict.get("id", source_artifact_id),),
                    )
                    messages = [dict(row) for row in cur.fetchall()]
                    summary_dict["linked_messages"] = messages
                except sqlite3.OperationalError:
                    summary_dict["linked_messages"] = []

                expanded.append(summary_dict)

            conn.close()
            return DrillDownResult(
                method_used=DrillDownMethod.SQLITE_DAG,
                success=len(expanded) > 0,
                expanded_content=expanded,
                source_artifact_id=source_artifact_id,
                error="No matching summary found" if not expanded else None,
            )
        except Exception as e:
            return DrillDownResult(
                method_used=DrillDownMethod.SQLITE_DAG,
                success=False,
                error=str(e),
                source_artifact_id=source_artifact_id,
            )

    @property
    def invocation_count(self) -> int:
        """Total drill-down invocations (for FR-024 metrics)."""
        return self._invocation_count
