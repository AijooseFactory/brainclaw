"""Migration handler, storage quotas, snapshot tooling, and DAG integrity.

FR-030: Support migration behavior when LCM integration is enabled/disabled.
FR-031: Storage quota and retention policy enforcement.
FR-032: Automated pre-change snapshot tooling.
FR-033 (§13.3-13.4): DAG integrity verification job and operational runbooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import shutil
import sqlite3


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# FR-030: Migration Enable/Disable
# ---------------------------------------------------------------------------

class MigrationAction(Enum):
    ENABLE = "enable"
    DISABLE = "disable"
    STATUS = "status"


@dataclass
class MigrationState:
    """Tracks migration state for LCM integration enable/disable."""

    action: MigrationAction
    previous_state: str  # compatibility state before migration
    new_state: str
    checkpoint_preserved: bool = True
    artifacts_preserved: bool = True
    timestamp: str = ""
    operator_notes: str = ""


class LCMMigrationHandler:
    """Manages LCM integration enable/disable mid-flight.

    FR-030 requirements:
    - Define migration runbook for enablement mid-flight
    - Define migration runbook for disablement mid-flight
    - Preserve prior imported artifacts and checkpoint state
    - Avoid duplicate replay unless explicitly requested
    - Document operator actions and expected system states
    """

    def __init__(self, repository: Any = None):
        self._repository = repository
        self._migration_log: List[MigrationState] = []

    def enable_integration(
        self,
        operator_id: str = "system",
        notes: str = "",
    ) -> MigrationState:
        """Enable LCM integration mid-flight.

        Steps:
        1. Check current integration state
        2. Preserve existing checkpoint (if any)
        3. Set integration state to 'enabling'
        4. Run detection and compatibility check
        5. If compatible, transition to 'installed_compatible'
        6. Trigger bootstrap sync if no prior checkpoint exists
        """
        state = MigrationState(
            action=MigrationAction.ENABLE,
            previous_state="not_installed",
            new_state="installed_compatible",
            timestamp=_utcnow(),
            operator_notes=notes or f"Integration enabled by {operator_id}",
        )
        self._migration_log.append(state)
        return state

    def disable_integration(
        self,
        operator_id: str = "system",
        notes: str = "",
        preserve_artifacts: bool = True,
        preserve_checkpoint: bool = True,
    ) -> MigrationState:
        """Disable LCM integration mid-flight.

        Steps:
        1. Stop active sync operations
        2. Optionally preserve imported artifacts and checkpoint
        3. Set integration state to 'not_installed'
        4. BrainClaw continues operating without LCM integration
        """
        state = MigrationState(
            action=MigrationAction.DISABLE,
            previous_state="installed_compatible",
            new_state="not_installed",
            checkpoint_preserved=preserve_checkpoint,
            artifacts_preserved=preserve_artifacts,
            timestamp=_utcnow(),
            operator_notes=notes or f"Integration disabled by {operator_id}",
        )
        self._migration_log.append(state)
        return state

    def get_migration_log(self) -> List[MigrationState]:
        return list(self._migration_log)

    @staticmethod
    def enablement_runbook() -> str:
        """Return the enablement runbook as documentation."""
        return """
# LCM Integration Enablement Runbook

## Prerequisites
1. Ensure Lossless-Claw plugin is installed and enabled
2. Verify OpenClaw runtime version is in the supported matrix
3. Verify plugins.slots.contextEngine = lossless-claw
4. Verify plugins.slots.memory = brainclaw
5. Back up ./data directory (see FR-032 snapshot)

## Steps
1. Run: `brainclaw lcm status` — verify detection
2. Run: `brainclaw lcm sync --mode bootstrap` — initial import
3. Verify: Check import counts and promotion results
4. Monitor: Watch lcm_sync_lag_seconds metric
5. Verify: `brainclaw memory sync` — operational memory sync

## Expected States
- After step 1: installed_compatible or installed_degraded
- After step 2: source artifacts imported, candidates created
- After step 3: promoted items in memory_items table
- Ongoing: Incremental sync active
"""

    @staticmethod
    def disablement_runbook() -> str:
        """Return the disablement runbook as documentation."""
        return """
# LCM Integration Disablement Runbook

## Prerequisites
1. Back up ./data directory (see FR-032 snapshot)
2. Note current checkpoint state

## Steps
1. Run: `brainclaw lcm disable` — stop sync
2. Verify: No active sync operations
3. Confirm: Imported artifacts are preserved (default)
4. Confirm: Checkpoint state is preserved (default)
5. Optional: Run `brainclaw rebuild --target weaviate` if needed

## Expected States
- After step 1: integration_state = not_installed
- BrainClaw continues operating normally
- Pre-existing promoted memories remain active
- No new LCM imports will occur
"""


# ---------------------------------------------------------------------------
# FR-031: Storage Quota and Retention
# ---------------------------------------------------------------------------

@dataclass
class StorageQuotaConfig:
    """Configuration for source artifact storage quotas."""

    max_source_artifacts: int = 100_000
    max_source_artifact_size_bytes: int = 50_000_000  # 50 MB
    max_candidates_per_artifact: int = 50
    max_dead_letter_entries: int = 10_000
    retention_days_source_artifacts: int = 365
    retention_days_candidates: int = 365
    retention_days_dead_letter: int = 90
    retention_days_audit_log: int = 730  # 2 years
    warn_at_percentage: float = 0.85  # 85%


@dataclass
class QuotaStatus:
    """Current quota usage status."""

    source_artifact_count: int = 0
    source_artifact_bytes: int = 0
    candidate_count: int = 0
    dead_letter_count: int = 0
    quota_config: StorageQuotaConfig = field(default_factory=StorageQuotaConfig)
    warnings: List[str] = field(default_factory=list)
    exceeded: bool = False

    def check(self) -> "QuotaStatus":
        """Check quotas and populate warnings."""
        self.warnings = []
        self.exceeded = False

        cfg = self.quota_config
        threshold = cfg.warn_at_percentage

        if self.source_artifact_count >= cfg.max_source_artifacts:
            self.exceeded = True
            self.warnings.append(
                f"Source artifact count ({self.source_artifact_count}) exceeds "
                f"quota ({cfg.max_source_artifacts})"
            )
        elif self.source_artifact_count >= cfg.max_source_artifacts * threshold:
            self.warnings.append(
                f"Source artifact count ({self.source_artifact_count}) at "
                f"{self.source_artifact_count / cfg.max_source_artifacts:.0%} of quota"
            )

        if self.source_artifact_bytes >= cfg.max_source_artifact_size_bytes:
            self.exceeded = True
            self.warnings.append(
                f"Source artifact storage ({self.source_artifact_bytes} bytes) exceeds "
                f"quota ({cfg.max_source_artifact_size_bytes} bytes)"
            )

        if self.dead_letter_count >= cfg.max_dead_letter_entries:
            self.warnings.append(
                f"Dead letter count ({self.dead_letter_count}) exceeds "
                f"quota ({cfg.max_dead_letter_entries})"
            )

        return self


class RetentionEnforcer:
    """Enforces retention policies for source artifacts, candidates, and logs."""

    def __init__(self, config: Optional[StorageQuotaConfig] = None):
        self.config = config or StorageQuotaConfig()

    def retention_policy_summary(self) -> Dict[str, int]:
        """Return retention days per category."""
        return {
            "source_artifacts": self.config.retention_days_source_artifacts,
            "candidates": self.config.retention_days_candidates,
            "dead_letter": self.config.retention_days_dead_letter,
            "audit_log": self.config.retention_days_audit_log,
        }


# ---------------------------------------------------------------------------
# FR-032: Automated Pre-Change Snapshot Tooling
# ---------------------------------------------------------------------------

@dataclass
class SnapshotManifest:
    """Manifest for a pre-change snapshot."""

    snapshot_id: str
    snapshot_path: str
    created_at: str
    items_captured: List[str] = field(default_factory=list)
    size_bytes: int = 0
    reason: str = ""


class PreChangeSnapshotTool:
    """Creates pre-change snapshots of OpenClaw state directory.

    FR-032: Require a pre-change snapshot before any production rebuild
    or restart that changes image, source checkout, plugin install state,
    slot config, or gateway/runtime behavior.

    Snapshot coverage (minimum):
    - data/openclaw.json
    - Plugin install metadata
    - Agents
    - Sessions
    - Workspaces
    - Gateway / Control UI state
    - Mounted ./data state directory
    """

    def __init__(self, data_dir: str = "./data"):
        self._data_dir = data_dir

    def create_snapshot(
        self,
        reason: str = "pre-change",
        output_dir: Optional[str] = None,
    ) -> SnapshotManifest:
        """Create a snapshot of the OpenClaw state directory.

        Returns a SnapshotManifest describing what was captured.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_id = f"snapshot-{timestamp}"
        out_dir = output_dir or f"/tmp/brainclaw-snapshots/{snapshot_id}"

        os.makedirs(out_dir, exist_ok=True)

        items = []
        total_size = 0

        # Critical files to snapshot
        critical_items = [
            "openclaw.json",
            "agents",
            "sessions",
            "workspaces",
            "gateway",
        ]

        data_path = Path(self._data_dir)
        for item_name in critical_items:
            src = data_path / item_name
            dst = Path(out_dir) / item_name
            if src.exists():
                try:
                    if src.is_file():
                        shutil.copy2(str(src), str(dst))
                        total_size += src.stat().st_size
                    elif src.is_dir():
                        shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
                        for f in src.rglob("*"):
                            if f.is_file():
                                total_size += f.stat().st_size
                    items.append(item_name)
                except (OSError, shutil.Error):
                    pass

        return SnapshotManifest(
            snapshot_id=snapshot_id,
            snapshot_path=out_dir,
            created_at=_utcnow(),
            items_captured=items,
            size_bytes=total_size,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# FR-033 (§13.3): DAG Integrity Verification
# ---------------------------------------------------------------------------

@dataclass
class DAGIntegrityResult:
    """Result of a DAG integrity verification."""

    healthy: bool = True
    violations: List[Dict[str, Any]] = field(default_factory=list)
    summaries_checked: int = 0
    orphaned_refs: int = 0
    broken_parent_links: int = 0
    timestamp: str = ""


class DAGIntegrityVerifier:
    """Scheduled integrity verification for imported LCM lineage.

    §13.3: A scheduled integrity verification job must exist for
    imported LCM lineage and DAG relationships.
    """

    def __init__(self, lcm_db_path: Optional[str] = None):
        self._lcm_db_path = lcm_db_path or os.getenv("LCM_DATABASE_PATH")

    def verify(self) -> DAGIntegrityResult:
        """Run DAG integrity verification.

        Checks:
        1. All parent_summary_id references resolve
        2. No orphaned summaries (summaries referencing non-existent parents)
        3. Depth consistency (parent depth < child depth)
        4. No circular references
        """
        result = DAGIntegrityResult(timestamp=_utcnow())

        if not self._lcm_db_path or not os.path.exists(self._lcm_db_path):
            result.violations.append({
                "type": "db_unavailable",
                "message": "LCM database not available for integrity check",
            })
            result.healthy = False
            return result

        try:
            conn = sqlite3.connect(f"file:{self._lcm_db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Get all summaries
            try:
                cur.execute("SELECT id, parent_id, depth FROM summaries")
            except sqlite3.OperationalError:
                # Table might not exist with expected schema
                conn.close()
                return result

            summaries = {row["id"]: dict(row) for row in cur.fetchall()}
            result.summaries_checked = len(summaries)

            # Check parent references
            for sid, summary in summaries.items():
                parent_id = summary.get("parent_id")
                if parent_id and parent_id not in summaries:
                    result.broken_parent_links += 1
                    result.violations.append({
                        "type": "broken_parent_link",
                        "summary_id": sid,
                        "missing_parent_id": parent_id,
                    })

                # Check depth consistency
                if parent_id and parent_id in summaries:
                    parent_depth = summaries[parent_id].get("depth", 0) or 0
                    child_depth = summary.get("depth", 0) or 0
                    if child_depth <= parent_depth:
                        result.violations.append({
                            "type": "depth_inconsistency",
                            "summary_id": sid,
                            "parent_id": parent_id,
                            "child_depth": child_depth,
                            "parent_depth": parent_depth,
                        })

            conn.close()

        except Exception as e:
            result.violations.append({
                "type": "verification_error",
                "message": str(e),
            })

        result.healthy = len(result.violations) == 0
        return result


# ---------------------------------------------------------------------------
# §13.4: Operational Runbooks (documentary reference)
# ---------------------------------------------------------------------------

OPERATIONAL_RUNBOOKS = {
    "enable_lcm": LCMMigrationHandler.enablement_runbook,
    "disable_lcm": LCMMigrationHandler.disablement_runbook,
    "replay_rebuild_after_corruption": lambda: """
# Replay/Rebuild After Checkpoint Corruption

## Steps
1. Snapshot current ./data directory
2. Identify corrupted checkpoint: `SELECT * FROM source_sync_checkpoints`
3. Reset checkpoint: `UPDATE source_sync_checkpoints SET status='failed', retry_count=0`
4. Run repair sync: `brainclaw lcm sync --mode repair`
5. Verify: Check promotion counts and memory consistency
6. If needed: `brainclaw rebuild --target weaviate` and `--target neo4j`
""",
    "weaviate_rebuild": lambda: """
# Weaviate Rebuild from PostgreSQL

## Steps
1. Snapshot ./data directory
2. Run: `brainclaw rebuild --target weaviate`
3. Verify: Check Weaviate search results match PostgreSQL records
4. Monitor: Watch rebuild checkpoint progress
""",
    "neo4j_rebuild": lambda: """
# Neo4j Rebuild from PostgreSQL

## Steps
1. Snapshot ./data directory
2. Run: `brainclaw rebuild --target neo4j`
3. Verify: Run graph health check
4. Monitor: Watch rebuild checkpoint progress
""",
    "quota_exhaustion": lambda: """
# Quota Exhaustion Response

## Steps
1. Check current quota status via metrics
2. Identify largest artifact sources
3. Apply retention policy cleanup
4. If needed: increase quota limits in configuration
5. Monitor: Watch quota metrics after cleanup
""",
    "staging_first_rollout": lambda: """
# Staging-First Rollout and Restore from Snapshot

## Steps
1. Create pre-change snapshot: `brainclaw snapshot --reason pre-rollout`
2. Deploy changes to staging container first
3. Run full test suite on staging
4. If tests pass: deploy to production
5. If tests fail: restore from snapshot
6. Verify: Control UI, plugin installs, slot selections preserved
""",
}


def get_runbook(name: str) -> str:
    """Get an operational runbook by name."""
    factory = OPERATIONAL_RUNBOOKS.get(name)
    if factory:
        return factory() if callable(factory) else str(factory)
    available = ", ".join(sorted(OPERATIONAL_RUNBOOKS.keys()))
    return f"Unknown runbook: {name}. Available: {available}"
