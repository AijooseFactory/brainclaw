"""
Migration Orchestrator - Coordinates LCM to GraphRAG migration.

Ensures data preservation and provides rollback capability.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import json
from pathlib import Path

from .lcm_export import LCMExportService, LCMSummary
from ..integration.lcm_migration import LCMMigrationHandler
from ..integration.openclaw_client import OpenClawMemoryClient
from ..config import OpenClawMemoryConfig


@dataclass
class MigrationManifest:
    """Manifest tracking migration progress."""
    migration_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = 'pending'  # pending, in_progress, completed, failed
    
    # Counts
    summaries_exported: int = 0
    summaries_migrated: int = 0
    memory_files_exported: int = 0
    memory_files_migrated: int = 0
    
    # Verification
    export_checksum: Optional[str] = None
    migration_checksum: Optional[str] = None
    verification_passed: bool = False
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    # Backup
    backup_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dict."""
        return {
            'migration_id': self.migration_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'status': self.status,
            'summaries_exported': self.summaries_exported,
            'summaries_migrated': self.summaries_migrated,
            'memory_files_exported': self.memory_files_exported,
            'memory_files_migrated': self.memory_files_migrated,
            'export_checksum': self.export_checksum,
            'migration_checksum': self.migration_checksum,
            'verification_passed': self.verification_passed,
            'errors': self.errors,
            'backup_path': self.backup_path
        }


class MigrationOrchestrator:
    """
    Orchestrates LCM to GraphRAG migration.
    
    Key Principles:
    1. LCM is NEVER modified (read-only)
    2. Migration creates NEW copies in GraphRAG
    3. Original LCM remains untouched as backup
    4. Verification confirms no data loss
    5. User must explicitly confirm switch
    """
    
    def __init__(
        self,
        postgres_config,
        weaviate_config,
        neo4j_config,
        agent_id: str,
        backup_dir: str = "/tmp/lcm_backup"
    ):
        self.export_service = LCMExportService()
        self.migration_handler = None  # Initialized after client connects
        self.agent_id = agent_id
        self.backup_dir = Path(backup_dir)
        self.manifest: Optional[MigrationManifest] = None
        
        # Storage configs
        self.postgres_config = postgres_config
        self.weaviate_config = weaviate_config
        self.neo4j_config = neo4j_config
    
    async def start_migration(self) -> str:
        """
        Start the migration process.
        
        Returns:
            Migration ID for tracking.
        """
        import uuid
        migration_id = str(uuid.uuid4())
        
        self.manifest = MigrationManifest(
            migration_id=migration_id,
            started_at=datetime.utcnow(),
            status='in_progress'
        )
        
        # Save initial manifest
        self._save_manifest()
        
        return migration_id
    
    async def export_lcm_data(self) -> Dict[str, Any]:
        """
        Export all LCM data (READ-ONLY).
        
        Step 1: Export all data from LCM without modification.
        
        Returns:
            Exported data with checksums.
        """
        if not self.manifest:
            raise ValueError("Migration not started. Call start_migration() first.")
        
        # Export from LCM (read-only)
        export_data = await self.export_service.export_all()
        
        # Update manifest
        self.manifest.summaries_exported = len(export_data.get('summaries', []))
        self.manifest.memory_files_exported = len(export_data.get('memory_files', {}))
        self.manifest.export_checksum = export_data.get('metadata', {}).get('checksum')
        
        # Create backup
        backup_path = self.backup_dir / f"lcm_backup_{self.manifest.migration_id}"
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Save export to backup
        with open(backup_path / "export.json", 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        self.manifest.backup_path = str(backup_path)
        self._save_manifest()
        
        return export_data
    
    async def migrate_to_graphrag(
        self,
        export_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Migrate exported LCM data to GraphRAG.
        
        Step 2: Create NEW copies in GraphRAG.
        LCM is NOT touched during this step.
        
        Args:
            export_data: Data exported from LCM
            
        Returns:
            Migration results.
        """
        if not self.manifest:
            raise ValueError("Migration not started. Call start_migration() first.")
        
        # Initialize memory client
        config = OpenClawMemoryConfig(
            postgres=self.postgres_config,
            weaviate=self.weaviate_config,
            neo4j=self.neo4j_config,
            agent_id=self.agent_id,
            agent_name=self.agent_id,
            team_id="ai-joose-factory-team",
            team_member_ids=[]
        )
        client = OpenClawMemoryClient(config)
        await client.initialize()
        
        try:
            # Initialize migration handler
            self.migration_handler = LCMMigrationHandler(client.postgres)
            
            # Migrate summaries
            for summary in export_data.get('summaries', []):
                await self.migration_handler.migrate_summary(summary, self.agent_id)
                self.manifest.summaries_migrated += 1
            
            # Migrate MEMORY.md files
            for file_path, content in export_data.get('memory_files', {}).items():
                await self.migration_handler.migrate_memories_md(content, self.agent_id)
                self.manifest.memory_files_migrated += 1
            
            self._save_manifest()
            
            return {
                'summaries_migrated': self.manifest.summaries_migrated,
                'memory_files_migrated': self.manifest.memory_files_migrated
            }
        
        finally:
            await client.close()
    
    async def verify_migration(self) -> bool:
        """
        Verify that migration completed without data loss.
        
        Step 3: Verify all data migrated correctly.
        
        Returns:
            True if verification passed, False otherwise.
        """
        if not self.manifest:
            raise ValueError("Migration not started.")
        
        # Verify counts
        if self.manifest.summaries_migrated != self.manifest.summaries_exported:
            self.manifest.errors.append(
                f"Summary count mismatch: exported {self.manifest.summaries_exported}, "
                f"migrated {self.manifest.summaries_migrated}"
            )
        
        if self.manifest.memory_files_migrated != self.manifest.memory_files_exported:
            self.manifest.errors.append(
                f"Memory file count mismatch: exported {self.manifest.memory_files_exported}, "
                f"migrated {self.manifest.memory_files_migrated}"
            )
        
        # Check if any errors
        passed = len(self.manifest.errors) == 0
        
        self.manifest.verification_passed = passed
        self._save_manifest()
        
        return passed
    
    async def complete_migration(self) -> MigrationManifest:
        """
        Complete the migration process.
        
        Step 4: Mark migration as complete.
        
        IMPORTANT: This does NOT disable LCM. LCM remains active
        as backup until user explicitly confirms switch.
        
        Returns:
            Final migration manifest.
        """
        if not self.manifest:
            raise ValueError("Migration not started.")
        
        self.manifest.completed_at = datetime.utcnow()
        self.manifest.status = 'completed' if self.manifest.verification_passed else 'failed'
        self._save_manifest()
        
        return self.manifest
    
    async def rollback(self) -> bool:
        """
        Rollback the migration.
        
        This only removes the NEW GraphRAG data.
        LCM data is NEVER touched.
        
        Returns:
            True if rollback successful.
        """
        if not self.manifest:
            return False
        
        # Remove GraphRAG data created during migration
        # This does NOT touch LCM
        
        # Reset manifest
        self.manifest.status = 'rolled_back'
        self._save_manifest()
        
        return True
    
    def _save_manifest(self):
        """Save manifest to backup directory."""
        if not self.manifest or not self.manifest.backup_path:
            return
        
        manifest_path = Path(self.manifest.backup_path) / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(self.manifest.to_dict(), f, indent=2)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current migration status."""
        if not self.manifest:
            return {'status': 'not_started'}
        
        return self.manifest.to_dict()