"""Retrieval policy module for BrainClaw Memory System.

This module defines retrieval plans that map intents to appropriate
storage backends (PostgreSQL, Weaviate, Neo4j) and reranking strategies.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from .intent import Intent


@dataclass
class RetrievalPlan:
    """Defines how to retrieve results for a specific intent.
    
    Attributes:
        use_postgres: Whether to use PostgreSQL for this intent.
        use_weaviate: Whether to use Weaviate for this intent.
        use_neo4j: Whether to use Neo4j for this intent.
        postgres_query: Query parameters for PostgreSQL retrieval.
        weaviate_params: Search parameters for Weaviate.
        cypher_query: Cypher query for Neo4j graph traversal.
        rerank_weights: Weights for result reranking.
    """
    use_postgres: bool = False
    use_weaviate: bool = False
    use_neo4j: bool = False
    postgres_query: Optional[Dict[str, Any]] = None
    weaviate_params: Optional[Dict[str, Any]] = None
    cypher_query: Optional[str] = None
    rerank_weights: Dict[str, float] = field(default_factory=dict)
    
    # Store client references for execution
    _postgres: Any = field(default=None, repr=False)
    _weaviate: Any = field(default=None, repr=False)
    _neo4j: Any = field(default=None, repr=False)

    async def execute(self) -> List[Dict[str, Any]]:
        """Execute the retrieval plan across all enabled stores.
        
        Returns:
            Flat list of results from all sources.
        """
        results = []
        
        # 1. Query Postgres (Vector/Semantic fallback or relational)
        if self.use_postgres and self._postgres:
            pg_res = await self._postgres.query(
                self.postgres_query.get("query", ""),
                limit=self.postgres_query.get("limit", 10)
            )
            for r in pg_res:
                r["source"] = "postgres"
                results.append(r)
                
        # 2. Query Weaviate (Hybrid Search)
        if self.use_weaviate and self._weaviate:
            wv_res = await self._weaviate.search_chunks_hybrid(
                query=self.weaviate_params.get("query", ""),
                alpha=self.weaviate_params.get("alpha", 0.7),
                limit=self.weaviate_params.get("limit", 10)
            )
            for r in wv_res:
                r["source"] = "weaviate"
                results.append(r)
                
        # 3. Query Neo4j (Graph Traversal)
        if self.use_neo4j and self._neo4j:
            neo_res = await self._neo4j.query(
                self.cypher_query or "",
                {"query": self.weaviate_params.get("query", "") if self.weaviate_params else ""}
            )
            for r in neo_res:
                r["source"] = "neo4j"
                results.append(r)
                
        return results


# Retrieval plans based on spec
RETRIEVAL_PLANS: Dict[Intent, RetrievalPlan] = {
    Intent.FACT_LOOKUP: RetrievalPlan(
        use_postgres=True,  # Fallback
        use_weaviate=True,  # Primary - semantic search
        use_neo4j=False,
        postgres_query={
            "table": "memory_items",
            "memory_class": "semantic",
            "fallback": True
        },
        weaviate_params={
            "collection": "MemoryChunk",
            "hybrid": True,
            "alpha": 0.7,
            "properties": ["content", "memory_type"]
        },
        cypher_query=None,
        rerank_weights={
            "relevance": 0.6,
            "confidence": 0.3,
            "recency": 0.1
        }
    ),
    
    Intent.DECISION_RECALL: RetrievalPlan(
        use_postgres=True,  # Primary - canonical decision memories
        use_weaviate=False,
        use_neo4j=True,  # Graph traversal for decisions
        postgres_query={
            "table": "memory_items",
            "memory_class": "decision",
            "is_current": True,
            "status": "accepted",
            "order_by": "created_at",
            "order_desc": True
        },
        weaviate_params=None,
        cypher_query="""
            MATCH (d:Decision)
            WHERE d.status IN ['accepted', 'active'] AND coalesce(d.is_current, true) = true
            OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(e)
            OPTIONAL MATCH (d)-[:DECIDED_ABOUT]->(entity)
            OPTIONAL MATCH (d)<-[:DECIDED_BY]-(u:User)
            RETURN d, e, entity, u
            ORDER BY d.created_at DESC
            LIMIT 50
        """,
        rerank_weights={
            "relevance": 0.4,
            "confidence": 0.4,
            "recency": 0.2
        }
    ),
    
    Intent.RELATIONSHIP_QUERY: RetrievalPlan(
        use_postgres=False,
        use_weaviate=True,  # Semantic expansion
        use_neo4j=True,  # Primary - graph traversal
        postgres_query=None,
        weaviate_params={
            "collection": "Entity",
            "semantic": True,
            "properties": ["name", "description", "aliases"]
        },
        cypher_query=None,  # Generated dynamically based on query entities
        rerank_weights={
            "relevance": 0.3,
            "graph_distance": 0.4,
            "confidence": 0.3
        }
    ),
    
    Intent.CHANGE_DETECTION: RetrievalPlan(
        use_postgres=True,  # Primary - temporal diff
        use_weaviate=False,
        use_neo4j=True,  # SUPERSEDES edges for change tracking
        postgres_query={
            "table": "memory_items",
            "order_by": "updated_at",
            "order_desc": True,
            "include_superseded": True
        },
        weaviate_params=None,
        cypher_query="""
            MATCH (old:MemoryItem)-[:SUPERSEDES]->(new:MemoryItem)
            RETURN old, new
            ORDER BY new.updated_at DESC
        """,
        rerank_weights={
            "relevance": 0.4,
            "recency": 0.4,
            "confidence": 0.2
        }
    ),
    
    Intent.OWNERSHIP_QUERY: RetrievalPlan(
        use_postgres=False,
        use_weaviate=True,  # Context expansion
        use_neo4j=True,  # Primary - relationship queries
        postgres_query=None,
        weaviate_params={
            "collection": "MemoryChunk",
            "semantic": True,
            "properties": ["content"]
        },
        cypher_query="""
            MATCH (e:Entity)
            WHERE e.name CONTAINS $query OR e.canonical_name CONTAINS $query
            OPTIONAL MATCH (e)<-[:ASSIGNED_TO]-(u:User)
            OPTIONAL MATCH (e)<-[:DECIDED_BY]-(u2:User)
            OPTIONAL MATCH (e)<-[:CREATED]-(a:Agent)
            OPTIONAL MATCH (e)-[:MENTIONS]->(other:Entity)
            RETURN e, u, a, other
            LIMIT 20
        """,
        rerank_weights={
            "relevance": 0.4,
            "confidence": 0.3,
            "graph_distance": 0.3
        }
    ),
    
    Intent.PROCEDURAL_RECALL: RetrievalPlan(
        use_postgres=True,  # Primary - workflow/procedures
        use_weaviate=True,  # Semantic search for procedures
        use_neo4j=False,
        postgres_query={
            "table": "memory_items",
            "memory_class": "procedural",
            "order_by": "created_at",
            "order_desc": True
        },
        weaviate_params={
            "collection": "MemoryChunk",
            "hybrid": True,
            "alpha": 0.6,
            "properties": ["content"],
            "filters": {"memory_class": "procedural"}
        },
        cypher_query=None,
        rerank_weights={
            "relevance": 0.5,
            "confidence": 0.3,
            "recency": 0.2
        }
    ),
}


def get_retrieval_plan(intent: Intent) -> RetrievalPlan:
    """Get the retrieval plan for a given intent.
    
    Args:
        intent: The classified intent.
        
    Returns:
        RetrievalPlan defining how to retrieve results.
        
    Raises:
        KeyError: If intent is not recognize
    """
    if intent not in RETRIEVAL_PLANS:
        # Default to fact_lookup plan for unknown intents
        return RETRIEVAL_PLANS[Intent.FACT_LOOKUP]
    return RETRIEVAL_PLANS[intent]


def get_rerank_weights(intent: Intent) -> Dict[str, float]:
    """Get reranking weights for a given intent.
    
    Args:
        intent: The classified intent.
        
    Returns:
        Dictionary of rerank weights.
    """
    plan = get_retrieval_plan(intent)
    return plan.rerank_weights


def get_enabled_stores(intent: Intent) -> Dict[str, bool]:
    """Get which stores are enabled for a given intent.
    
    Args:
        intent: The classified intent.
        
    Returns:
        Dictionary with store enablement flags.
    """
    plan = get_retrieval_plan(intent)
    return {
        "postgres": plan.use_postgres,
        "weaviate": plan.use_weaviate,
        "neo4j": plan.use_neo4j
    }


class RetrievalPolicy:
    """Retrieval policy that determines how to retrieve results for intents.
    
    This class wraps the retrieval plan functions to provide a consistent
    interface for the OpenClawMemoryClient.
    """
    
    def __init__(
        self,
        postgres_client=None,
        weaviate_client=None,
        neo4j_client=None
    ):
        """Initialize retrieval policy with storage clients.
        
        Args:
            postgres_client: Optional PostgresClient instance
            weaviate_client: Optional WeaviateClient instance
            neo4j_client: Optional Neo4jClient instance
        """
        self.postgres = postgres_client
        self.weaviate = weaviate_client
        self.neo4j = neo4j_client
    
    def plan(self, intent: Intent, query: str) -> RetrievalPlan:
        """Get the retrieval plan for a given intent and query.
        
        Args:
            intent: The classified intent
            query: The search query string
            
        Returns:
            RetrievalPlan defining how to retrieve results
        """
        plan = get_retrieval_plan(intent)
        
        # Inject client references into the plan
        plan._postgres = self.postgres
        plan._weaviate = self.weaviate
        plan._neo4j = self.neo4j
        
        # Inject query into params
        if plan.postgres_query:
            plan.postgres_query["query"] = query
        if plan.weaviate_params:
            plan.weaviate_params["query"] = query
            
        return plan
