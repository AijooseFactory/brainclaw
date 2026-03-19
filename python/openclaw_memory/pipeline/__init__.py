"""Memory system ingestion pipeline with lazy exports.

Keep imports light so unit tests can load extraction helpers without pulling
optional runtime dependencies like asyncpg or graph clients.
"""

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


def __getattr__(name: str):
    if name in {"Chunk", "chunk_content", "chunk_by_tokens"}:
        from openclaw_memory.pipeline.chunking import Chunk, chunk_content, chunk_by_tokens

        return {
            "Chunk": Chunk,
            "chunk_content": chunk_content,
            "chunk_by_tokens": chunk_by_tokens,
        }[name]

    if name in {
        "Entity",
        "Relationship",
        "ExtractionResult",
        "extract_entities",
        "extract_relationships",
        "extract_all",
    }:
        from openclaw_memory.pipeline.extraction import (
            Entity,
            Relationship,
            ExtractionResult,
            extract_entities,
            extract_relationships,
            extract_all,
        )

        return {
            "Entity": Entity,
            "Relationship": Relationship,
            "ExtractionResult": ExtractionResult,
            "extract_entities": extract_entities,
            "extract_relationships": extract_relationships,
            "extract_all": extract_all,
        }[name]

    if name in {"SyncStatus", "sync_to_weaviate", "sync_to_neo4j", "sync_memory_item"}:
        from openclaw_memory.pipeline.sync import (
            SyncStatus,
            sync_to_weaviate,
            sync_to_neo4j,
            sync_memory_item,
        )

        return {
            "SyncStatus": SyncStatus,
            "sync_to_weaviate": sync_to_weaviate,
            "sync_to_neo4j": sync_to_neo4j,
            "sync_memory_item": sync_memory_item,
        }[name]

    if name in {
        "IngestionEvent",
        "IngestionResult",
        "IngestionPipeline",
        "MemoryLifecycle",
        "WritePolicy",
        "ingest_event",
        "should_promote_to_memory",
        "determine_memory_class",
    }:
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

        return {
            "IngestionEvent": IngestionEvent,
            "IngestionResult": IngestionResult,
            "IngestionPipeline": IngestionPipeline,
            "MemoryLifecycle": MemoryLifecycle,
            "WritePolicy": WritePolicy,
            "ingest_event": ingest_event,
            "should_promote_to_memory": should_promote_to_memory,
            "determine_memory_class": determine_memory_class,
        }[name]

    if name in {
        "SecretsRedactor",
        "RedactionResult",
        "DetectionResult",
        "redact_secrets",
        "detect_secrets",
        "get_default_redactor",
    }:
        from openclaw_memory.pipeline.redaction import (
            SecretsRedactor,
            RedactionResult,
            DetectionResult,
            redact_secrets,
            detect_secrets,
            get_default_redactor,
        )

        return {
            "SecretsRedactor": SecretsRedactor,
            "RedactionResult": RedactionResult,
            "DetectionResult": DetectionResult,
            "redact_secrets": redact_secrets,
            "detect_secrets": detect_secrets,
            "get_default_redactor": get_default_redactor,
        }[name]

    raise AttributeError(name)
