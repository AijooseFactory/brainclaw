"""OpenClaw integration exports with lazy imports.

Keep package import light so helper submodules can be used without pulling
optional runtime dependencies like asyncpg during unit tests.
"""

__all__ = [
    "OpenClawMemoryClient",
    "SessionMemoryContext",
    "LCMMigrationHandler",
    "LosslessClawAdapter",
    "CompatibilityState",
    "ReasonCode",
    "PromotionThresholds",
    "OpenClawRuntimeSnapshot",
    "SourceAdapter",
    "SourceAdapterRegistry",
    "LCMSourceAdapter",
    "FileSourceAdapter",
    "ManualSourceAdapter",
]


def __getattr__(name: str):
    if name == "OpenClawMemoryClient":
        from .openclaw_client import OpenClawMemoryClient

        return OpenClawMemoryClient
    if name == "SessionMemoryContext":
        from .session_context import SessionMemoryContext

        return SessionMemoryContext
    if name == "LCMMigrationHandler":
        from .lcm_migration import LCMMigrationHandler

        return LCMMigrationHandler
    if name in {
        "LosslessClawAdapter",
        "CompatibilityState",
        "ReasonCode",
        "PromotionThresholds",
        "OpenClawRuntimeSnapshot",
    }:
        from .lossless_adapter import (
            LosslessClawAdapter,
            CompatibilityState,
            ReasonCode,
            PromotionThresholds,
            OpenClawRuntimeSnapshot,
        )

        return {
            "LosslessClawAdapter": LosslessClawAdapter,
            "CompatibilityState": CompatibilityState,
            "ReasonCode": ReasonCode,
            "PromotionThresholds": PromotionThresholds,
            "OpenClawRuntimeSnapshot": OpenClawRuntimeSnapshot,
        }[name]
    if name in {
        "SourceAdapter",
        "SourceAdapterRegistry",
        "LCMSourceAdapter",
        "FileSourceAdapter",
        "ManualSourceAdapter",
    }:
        from .source_adapter import (
            SourceAdapter,
            SourceAdapterRegistry,
            LCMSourceAdapter,
            FileSourceAdapter,
            ManualSourceAdapter,
        )

        return {
            "SourceAdapter": SourceAdapter,
            "SourceAdapterRegistry": SourceAdapterRegistry,
            "LCMSourceAdapter": LCMSourceAdapter,
            "FileSourceAdapter": FileSourceAdapter,
            "ManualSourceAdapter": ManualSourceAdapter,
        }[name]
    raise AttributeError(name)
