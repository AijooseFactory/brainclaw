"""OpenClaw integration exports with lazy imports.

Keep package import light so helper submodules can be used without pulling
optional runtime dependencies like asyncpg during unit tests.
"""

__all__ = ["OpenClawMemoryClient", "SessionMemoryContext", "LCMMigrationHandler"]


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
    raise AttributeError(name)
