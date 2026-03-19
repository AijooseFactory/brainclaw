"""Source adapter protocol and registry for BrainClaw integration sources.

FR-004: BrainClaw must register Lossless-Claw through a source adapter model
with a pluggable adapter layer. Integration logic must not be hardcoded deep
inside unrelated ingestion code paths.

Supported adapters:
  - LCMSourceAdapter  (Lossless-Claw SQLite DAG summaries)
  - FileSourceAdapter (file-based artifact import)
  - ManualSourceAdapter (operator-injected knowledge)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class SourceArtifact:
    """Normalized artifact produced by any source adapter."""

    source_artifact_id: str
    source_plugin: str
    source_artifact_type: str
    content: str
    source_session_id: Optional[str] = None
    source_conversation_id: Optional[str] = None
    source_parent_summary_id: Optional[str] = None
    summary_depth: Optional[int] = None
    source_created_at: Optional[str] = None
    earliest_source_timestamp: Optional[str] = None
    latest_source_timestamp: Optional[str] = None
    original_message_ids: List[str] = field(default_factory=list)
    topic_hints: List[str] = field(default_factory=list)
    file_ids: List[str] = field(default_factory=list)
    kind: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionReport:
    """Detection and compatibility report from a source adapter."""

    source_plugin: str
    compatibility_state: str
    reason_code: Optional[str] = None
    source_version: Optional[str] = None
    schema_fingerprint: Optional[str] = None
    supported_profile: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SourceAdapter(Protocol):
    """Protocol that all BrainClaw source adapters must satisfy.

    Each adapter is responsible for:
    1. Detecting whether its source is available and compatible
    2. Iterating artifacts (with checkpoint-based pagination)
    3. Classifying session statefulness when applicable
    """

    source_plugin: str

    def detect(self) -> DetectionReport:
        """Detect source availability and compatibility."""
        ...

    def iter_artifacts(
        self,
        *,
        last_created_at: Optional[str] = None,
        last_artifact_id: Optional[str] = None,
    ) -> List[SourceArtifact]:
        """Iterate artifacts from the source, respecting checkpoint position."""
        ...


class LCMSourceAdapter:
    """Adapter wrapping LosslessClawAdapter to satisfy the SourceAdapter protocol.

    This is the primary adapter for importing Lossless-Claw summary artifacts
    into BrainClaw's canonical pipeline.
    """

    source_plugin: str = "lossless-claw"

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    def detect(self) -> DetectionReport:
        report = self._adapter.detect()
        return DetectionReport(
            source_plugin=self.source_plugin,
            compatibility_state=report.compatibility_state.value
            if hasattr(report.compatibility_state, "value")
            else str(report.compatibility_state),
            reason_code=report.reason_code,
            source_version=report.plugin_version,
            schema_fingerprint=report.schema_fingerprint,
            supported_profile=report.supported_profile,
            extra={"tool_availability": report.tool_availability},
        )

    def iter_artifacts(
        self,
        *,
        last_created_at: Optional[str] = None,
        last_artifact_id: Optional[str] = None,
    ) -> List[SourceArtifact]:
        raw_artifacts = self._adapter.iter_summary_artifacts(
            last_created_at=last_created_at,
            last_artifact_id=last_artifact_id,
        )
        return [
            SourceArtifact(
                source_artifact_id=raw["source_artifact_id"],
                source_plugin=self.source_plugin,
                source_artifact_type="lcm_summary",
                content=raw["content"],
                source_session_id=raw.get("source_session_id"),
                source_conversation_id=raw.get("source_conversation_id"),
                source_parent_summary_id=raw.get("source_parent_summary_id"),
                summary_depth=raw.get("summary_depth"),
                source_created_at=raw.get("source_created_at"),
                earliest_source_timestamp=raw.get("earliest_source_timestamp"),
                latest_source_timestamp=raw.get("latest_source_timestamp"),
                original_message_ids=raw.get("original_message_ids", []),
                topic_hints=raw.get("topic_hints", []),
                file_ids=raw.get("file_ids", []),
                kind=raw.get("kind"),
            )
            for raw in raw_artifacts
        ]

    def classify_session_statefulness(self, session_id: str):
        """Delegate session policy to the underlying adapter."""
        return self._adapter.classify_session_statefulness(session_id)


class FileSourceAdapter:
    """Adapter for importing artifacts from local files or directories.

    Supports importing markdown, JSON, or YAML files as source artifacts
    for BrainClaw extraction and promotion.
    """

    source_plugin: str = "file"

    def __init__(self, base_path: str) -> None:
        self._base_path = base_path

    def detect(self) -> DetectionReport:
        import os

        if os.path.isdir(self._base_path):
            return DetectionReport(
                source_plugin=self.source_plugin,
                compatibility_state="installed_compatible",
            )
        return DetectionReport(
            source_plugin=self.source_plugin,
            compatibility_state="not_installed",
            reason_code="SOURCE_UNREACHABLE",
        )

    def iter_artifacts(
        self,
        *,
        last_created_at: Optional[str] = None,
        last_artifact_id: Optional[str] = None,
    ) -> List[SourceArtifact]:
        import os
        from pathlib import Path

        artifacts: List[SourceArtifact] = []
        base = Path(self._base_path)
        if not base.is_dir():
            return artifacts

        for file_path in sorted(base.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix not in {".md", ".json", ".yaml", ".yml", ".txt"}:
                continue
            rel_path = str(file_path.relative_to(base))
            stat = file_path.stat()
            created_at = str(stat.st_mtime)

            # Checkpoint filtering
            if last_created_at and created_at <= last_created_at:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            artifacts.append(
                SourceArtifact(
                    source_artifact_id=rel_path,
                    source_plugin=self.source_plugin,
                    source_artifact_type="file_artifact",
                    content=content,
                    source_created_at=created_at,
                    kind=file_path.suffix.lstrip("."),
                    metadata={"file_path": str(file_path)},
                )
            )
        return artifacts


class ManualSourceAdapter:
    """Adapter for operator-injected knowledge artifacts.

    Accepts pre-built artifacts via `add_artifact()` and yields them
    through the standard adapter interface.
    """

    source_plugin: str = "manual"

    def __init__(self) -> None:
        self._artifacts: List[SourceArtifact] = []

    def detect(self) -> DetectionReport:
        return DetectionReport(
            source_plugin=self.source_plugin,
            compatibility_state="installed_compatible",
        )

    def add_artifact(self, artifact: SourceArtifact) -> None:
        """Add an artifact for ingestion."""
        self._artifacts.append(artifact)

    def iter_artifacts(
        self,
        *,
        last_created_at: Optional[str] = None,
        last_artifact_id: Optional[str] = None,
    ) -> List[SourceArtifact]:
        if last_created_at is None and last_artifact_id is None:
            return list(self._artifacts)
        # For manual adapter, return only artifacts added after the checkpoint
        return [
            a
            for a in self._artifacts
            if a.source_created_at and (last_created_at is None or a.source_created_at > last_created_at)
        ]


class SourceAdapterRegistry:
    """Registry for managing active source adapters.

    Provides lookup and iteration over registered adapters.
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        """Register a source adapter by its plugin name."""
        self._adapters[adapter.source_plugin] = adapter

    def unregister(self, source_plugin: str) -> None:
        """Remove a registered adapter."""
        self._adapters.pop(source_plugin, None)

    def get(self, source_plugin: str) -> Optional[SourceAdapter]:
        """Get a registered adapter by plugin name."""
        return self._adapters.get(source_plugin)

    def list_adapters(self) -> List[str]:
        """List registered adapter plugin names."""
        return list(self._adapters.keys())

    def detect_all(self) -> Dict[str, DetectionReport]:
        """Run detection on all registered adapters."""
        return {name: adapter.detect() for name, adapter in self._adapters.items()}
