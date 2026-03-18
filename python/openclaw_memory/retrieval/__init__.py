"""Retrieval module for BrainClaw Memory System.

This package provides intent classification, policy-based retrieval routing,
and result fusion across PostgreSQL, Weaviate, and Neo4j storage backends.

Key Components:
- intent: Intent classification for user queries
- policy: Retrieval plans mapping intents to storage backends
- fusion: Result retrieval, deduplication, reranking, and evidence assembly
"""
from .intent import (
    Intent,
    IntentClassifier,
    ClassificationResult,
    classify,
    classify_multiple,
)

from .policy import (
    RetrievalPlan,
    RETRIEVAL_PLANS,
    get_retrieval_plan,
    get_rerank_weights,
    get_enabled_stores,
)

from .fusion import (
    retrieve,
    retrieve_sync,
    rerank_results,
    assemble_evidence,
    ResultItem,
    query_postgres,
    query_weaviate,
    query_neo4j,
)

__all__ = [
    # Intent
    "Intent",
    "IntentClassifier", 
    "ClassificationResult",
    "classify",
    "classify_multiple",
    # Policy
    "RetrievalPlan",
    "RETRIEVAL_PLANS",
    "get_retrieval_plan",
    "get_rerank_weights",
    "get_enabled_stores",
    # Fusion
    "retrieve",
    "retrieve_sync",
    "rerank_results",
    "assemble_evidence",
    "ResultItem",
    "query_postgres",
    "query_weaviate",
    "query_neo4j",
]

__version__ = "0.1.0"