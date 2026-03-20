"""Sync pipeline module for syncing memory to Weaviate and Neo4j."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
import logging

from openclaw_memory.storage.postgres import MemoryItem
from openclaw_memory.pipeline.extraction import Entity, Relationship

logger = logging.getLogger(__name__)


@dataclass
class SyncStatus:
    """Tracks the sync status of a memory item."""
    memory_item_id: str
    weaviate_id: Optional[str] = None
    neo4j_id: Optional[str] = None
    weaviate_synced: bool = False
    neo4j_synced: bool = False
    weaviate_synced_at: Optional[datetime] = None
    neo4j_synced_at: Optional[datetime] = None
    error: Optional[str] = None


async def sync_to_weaviate(
    client: Any,
    memory_items: List[MemoryItem],
    batch_size: int = 100,
) -> Dict[str, Any]:
    """Sync memory items to Weaviate for semantic search.
    
    Args:
        client: Weaviate client instance
        memory_items: List of MemoryItems to sync
        batch_size: Number of items per batch
        
    Returns:
        Dict with sync results
    """
    if not memory_items:
        return {"synced_count": 0, "ids": []}
    
    synced_ids = []
    failed_count = 0
    
    try:
        # Prepare objects for Weaviate batch import
        objects = []
        for item in memory_items:
            if item.content_embedding is None:
                logger.warning(f"Skipping item {item.id} - no embedding")
                continue
                
            obj = {
                "id": str(item.id),
                "class": "MemoryChunk",
                "properties": {
                    "memory_item_id": str(item.id),
                    "tenant_id": str(item.tenant_id) if item.tenant_id else None,
                    "memory_class": item.memory_class,
                    "memory_type": item.memory_type,
                    "content": item.content,
                    "session_id": str(item.source_session_id) if item.source_session_id else None,
                    "valid_from": item.valid_from.isoformat() if item.valid_from else None,
                    "valid_to": item.valid_to.isoformat() if item.valid_to else None,
                    "confidence": item.confidence,
                    "visibility_scope": item.visibility_scope,
                    "source_type": "memory_item",
                },
                "vector": item.content_embedding,
            }
            objects.append(obj)
        
        # Batch import
        if objects:
            # Use client batch import
            if hasattr(client, 'batch_import'):
                result = await client.batch_import(objects)
                if result and "ids" in result:
                    synced_ids.extend(result["ids"])
            elif hasattr(client, 'batch'):
                # Alternative API
                with client.batch as batch:
                    for obj in objects:
                        batch.add_object(**obj)
                    batch.flush()
                synced_ids = [o["id"] for o in objects]
        
        return {
            "synced_count": len(synced_ids),
            "ids": synced_ids,
            "failed_count": failed_count,
        }
        
    except Exception as e:
        logger.error(f"Weaviate sync failed: {e}")
        return {
            "synced_count": len(synced_ids),
            "ids": synced_ids,
            "failed_count": len(memory_items) - len(synced_ids),
            "error": str(e),
        }


async def sync_to_neo4j(
    client: Any,
    entities: List[Entity],
    relationships: List[Relationship],
) -> Dict[str, Any]:
    """Sync entities and relationships to Neo4j graph.
    
    Args:
        client: Neo4j driver/session
        entities: List of entities to sync
        relationships: List of relationships to sync
        
    Returns:
        Dict with sync results
    """
    entity_count = 0
    rel_count = 0
    errors = []
    
    try:
        # Sync entities as nodes
        if entities:
            for entity in entities:
                try:
                    # Build Cypher query for entity node
                    query = """
                    MERGE (e:Entity {
                        id: $id,
                        entity_type: $entity_type,
                        name: $name,
                        canonical_name: $canonical_name
                    })
                    SET e.description = $description,
                        e.properties = $properties,
                        e.confidence = $confidence
                    RETURN e.id as id
                    """
                    
                    params = {
                        "id": entity.id,
                        "entity_type": entity.entity_type,
                        "name": entity.name,
                        "canonical_name": entity.canonical_name,
                        "description": entity.description,
                        "properties": entity.properties,
                        "confidence": entity.confidence,
                    }
                    
                    if hasattr(client, 'run'):
                        client.run(query, params)
                    elif hasattr(client, 'execute_query'):
                        await client.execute_query(query, params)
                    
                    entity_count += 1
                    
                except Exception as e:
                    errors.append(f"Entity {entity.id}: {e}")
        
        # Sync relationships as edges
        if relationships:
            for rel in relationships:
                try:
                    query = """
                    MATCH (s:Entity {id: $source_id})
                    MATCH (t:Entity {id: $target_id})
                    MERGE (s)-[r:RELATES {
                        id: $rel_id,
                        relationship_type: $rel_type
                    }]->(t)
                    SET r.properties = $properties,
                        r.confidence = $confidence,
                        r.evidence = $evidence
                    """
                    
                    params = {
                        "rel_id": rel.id,
                        "source_id": rel.source_entity_id,
                        "target_id": rel.target_entity_id,
                        "rel_type": rel.relationship_type,
                        "properties": rel.properties,
                        "confidence": rel.confidence,
                        "evidence": rel.evidence,
                    }
                    
                    if hasattr(client, 'run'):
                        client.run(query, params)
                    elif hasattr(client, 'execute_query'):
                        await client.execute_query(query, params)
                    
                    rel_count += 1
                    
                except Exception as e:
                    errors.append(f"Relationship {rel.id}: {e}")
        
        return {
            "synced_count": entity_count + rel_count,
            "entity_count": entity_count,
            "relationship_count": rel_count,
            "errors": errors,
        }
        
    except Exception as e:
        logger.error(f"Neo4j sync failed: {e}")
        return {
            "synced_count": entity_count + rel_count,
            "entity_count": entity_count,
            "relationship_count": rel_count,
            "error": str(e),
            "errors": errors,
        }


async def sync_memory_item(
    postgres_client: Any,
    weaviate_client: Any,
    neo4j_client: Any,
    memory_item: MemoryItem,
    entities: List[Entity],
    relationships: List[Relationship],
    max_retries: int = 3,
) -> SyncStatus:
    """Sync a memory item to all three stores.
    
    Orchestrates syncing to PostgreSQL, Weaviate, and Neo4j with retry logic.
    
    Args:
        postgres_client: PostgreSQL client
        weaviate_client: Weaviate client
        neo4j_client: Neo4j client
        memory_item: The memory item to sync
        entities: Extracted entities
        relationships: Extracted relationships
        max_retries: Maximum retry attempts for failed syncs
        
    Returns:
        SyncStatus with sync state
    """
    status = SyncStatus(
        memory_item_id=str(memory_item.id),
    )
    
    # Sync to Weaviate and Neo4j in parallel to reduce indexing latency
    sync_tasks = []
    
    # Weaviate Task
    if memory_item.content_embedding:
        async def sync_weaviate_with_retries():
            for attempt in range(max_retries):
                try:
                    wv_result = await sync_to_weaviate(weaviate_client, [memory_item])
                    if wv_result and wv_result.get("synced_count", 0) > 0:
                        return wv_result["ids"][0]
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Weaviate sync final failure: {e}")
                    logger.warning(f"Weaviate sync attempt {attempt + 1} failed: {e}")
            return None
        
        sync_tasks.append(sync_weaviate_with_retries())
    else:
        sync_tasks.append(asyncio.sleep(0, result=None)) # Placeholder

    # Neo4j Task
    if entities or relationships:
        async def sync_neo4j_with_retries():
            for attempt in range(max_retries):
                try:
                    neo4j_result = await sync_to_neo4j(neo4j_client, entities, relationships)
                    if neo4j_result and neo4j_result.get("synced_count", 0) > 0:
                        return True
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Neo4j sync final failure: {e}")
                    logger.warning(f"Neo4j sync attempt {attempt + 1} failed: {e}")
            return False
        
        sync_tasks.append(sync_neo4j_with_retries())
    else:
        sync_tasks.append(asyncio.sleep(0, result=False)) # Placeholder

    # Run tasks in parallel
    wv_id, neo_synced = await asyncio.gather(*sync_tasks)
    
    if wv_id:
        status.weaviate_id = wv_id
        status.weaviate_synced = True
        status.weaviate_synced_at = datetime.utcnow()
    
    if neo_synced:
        status.neo4j_synced = True
        status.neo4j_synced_at = datetime.utcnow()
    
    # Fallback/Self-Healing logic:
    # If one of the stores failed persistently, we record the error and allow the system 
    # to retry during the next maintenance cycle.
    if not wv_id or not neo_synced:
        status.error = f"SelfHealing: Partial sync failure. Weaviate: {bool(wv_id)}, Neo4j: {neo_synced}"
        logger.warning(status.error)

    # Update sync status in PostgreSQL
    await postgres_client.update_sync_status(
        memory_item.id,
        weaviate_id=status.weaviate_id,
        neo4j_id=status.neo4j_id,
        weaviate_synced=status.weaviate_synced,
        neo4j_synced=status.neo4j_synced,
    )
    
    return status


# Alias for backwards compatibility
sync_all = sync_memory_item