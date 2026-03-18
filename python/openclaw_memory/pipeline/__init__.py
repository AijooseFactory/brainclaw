"""Memory system ingestion pipeline.

This module provides the core pipeline for:
- Chunking content into processable units
- Extracting entities and relationships
- Syncing to Weaviate (semantic) and Neo4j (graph)
- Managing memory lifecycle and write policies
- Secrets redaction before storage

Usage:
    from openclaw_memory.pipeline import IngestionPipeline, ingest_event
    from openclaw_memory.pipeline.chunking import chunk_content
    from openclaw_memory.pipeline.extraction import extract_all
    from openclaw_memory.pipeline.redaction import SecretsRedactor, redact_secrets
"""
from openclaw_memory.pipeline.chunking import Chunk, chunk_content, chunk_by_tokens
from openclaw_memory.pipeline.extraction import (
    Entity,
    Relationship,
    ExtractionResult,
    extract_entities,
    extract_relationships,
    extract_all,
)
from openclaw_memory.pipeline.sync import (
    SyncStatus,
    sync_to_weaviate,
    sync_to_neo4j,
    sync_memory_item,
)
from openclaw_memory.pipeline.ingestion import (
    IngestionEvent,
    IngestionResult,
    IngestionPipeline,
    MemoryLifecycle,
    WritePolicy,
    ingest_event,
    should_promote_to_memory,
    determine_memory_class,
)
from openclaw_memory.pipeline.redaction import (
    SecretsRedactor,
    RedactionResult,
    DetectionResult,
    redact_secrets,
    detect_secrets,
    get_default_redactor,
)

__all__ = [
    # Chunking
    "Chunk",
    "chunk_content",
    "chunk_by_tokens",
    # Extraction
    "Entity",
    "Relationship",
    "ExtractionResult",
    "extract_entities",
    "extract_relationships",
    "extract_all",
    # Sync
    "SyncStatus",
    "sync_to_weaviate",
    "sync_to_neo4j",
    "sync_memory_item",
    # Ingestion
    "IngestionEvent",
    "IngestionResult",
    "IngestionPipeline",
    "MemoryLifecycle",
    "WritePolicy",
    "ingest_event",
    "should_promote_to_memory",
    "determine_memory_class",
    # Redaction
    "SecretsRedactor",
    "RedactionResult",
    "DetectionResult",
    "redact_secrets",
    "detect_secrets",
    "get_default_redactor",
]