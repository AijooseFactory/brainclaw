"""Result fusion module for BrainClaw Memory System.

This module combines results from multiple storage backends (PostgreSQL,
Weaviate, Neo4j), performs deduplication, reranks results, and assembles
evidence for LLM context.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse
import uuid
import time

# Observability imports (optional - graceful degradation)
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from ..observability.logging import get_logger
    from ..observability.metrics import MetricsHelper
    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False

from .intent import Intent
from .policy import get_retrieval_plan
from .rrf_fusion import (
    reciprocal_rank_fusion,
    fuse_with_provenance,
    apply_rrf_then_weight,
    DEFAULT_RRF_K,
)
from ..storage.postgres import PostgresClient
from ..storage.weaviate_client import WeaviateClient
from ..storage.neo4j_client import Neo4jClient
from ..embeddings import EmbeddingService, EmbeddingConfig
from ..config import OpenClawMemoryConfig, RRF_K_DEFAULT, RRF_MAX_RESULTS

# Get logger
logger = get_logger("openclaw.retrieval.fusion") if _OBSERVABILITY_AVAILABLE else None


class _FakeSpan:
    """Fake span for when tracing is not available."""
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def set_attribute(self, key, value):
        pass
    
    def set_status(self, status):
        pass
    
    def record_exception(self, exc):
        pass


# Type for individual result items
@dataclass
class ResultItem:
    """A single retrieved result with metadata."""
    content: str
    source: str  # postgres, weaviate, neo4j
    relevance: float = 0.5
    confidence: float = 0.5
    recency: float = 0.5
    graph_distance: Optional[float] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    provenance: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "source": self.source,
            "relevance": self.relevance,
            "confidence": self.confidence,
            "recency": self.recency,
            "graph_distance": self.graph_distance,
            "id": self.id,
            "provenance": self.provenance,
            "metadata": self.metadata,
        }


def _normalize_result(result: Dict[str, Any], source: str) -> ResultItem:
    """Normalize a result from any source into a ResultItem.
    
    Args:
        result: Raw result dictionary from a storage backend.
        source: Source identifier (postgres, weaviate, neo4j).
        
    Returns:
        Normalized ResultItem.
    """
    return ResultItem(
        content=result.get("content", result.get("text", "")),
        source=source,
        relevance=result.get("relevance", result.get("score", 0.5)),
        confidence=result.get("confidence", result.get("extraction_confidence", 0.5)),
        recency=result.get("recency", _calculate_recency(result)),
        graph_distance=result.get("graph_distance"),
        id=result.get("id", str(uuid.uuid4())),
        provenance=result.get("provenance", {}),
        metadata=result.get("metadata", {}),
    )


def _calculate_recency(result: Dict[str, Any]) -> float:
    """Calculate recency score from timestamp fields.
    
    Args:
        result: Result dictionary potentially containing timestamp.
        
    Returns:
        Recency score between 0 and 1.
    """
    # Check various timestamp field names
    timestamp = (
        result.get("created_at") or
        result.get("timestamp") or
        result.get("valid_from") or
        result.get("updated_at")
    )
    
    if timestamp:
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return 0.5
        elif isinstance(timestamp, datetime):
            pass
        else:
            return 0.5
        
        # Calculate days since
        if timestamp.tzinfo is not None:
            now = datetime.now(timestamp.tzinfo)
        else:
            now = datetime.utcnow()
        
        days_old = (now - timestamp).days
        
        # Convert to 0-1 score (newer = higher)
        # 0 days = 1.0, 365 days = 0.0
        return max(0.0, 1.0 - (days_old / 365))
    
    return 0.5


# Storage backend connection placeholders
# These will be replaced with actual storage client calls in production

async def query_postgres(
    query_params: Dict[str, Any],
    tenant_id: str,
    limit: int
) -> List[Dict[str, Any]]:
    """Query PostgreSQL for memory items.
    
    In production, this would use the actual PostgresClient.
    Currently returns empty list as placeholder.
    
    Args:
        query_params: Query parameters from retrieval plan.
        tenant_id: Tenant identifier.
        limit: Maximum results to return.
        
    Returns:
        List of result dictionaries.
    """
    # TODO: Import and use actual PostgresClient when available
    # from storage.postgres import PostgresClient
    # return await client.query_memory_items(tenant_id, query_params, limit)
    return []


async def query_weaviate(
    query: str,
    params: Dict[str, Any],
    tenant_id: str,
    limit: int
) -> List[Dict[str, Any]]:
    """Query Weaviate for semantic search.
    
    In production, this would use the actual WeaviateClient.
    Currently returns empty list as placeholder.
    
    Args:
        query: Search query string.
        params: Weaviate search parameters.
        tenant_id: Tenant identifier.
        limit: Maximum results to return.
        
    Returns:
        List of result dictionaries.
    """
    # TODO: Import and use actual WeaviateClient when available
    # from storage.weaviate_client import WeaviateClient
    # return await client.hybrid_search(query, params, tenant_id, limit)
    return []


async def query_neo4j(
    cypher_query: str,
    tenant_id: str,
    params: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Query Neo4j for graph traversal.
    
    In production, this would use the actual Neo4jClient.
    Currently returns empty list as placeholder.
    
    Args:
        cypher_query: Cypher query string.
        tenant_id: Tenant identifier.
        params: Additional query parameters.
        
    Returns:
        List of result dictionaries.
    """
    # TODO: Import and use actual Neo4jClient when available
    # from storage.neo4j_client import Neo4jClient
    # return await client.execute_query(cypher_query, tenant_id, params)
    return []


def _deduplicate_results(results: List[ResultItem]) -> List[ResultItem]:
    """Remove duplicate results based on content similarity.
    
    Uses simple exact match deduplication in this implementation.
    A more sophisticated approach would use semantic similarity.
    
    Args:
        results: List of ResultItems to deduplicate.
        
    Returns:
        Deduplicated list of results.
    """
    if not results:
        return []
    
    seen_content: Set[str] = set()
    deduped: List[ResultItem] = []
    
    # Sort by confidence to prefer higher confidence duplicates
    sorted_results = sorted(results, key=lambda x: x.confidence, reverse=True)
    
    for result in sorted_results:
        # Normalize content for comparison
        content_normalized = result.content.strip().lower()
        
        if content_normalized not in seen_content:
            seen_content.add(content_normalized)
            deduped.append(result)
    
    return deduped


def rerank_results(
    results: List[ResultItem],
    weights: Dict[str, float],
    limit: Optional[int] = None
) -> List[ResultItem]:
    """Rerank results based on weighted scoring.
    
    Args:
        results: List of results to rerank.
        weights: Dictionary of weights for scoring.
                 Supported: relevance, confidence, recency, graph_distance
        limit: Optional limit on number of results to return.
        
    Returns:
        Sorted list of results.
    """
    if not results:
        return []
    
    if not weights:
        weights = {"relevance": 1.0}
    
    # Normalize weights to sum to 1
    weight_sum = sum(weights.values())
    if weight_sum > 0:
        normalized_weights = {k: v / weight_sum for k, v in weights.items()}
    else:
        normalized_weights = {"relevance": 1.0}
    
    scored_results = []
    
    for result in results:
        score = 0.0
        
        # Apply relevance weight
        if "relevance" in normalized_weights:
            score += result.relevance * normalized_weights["relevance"]
        
        # Apply confidence weight
        if "confidence" in normalized_weights:
            score += result.confidence * normalized_weights["confidence"]
        
        # Apply recency weight
        if "recency" in normalized_weights:
            score += result.recency * normalized_weights["recency"]
        
        # Apply graph_distance weight (lower is better, so inverse)
        if "graph_distance" in normalized_weights and result.graph_distance is not None:
            # Invert: closer nodes (lower distance) should rank higher
            distance_score = max(0, 1.0 - result.graph_distance)
            score += distance_score * normalized_weights["graph_distance"]
        
        result.metadata["rerank_score"] = score
        scored_results.append((score, result))
    
    # Sort by score descending
    scored_results.sort(key=lambda x: x[0], reverse=True)
    
    # Extract results
    reranked = [r for _, r in scored_results]
    
    if limit:
        return reranked[:limit]
    
    return reranked


def assemble_evidence(
    results: List[ResultItem],
    include_provenance: bool = True
) -> str:
    """Assemble results into evidence string for LLM context.
    
    Args:
        results: List of result items.
        include_provenance: Whether to include provenance metadata.
        
    Returns:
        Formatted evidence string.
    """
    if not results:
        return ""
    
    evidence_parts = []
    
    for i, result in enumerate(results, 1):
        if include_provenance and result.provenance:
            # Format with provenance metadata
            source = result.provenance.get("source", result.source)
            conf = result.provenance.get("confidence", result.confidence)
            evidence_parts.append(
                f"[{i}. {source}, confidence={conf:.2f}] {result.content}"
            )
        elif include_provenance:
            # Use source field directly
            evidence_parts.append(
                f"[{i}. {result.source}, confidence={result.confidence:.2f}] {result.content}"
            )
        else:
            # Simple format without provenance
            evidence_parts.append(f"{i}. {result.content}")
    
    return "\n\n".join(evidence_parts)


async def retrieve(
    query: str,
    intent: Intent,
    tenant_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Execute policy-based retrieval across storage backends.
    
    Uses Reciprocal Rank Fusion (RRF) to combine results from multiple sources
    before applying intent-based weighting.
    
    Args:
        query: User query string.
        intent: Classified intent from IntentClassifier.
        tenant_id: Tenant identifier.
        limit: Maximum number of results to return.
        
    Returns:
        List of result dictionaries with metadata.
    """
    # Get retrieval plan for this intent
    plan = get_retrieval_plan(intent)
    
    # Collect results by source for RRF fusion
    results_by_source: Dict[str, List[Dict[str, Any]]] = {}
    
    # Execute PostgreSQL query if enabled
    if plan.use_postgres and plan.postgres_query:
        pg_results = await query_postgres(
            plan.postgres_query,
            tenant_id,
            limit
        )
        # Normalize and tag with source
        results_by_source["postgres"] = [
            {**_normalize_result(r, "postgres").to_dict(), "source": "postgres"}
            for r in pg_results
        ]
    
    # Execute Weaviate search if enabled
    if plan.use_weaviate and plan.weaviate_params:
        wv_results = await query_weaviate(
            query,
            plan.weaviate_params,
            tenant_id,
            limit
        )
        results_by_source["weaviate"] = [
            {**_normalize_result(r, "weaviate").to_dict(), "source": "weaviate"}
            for r in wv_results
        ]
    
    # Execute Neo4j query if enabled
    if plan.use_neo4j:
        if plan.cypher_query:
            neo_results = await query_neo4j(
                plan.cypher_query,
                tenant_id,
                {"query": query}
            )
        else:
            # Generate dynamic query based on intent
            neo_results = await _generate_neo4j_query(intent, query, tenant_id)
        
        results_by_source["neo4j"] = [
            {**_normalize_result(r, "neo4j").to_dict(), "source": "neo4j"}
            for r in neo_results
        ]
    
    # Check if we have multiple sources - use RRF if so
    active_sources = [s for s, r in results_by_source.items() if r]
    
    if len(active_sources) >= 2:
        # Use RRF for multi-source fusion
        fused_results = fuse_with_provenance(
            results_by_source,
            k=RRF_K_DEFAULT,
            limit=limit * 2  # Get more for re-ranking
        )
        
        # Apply intent-based weighting after RRF
        final_results = apply_rrf_then_weight(
            fused_results,
            plan.rerank_weights,
            limit=limit
        )
        
        # Add source information back
        for r in final_results:
            r["source"] = r.get("sources", ["unknown"])[0] if r.get("sources") else "unknown"
        
        return final_results
    
    # Single source or no results - use legacy weighted scoring
    all_results: List[ResultItem] = []
    for source, results in results_by_source.items():
        for r in results:
            all_results.append(_normalize_result(r, source))
    
    # Deduplicate results
    all_results = _deduplicate_results(all_results)
    
    # Rerank results (fallback for single source)
    all_results = rerank_results(all_results, plan.rerank_weights, limit=limit)
    
    return [r.to_dict() for r in all_results]


async def _generate_neo4j_query(
    intent: Intent,
    query: str,
    tenant_id: str
) -> List[Dict[str, Any]]:
    """Generate dynamic Neo4j query based on intent and query string.
    
    This is a placeholder for more sophisticated query generation.
    
    Args:
        intent: The classified intent.
        query: User query string.
        tenant_id: Tenant identifier.
        
    Returns:
        List of result dictionaries.
    """
    # For relationship queries, extract entity mentions and traverse
    # This is a simplified implementation
    return []


# Convenience function for synchronous access
def retrieve_sync(
    query: str,
    intent: Intent,
    tenant_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Synchronous wrapper for retrieve function.
    
    Args:
        query: User query string.
        intent: Classified intent from IntentClassifier.
        tenant_id: Tenant identifier.
        limit: Maximum number of results to return.
        
    Returns:
        List of result dictionaries with metadata.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(retrieve(query, intent, tenant_id, limit))


class ResultFusion:
    """Fuses results from multiple storage backends.
    
    This class wires the fusion layer to actual storage clients, allowing
    E2E retrieval from PostgreSQL, Weaviate, and Neo4j.
    """
    
    def __init__(
        self,
        config: Optional[OpenClawMemoryConfig] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self.config = config
        self._postgres: Optional[PostgresClient] = None
        self._weaviate: Optional[WeaviateClient] = None
        self._neo4j: Optional[Neo4jClient] = None
        self._embedding_service: Optional[EmbeddingService] = embedding_service
    
    async def initialize_embeddings(self):
        """Initialize the embedding service if configured."""
        if self._embedding_service and not await self._embedding_service.is_initialized():
            await self._embedding_service.initialize()
    
    async def initialize(
        self,
        postgres: Optional[PostgresClient] = None,
        weaviate: Optional[WeaviateClient] = None,
        neo4j: Optional[Neo4jClient] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """Initialize storage clients.
        
        Args:
            postgres: Optional PostgresClient instance
            weaviate: Optional WeaviateClient instance
            neo4j: Optional Neo4jClient instance
            embedding_service: Optional EmbeddingService instance
        """
        self._postgres = postgres
        self._weaviate = weaviate
        self._neo4j = neo4j
        
        # Set embedding service if provided
        if embedding_service:
            self._embedding_service = embedding_service
        
        # Initialize embedding service
        await self.initialize_embeddings()
        
        # Connect clients if provided but not connected
        if self._postgres and not hasattr(self._postgres, '_pool') or (hasattr(self._postgres, '_pool') and self._postgres._pool is None):
            await self._postgres.connect()
        if self._weaviate and not await self._weaviate.is_connected():
            await self._weaviate.connect()
        if self._neo4j and not await self._neo4j.is_connected():
            await self._neo4j.connect()
    
    async def close(self):
        """Close storage clients."""
        if self._postgres and hasattr(self._postgres, 'disconnect'):
            await self._postgres.disconnect()
        if self._weaviate and hasattr(self._weaviate, 'disconnect'):
            await self._weaviate.disconnect()
        if self._neo4j and hasattr(self._neo4j, 'disconnect'):
            await self._neo4j.disconnect()
    
    async def query_postgres(
        self,
        query: str,
        memory_class: Optional[str] = None,
        agent_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Query PostgreSQL for memories.
        
        Args:
            query: Search query (used for text search if supported)
            memory_class: Filter by memory class
            agent_id: Filter by agent ID
            tenant_id: Filter by tenant ID
            limit: Maximum results
            
        Returns:
            List of memory dictionaries
        """
        if not self._postgres:
            # Fallback to function-based query
            return await query_postgres(
                {"query": query, "memory_class": memory_class},
                tenant_id or "default",
                limit
            )
        
        try:
            # Use PostgresClient's query method
            sql = """
                SELECT id, content, memory_class, agent_id, visibility,
                       confidence, created_at, metadata
                FROM memory_items
                WHERE 1=1
            """
            params = []
            param_idx = 1
            
            if memory_class:
                sql += f" AND memory_class = ${param_idx}"
                params.append(memory_class)
                param_idx += 1
            
            if agent_id:
                sql += f" AND (agent_id = ${param_idx} OR visibility IN ('team', 'tenant', 'public'))"
                params.append(agent_id)
                param_idx += 1
            
            sql += f" ORDER BY created_at DESC LIMIT ${param_idx}"
            params.append(limit)
            
            results = await self._postgres.query(sql, params)
            return [dict(row) for row in results] if results else []
        except Exception as e:
            # Fallback to empty if query fails
            return []
    
    async def query_weaviate(
        self,
        query: str,
        alpha: float = 0.7,
        limit: int = 10,
        memory_class: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query Weaviate for semantic search.
        
        Args:
            query: Search query
            alpha: Hybrid search weight (0=BM25, 1=vector)
            limit: Maximum results
            memory_class: Optional filter by memory class
            tenant_id: Optional filter by tenant
            
        Returns:
            List of memory dictionaries
        """
        if not self._weaviate:
            # Fallback to function-based query
            return await query_weaviate(
                query,
                {"alpha": alpha, "collection": "MemoryChunk"},
                tenant_id or "default",
                limit
            )
        
        try:
            # Generate embedding for vector search (hybrid requires both text AND vector)
            query_vector = None
            if self._embedding_service and await self._embedding_service.is_initialized():
                query_vector = await self._embedding_service.generate_embedding(query)
            
            results = await self._weaviate.search_chunks_hybrid(
                query=query,
                query_vector=query_vector,
                memory_class=memory_class,
                limit=limit,
                alpha=alpha,
            )
            return results
        except Exception as e:
            # Fallback to empty if query fails
            return []
    
    async def query_neo4j(
        self,
        query: str,
        entity_type: Optional[str] = None,
        relationship_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Query Neo4j for relationship graph.
        
        Args:
            query: Search query (entity name to search for)
            entity_type: Filter by entity type
            relationship_type: Filter by relationship type
            limit: Maximum results
            
        Returns:
            List of entity dictionaries
        """
        if not self._neo4j:
            # Fallback to function-based query
            return await query_neo4j(
                query,
                "default",
                {"entity_type": entity_type}
            )
        
        try:
            # Build Cypher query
            cypher = """
                MATCH (e:Entity)
                WHERE e.name CONTAINS $query
                RETURN e.id as id, e.name as name, e.type as type, e.properties as properties
                LIMIT $limit
            """
            
            params = {"query": query, "limit": limit}
            if entity_type:
                cypher = cypher.replace("MATCH (e:Entity)", f"MATCH (e:Entity) WHERE e.type = $entity_type")
                params["entity_type"] = entity_type
            
            results = await self._neo4j.query(cypher, params)
            return [dict(record) for record in results] if results else []
        except Exception as e:
            # Fallback to empty if query fails
            return []
    
    async def fuse(
        self,
        raw_results: List[Dict[str, Any]],
        intent: Intent
    ) -> List[Dict[str, Any]]:
        """Fuse raw results from multiple backends.
        
        Args:
            raw_results: List of result dictionaries from retrieval
            intent: The classified intent for weighting
            
        Returns:
            Fused and deduplicated results
        """
        tracer = trace.get_tracer(__name__) if _OBSERVABILITY_AVAILABLE else None
        
        with tracer.start_as_current_span("rrf.fuse") if tracer else _FakeSpan() as span:
            if tracer:
                span.set_attribute("rrf.operation", "fuse")
                span.set_attribute("rrf.num_results", len(raw_results))
                span.set_attribute("rrf.intent", str(intent))
            
            start_time = time.perf_counter() if _OBSERVABILITY_AVAILABLE else 0
            
            # Get retrieval plan for intent-based weights
            plan = get_retrieval_plan(intent)
            weights = plan.rerank_weights
            
            # 1. Group results by source for RRF
            results_by_source = {}
            for res in raw_results:
                src = res.get("source", "unknown")
                if src not in results_by_source:
                    results_by_source[src] = []
                results_by_source[src].append(res)
            
            # 2. Apply Reciprocal Rank Fusion
            # This generates doc-level stats (rrf_score, source_count)
            fused_dicts = reciprocal_rank_fusion(
                list(results_by_source.values()),
                k=RRF_K_DEFAULT,
                limit=RRF_MAX_RESULTS
            )
            
            # 3. Convert to ResultItems and Normalize
            items = []
            for d in fused_dicts:
                item = _normalize_result(d, "fused")
                # Carry over RRF score into business logic
                item.score = d.get("rrf_score", 0.0)
                items.append(item)
            
            # 4. Apply Intent-based Reranking
            items = rerank_results(items, weights)
            
            result = [r.to_dict() for r in items]
            
            # Record metrics
            if _OBSERVABILITY_AVAILABLE:
                duration = time.perf_counter() - start_time
                
                if tracer and span:
                    span.set_attribute("rrf.result_count", len(result))
                    span.set_attribute("rrf.duration_ms", duration * 1000)
                    span.set_status(Status(StatusCode.OK))
                
                MetricsHelper.record_rrf_results(len(result))
                MetricsHelper.record_rrf_latency(duration)
            
            return result