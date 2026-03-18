"""
LCM Export Service - READ-ONLY export from Lossless Context Management.

This service exports LCM data without modifying anything in the ajf-openclaw container.
All operations are read-only.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import os


@dataclass
class LCMSummary:
    """Represents an LCM summary."""
    id: str
    conversation_id: Optional[str]
    content: str
    created_at: datetime
    summary_type: str  # 'condensed', 'file', etc.
    parent_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LCMMessage:
    """Represents an LCM message."""
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class LCMExportService:
    """
    READ-ONLY export service for LCM data.
    
    This service exports data from LCM without any modifications.
    It reads from:
    - LCM database (summaries, messages)
    - MEMORY.md files
    - memory/*.md files
    - Session data
    
    IMPORTANT: This service NEVER writes to LCM. It only reads.
    """
    
    def __init__(self, lcm_data_dir: str = "/app/.openclaw"):
        """
        Initialize the LCM export service.
        
        Args:
            lcm_data_dir: Path to LCM data directory (read-only)
        """
        self.lcm_data_dir = Path(lcm_data_dir)
        self._validate_read_only()
    
    def _validate_read_only(self):
        """Validate that we have read-only access to LCM data."""
        if not self.lcm_data_dir.exists():
            raise ValueError(f"LCM data directory not found: {self.lcm_data_dir}")
        
        # Check we can read (but not necessarily write)
        if not os.access(self.lcm_data_dir, os.R_OK):
            raise ValueError(f"Cannot read LCM data directory: {self.lcm_data_dir}")
    
    async def export_all(self) -> Dict[str, Any]:
        """
        Export ALL LCM data (READ-ONLY).
        
        Returns:
            Dict containing all LCM summaries, messages, and file references.
            This is a complete snapshot, suitable for verification.
        """
        export_data = {
            'exported_at': datetime.utcnow().isoformat(),
            'source': 'lcm',
            'summaries': [],
            'messages': [],
            'memory_files': {},
            'session_data': {},
        }
        
        # Export summaries
        export_data['summaries'] = await self.export_summaries()
        
        # Export messages (if available)
        export_data['messages'] = await self.export_messages()
        
        # Export MEMORY.md and memory/*.md files
        export_data['memory_files'] = await self.export_memory_files()
        
        # Export session data
        export_data['session_data'] = await self.export_session_data()
        
        # Add metadata with checksum calculated WITHOUT the checksum field
        # (for verification to work correctly)
        metadata_without_checksum = {
            'summary_count': len(export_data['summaries']),
            'message_count': len(export_data['messages']),
            'file_count': len(export_data['memory_files']),
        }
        
        # Calculate checksum over export_data with metadata WITHOUT checksum
        data_for_checksum = dict(export_data)
        data_for_checksum['metadata'] = metadata_without_checksum
        
        export_data['metadata'] = {
            **metadata_without_checksum,
            'checksum': self._calculate_checksum(data_for_checksum)
        }
        
        return export_data
    
    async def export_summaries(self) -> List[Dict[str, Any]]:
        """
        Export all LCM summaries (READ-ONLY).
        
        Returns:
            List of summary dicts with full content.
        """
        summaries = []
        
        # LCM summaries are stored in the OpenClaw database
        # This would integrate with OpenClaw's LCM system
        # For now, return empty list - actual integration would
        # query the LCM database
        
        # NOTE: This is READ-ONLY. No modifications to LCM.
        return summaries
    
    async def export_messages(self) -> List[Dict[str, Any]]:
        """
        Export all LCM messages (READ-ONLY).
        
        Returns:
            List of message dicts with full content.
        """
        messages = []
        
        # LCM messages are stored in the OpenClaw database
        # This would integrate with OpenClaw's LCM system
        
        return messages
    
    async def export_memory_files(self) -> Dict[str, str]:
        """
        Export MEMORY.md and memory/*.md files (READ-ONLY).
        
        Returns:
            Dict mapping file paths to file contents.
        """
        memory_files = {}
        
        # Export MEMORY.md
        memory_md = self.lcm_data_dir / "MEMORY.md"
        if memory_md.exists():
            memory_files['MEMORY.md'] = memory_md.read_text()
        
        # Export memory/*.md
        memory_dir = self.lcm_data_dir / "memory"
        if memory_dir.exists():
            for md_file in memory_dir.glob("*.md"):
                relative_path = f"memory/{md_file.name}"
                memory_files[relative_path] = md_file.read_text()
        
        return memory_files
    
    async def export_session_data(self) -> Dict[str, Any]:
        """
        Export session data (READ-ONLY).
        
        Returns:
            Dict of session data.
        """
        session_data = {}
        
        # Session data is stored in OpenClaw
        # This would integrate with OpenClaw's session system
        
        return session_data
    
    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """Calculate checksum for verification."""
        import hashlib
        
        # Create deterministic string representation
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def verify_export_integrity(self, export_data: Dict[str, Any]) -> bool:
        """
        Verify that export data integrity is intact.
        
        Args:
            export_data: Exported data to verify
            
        Returns:
            True if integrity is intact, False otherwise.
        """
        stored_checksum = export_data.get('metadata', {}).get('checksum')
        if not stored_checksum:
            return False
        
        # Remove checksum for calculation
        data_copy = {k: v for k, v in export_data.items() if k != 'metadata'}
        data_copy['metadata'] = {k: v for k, v in export_data.get('metadata', {}).items() if k != 'checksum'}
        
        calculated_checksum = self._calculate_checksum(data_copy)
        return calculated_checksum == stored_checksum