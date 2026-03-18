"""Reciprocal Rank Fusion (RRF) for multi-source result fusion.

RRF combines ranked lists from multiple retrieval systems using the formula:
    RRF_score(d) = Σ 1/(k + rank_i(d)) for each ranking list i

Where:
- k is a constant (typically 60)
- rank_i(d) is the rank of document d in ranking list i
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import uuid

# Default RRF constant
DEFAULT_RRF_K = 60


@dataclass
class RRFResult:
    """A result item with RRF fusion metadata."""
    id: str
    content: str
    sources: List[str] = field(default_factory=list)  # Which sources contributed
    rrf_score: float = 0.0
    original_scores: Dict[str, float] = field(default_factory=dict)  # Original scores per source
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "content": self.content,
            "sources": self.sources,
            "rrf_score": self.rrf_score,
            "original_scores": self.original_scores,
            "metadata": self.metadata,
        }


def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    k: int = DEFAULT_RRF_K,
    limit: int = 10,
    id_field: str = "id",
    score_field: str = "score",
    content_field: str = "content"
) -> List[Dict[str, Any]]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion.
    
    Args:
        ranked_lists: List of ranked result lists from different sources.
                      Each list should be sorted by relevance (best first).
        k: RRF constant (default 60). Higher values give more weight to rank position.
        limit: Maximum number of results to return.
        id_field: Field name to use as document identifier.
        score_field: Field name for original relevance score.
        content_field: Field name for content/text.
                    
    Returns:
        Fused and re-ranked list of results with RRF scores.
        
    Example:
        >>> pg_results = [{"id": "a", "content": "doc a", "score": 0.9}]
        >>> wv_results = [{"id": "a", "content": "doc a", "score": 0.85}, {"id": "b", ...}]
        >>> neo_results = [{"id": "b", "content": "doc b", "score": 0.7}]
        >>> fused = reciprocal_rank_fusion([pg_results, wv_results, neo_results])
        >>> # doc "a" appears in both pg and wv, so gets higher RRF score
    """
    if not ranked_lists:
        return []
    
    # Filter out empty lists
    non_empty_lists = [lst for lst in ranked_lists if lst]
    
    if not non_empty_lists:
        return []
    
    # If only one list, just add rank-based score and return
    if len(non_empty_lists) == 1:
        return _rank_single_list(
            non_empty_lists[0], k, limit, id_field, score_field, content_field
        )
    
    # Build document index: doc_id -> {sources: [], rrf_score: 0}
    doc_index: Dict[str, RRFResult] = {}
    
    # Process each ranked list
    for source_idx, results in enumerate(non_empty_lists):
        source_name = f"source_{source_idx}"
        
        for rank, doc in enumerate(results, start=1):
            doc_id = doc.get(id_field) or str(uuid.uuid4())
            content = doc.get(content_field) or doc.get("text", "")
            
            # Initialize document if not seen before
            if doc_id not in doc_index:
                doc_index[doc_id] = RRFResult(
                    id=doc_id,
                    content=content,
                    sources=[],
                    original_scores={},
                    metadata=doc.get("metadata", {}),
                )
            
            rrf_result = doc_index[doc_id]
            
            # Track which source contributed
            if source_name not in rrf_result.sources:
                rrf_result.sources.append(source_name)
            
            # Store original score from this source
            original_score = doc.get(score_field, 0.5)
            rrf_result.original_scores[source_name] = original_score
            
            # Accumulate RRF score: 1 / (k + rank)
            # Rank is 1-indexed
            rrf_result.rrf_score += 1.0 / (k + rank)
    
    # Sort by RRF score descending
    sorted_results = sorted(
        doc_index.values(),
        key=lambda x: (x.rrf_score, x.id),  # Tie-break by id
        reverse=True
    )
    
    # Convert to output format
    output = []
    for rrf_result in sorted_results[:limit]:
        output.append({
            "id": rrf_result.id,
            "content": rrf_result.content,
            "rrf_score": rrf_result.rrf_score,
            "sources": rrf_result.sources,
            "original_scores": rrf_result.original_scores,
            "source_count": len(rrf_result.sources),
            "metadata": rrf_result.metadata,
        })
    
    return output


def _rank_single_list(
    results: List[Dict[str, Any]],
    k: int,
    limit: int,
    id_field: str,
    score_field: str,
    content_field: str
) -> List[Dict[str, Any]]:
    """Handle single list case - add synthetic RRF scores based on rank."""
    output = []
    
    for rank, doc in enumerate(results[:limit], start=1):
        doc_id = doc.get(id_field) or str(uuid.uuid4())
        content = doc.get(content_field) or doc.get("text", "")
        original_score = doc.get(score_field, 0.5)
        
        # For single list, use 1/(k+rank) as score
        rrf_score = 1.0 / (k + rank)
        
        output.append({
            "id": doc_id,
            "content": content,
            "rrf_score": rrf_score,
            "sources": ["single"],
            "original_scores": {"single": original_score},
            "source_count": 1,
            "metadata": doc.get("metadata", {}),
        })
    
    return output


def fuse_with_provenance(
    results_by_source: Dict[str, List[Dict[str, Any]]],
    k: int = DEFAULT_RRF_K,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Fuse results with explicit source labels.
    
    Args:
        results_by_source: Dictionary mapping source name to result list.
                           Example: {"postgres": [...], "weaviate": [...], "neo4j": [...]}
        k: RRF constant.
        limit: Maximum results.
        
    Returns:
        Fused results with provenance metadata.
    """
    # Convert dict to list format with source names
    ranked_lists: List[List[Dict[str, Any]]] = []
    source_names: List[str] = []
    
    for source_name, results in results_by_source.items():
        if results:
            # Add source name to each result for tracking
            for r in results:
                r["_source_name"] = source_name
            ranked_lists.append(results)
            source_names.append(source_name)
    
    if not ranked_lists:
        return []
    
    # Use custom source name tracking
    fused = reciprocal_rank_fusion(
        ranked_lists,
        k=k,
        limit=limit,
        id_field="id",
        score_field="score",
        content_field="content"
    )
    
    # Remap source indices to actual source names
    for item in fused:
        actual_sources = []
        for source_idx in item.get("sources", []):
            if source_idx.startswith("source_"):
                idx = int(source_idx.split("_")[1])
                if idx < len(source_names):
                    actual_sources.append(source_names[idx])
            else:
                actual_sources.append(source_idx)
        item["sources"] = actual_sources
    
    return fused


def apply_rrf_then_weight(
    fused_results: List[Dict[str, Any]],
    weights: Dict[str, float],
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Apply intent-based weighting after RRF fusion.
    
    Args:
        fused_results: Results from RRF fusion.
        weights: Dictionary of weights for additional scoring factors.
                 Supported: relevance, confidence, recency
        limit: Maximum results to return.
        
    Returns:
        Reweighted results.
    """
    if not fused_results:
        return []
    
    if not weights:
        weights = {"relevance": 1.0}
    
    # Normalize weights
    weight_sum = sum(weights.values())
    if weight_sum > 0:
        normalized_weights = {k: v / weight_sum for k, v in weights.items()}
    else:
        normalized_weights = {"relevance": 1.0}
    
    # Normalize RRF score to 0-1 range for combination
    max_rrf = max(r.get("rrf_score", 0) for r in fused_results) if fused_results else 1.0
    if max_rrf == 0:
        max_rrf = 1.0
    
    scored_results = []
    
    for result in fused_results:
        # Start with normalized RRF score
        combined_score = (result.get("rrf_score", 0) / max_rrf) * 0.5  # 50% weight to RRF
        
        # Add weighted factors
        metadata = result.get("metadata", {})
        
        if "relevance" in normalized_weights:
            relevance = metadata.get("relevance", result.get("original_scores", {}).get("score", 0.5))
            combined_score += relevance * normalized_weights["relevance"] * 0.2
        
        if "confidence" in normalized_weights:
            confidence = metadata.get("confidence", 0.5)
            combined_score += confidence * normalized_weights["confidence"] * 0.15
        
        if "recency" in normalized_weights:
            recency = metadata.get("recency", 0.5)
            combined_score += recency * normalized_weights["recency"] * 0.15
        
        result["combined_score"] = combined_score
        scored_results.append((combined_score, result))
    
    # Sort by combined score descending
    scored_results.sort(key=lambda x: (x[0], x[1].get("id", "")), reverse=True)
    
    return [r for _, r in scored_results[:limit]]