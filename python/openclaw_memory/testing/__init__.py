"""
Testing utilities for BrainClaw Memory System.

This package provides synthetic data generators for E2E testing
without requiring access to internal BrainClaw modules.

Public API:
    generate_synthetic_documents: Generate standard test documents
    generate_contradictory_documents: Generate contradiction test cases
    generate_entity_rich_documents: Generate documents with rich entities
    SyntheticDataConfig: Configuration for data generation
"""

from openclaw_memory.testing.synthetic_data import (
    generate_synthetic_documents,
    generate_contradictory_documents,
    generate_entity_rich_documents,
    SyntheticDataConfig,
)

__all__ = [
    "generate_synthetic_documents",
    "generate_contradictory_documents",
    "generate_entity_rich_documents",
    "SyntheticDataConfig",
]