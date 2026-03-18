"""
Migration package for LCM to GraphRAG migration.

This package provides:
- LCMExportService: Read-only export from LCM
- MigrationOrchestrator: Orchestrates the migration process

All operations are read-only from LCM - no data is modified.
"""

# Import lcm_export first (no dependencies)
from .lcm_export import LCMExportService, LCMSummary, LCMMessage

# Import orchestrator with try/except to handle missing dependencies gracefully
try:
    from .orchestrator import MigrationOrchestrator, MigrationManifest
except ImportError as e:
    # If integration modules aren't available, provide placeholders
    MigrationOrchestrator = None
    MigrationManifest = None

__all__ = [
    'LCMExportService',
    'LCMSummary',
    'LCMMessage',
    'MigrationOrchestrator',
    'MigrationManifest',
]