"""Community summarization using LLM.

This module generates LLM-based summaries for communities detected
in the knowledge graph. Based on the GraphRAG paper's approach
to hierarchical community summarization.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import logging

from .communities import CommunityDetector

logger = logging.getLogger(__name__)


@dataclass
class CommunitySummary:
    """A summary for a community."""
    id: Optional[uuid.UUID] = None
    community_id: int = 0
    tenant_id: Optional[str] = None
    summary: str = ""
    full_context: str = ""
    node_count: int = 0
    edge_count: int = 0
    generation_method: str = "llm"
    llm_model: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for database storage."""
        return {
            "community_id": self.community_id,
            "tenant_id": self.tenant_id,
            "summary": self.summary,
            "full_context": self.full_context,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "generation_method": self.generation_method,
            "llm_model": self.llm_model,
        }


class CommunitySummarizer:
    """Generate LLM summaries for communities.
    
    This class takes communities detected by CommunityDetector and
    generates natural language summaries using an LLM. The summaries
    capture the key entities, relationships, and themes within each
    community.
    
    Summaries are stored in PostgreSQL and linked to community nodes
    in Neo4j.
    """

    def __init__(
        self,
        llm_client: Any,
        postgres: "PostgresClient",
        neo4j: "Neo4jClient",
        community_detector: Optional[CommunityDetector] = None,
    ):
        """Initialize community summarizer.
        
        Args:
            llm_client: LLM client for generating summaries (e.g., OpenAIClient, AnthropicClient)
            postgres: PostgreSQL client for storing summaries
            neo4j: Neo4j client for linking summaries
            community_detector: Optional community detector instance
        """
        self.llm = llm_client
        self.postgres = postgres
        self.neo4j = neo4j
        self.community_detector = community_detector

    def _format_community_context(
        self,
        community_id: int,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> str:
        """Format community data as context for LLM.
        
        Args:
            community_id: Community ID
            nodes: List of nodes in community
            edges: List of edges in community
            
        Returns:
            Formatted context string
        """
        # Format entities
        entity_lines = []
        for node in nodes:
            desc = node.get("description", "")
            entity_type = node.get("type", "Entity")
            entity_lines.append(f"- {node['name']} ({entity_type}): {desc}")
        
        entities_text = "\n".join(entity_lines) if entity_lines else "No entities found."
        
        # Format relationships
        rel_lines = []
        node_name_map = {n["id"]: n["name"] for n in nodes}
        
        for edge in edges:
            source_name = node_name_map.get(edge["source"], edge["source"])
            target_name = node_name_map.get(edge["target"], edge["target"])
            rel_type = edge["type"]
            rel_lines.append(f"- {source_name} --[{rel_type}]--> {target_name}")
        
        relationships_text = "\n".join(rel_lines) if rel_lines else "No relationships found."
        
        context = f"""Community {community_id} contains {len(nodes)} entities and {len(edges)} relationships:

## Entities:
{entities_text}

## Relationships:
{relationships_text}
"""
        return context

    def _create_summary_prompt(self, context: str) -> str:
        """Create prompt for LLM to generate summary.
        
        Args:
            context: Formatted community context
            
        Returns:
            Prompt string
        """
        return f"""You are an expert at analyzing knowledge graphs and summarizing communities of related concepts.

 Given the following community from a knowledge graph:

{context}

Please provide:
1. A brief summary (2-3 sentences) describing what this community represents
2. The key themes or topics covered
3. Important relationships between entities

Summary:"""

    async def summarize_community(
        self,
        community_id: int,
        tenant_id: Optional[str] = None,
        force_regenerate: bool = False,
    ) -> Optional[CommunitySummary]:
        """Generate summary for a community using LLM.
        
        Args:
            community_id: Community ID to summarize
            tenant_id: Optional tenant ID
            force_regenerate: Force regeneration even if summary exists
            
        Returns:
            CommunitySummary or None if generation fails
        """
        # Check if summary already exists
        if not force_regenerate:
            existing = await self.get_summary(community_id, tenant_id)
            if existing:
                logger.info(f"Using cached summary for community {community_id}")
                return existing
        
        # Get community data
        if self.community_detector:
            subgraph = await self.community_detector.get_community_subgraph(community_id, tenant_id)
            nodes = subgraph.get("nodes", [])
            edges = subgraph.get("edges", [])
        else:
            # Create temporary detector if not provided
            detector = CommunityDetector(self.neo4j)
            subgraph = await detector.get_community_subgraph(community_id, tenant_id)
            nodes = subgraph.get("nodes", [])
            edges = subgraph.get("edges", [])
        
        if not nodes:
            logger.warning(f"No nodes found for community {community_id}")
            return None
        
        # Format context
        context = self._format_community_context(community_id, nodes, edges)
        
        # Generate summary with LLM
        try:
            summary_text = await self._generate_summary_with_llm(context)
        except Exception as e:
            logger.error(f"LLM summary generation failed: {e}")
            # Fall back to template summary
            summary_text = self._generate_template_summary(nodes, edges)
        
        # Create summary object
        summary = CommunitySummary(
            community_id=community_id,
            tenant_id=tenant_id,
            summary=summary_text,
            full_context=context,
            node_count=len(nodes),
            edge_count=len(edges),
            generation_method="llm",
            llm_model=getattr(self.llm, "model", None),
        )
        
        # Store in PostgreSQL
        stored_summary = await self._store_summary(summary)
        
        # Link in Neo4j
        await self._link_summary_to_community(community_id, stored_summary.id, tenant_id)
        
        return stored_summary

    async def _generate_summary_with_llm(self, context: str) -> str:
        """Generate summary using LLM client.
        
        Args:
            context: Formatted community context
            
        Returns:
            Generated summary text
        """
        prompt = self._create_summary_prompt(context)
        
        # Call LLM - adapts to different LLM client interfaces
        if hasattr(self.llm, "generate"):
            # OpenAI-style client
            response = await self.llm.generate(prompt, max_tokens=500)
            if isinstance(response, dict):
                return response.get("content", response.get("text", str(response)))
            return response
        elif hasattr(self.llm, "complete"):
            # Anthropic-style client
            response = await self.llm.complete(prompt, max_tokens_to_sample=500)
            return response.completion
        elif hasattr(self.llm, "chat"):
            # Generic chat client
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            if isinstance(response, dict):
                return response.get("content", response.get("message", {}).get("content", str(response)))
            return str(response)
        else:
            raise ValueError(f"Unsupported LLM client: {type(self.llm)}")

    def _generate_template_summary(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> str:
        """Generate a template-based summary when LLM is unavailable.
        
        Args:
            nodes: Nodes in community
            edges: Edges in community
            
        Returns:
            Template summary text
        """
        node_names = [n["name"] for n in nodes[:5]]
        entity_types = list(set(n.get("type", "Entity") for n in nodes))
        
        summary = f"Community contains {len(nodes)} entities including {', '.join(node_names)}."
        
        if entity_types:
            summary += f" Entity types: {', '.join(entity_types)}."
        
        if edges:
            summary += f" Connected by {len(edges)} relationships."
        
        return summary

    async def _store_summary(
        self,
        summary: CommunitySummary,
    ) -> CommunitySummary:
        """Store summary in PostgreSQL.
        
        Args:
            summary: CommunitySummary to store
            
        Returns:
            Stored summary with ID
        """
        summary.id = uuid.uuid4()
        
        query = """
            INSERT INTO community_summaries (
                id, community_id, tenant_id, summary, full_context,
                node_count, edge_count, generation_method, llm_model
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (community_id, tenant_id) 
            DO UPDATE SET 
                summary = EXCLUDED.summary,
                full_context = EXCLUDED.full_context,
                node_count = EXCLUDED.node_count,
                edge_count = EXCLUDED.edge_count,
                generation_method = EXCLUDED.generation_method,
                llm_model = EXCLUDED.llm_model,
                updated_at = NOW()
            RETURNING *
        """
        
        async with self.postgres._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                summary.id,
                summary.community_id,
                summary.tenant_id,
                summary.summary,
                summary.full_context,
                summary.node_count,
                summary.edge_count,
                summary.generation_method,
                summary.llm_model,
            )
        
        return summary

    async def _link_summary_to_community(
        self,
        community_id: int,
        summary_id: uuid.UUID,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Link summary to community in Neo4j.
        
        Args:
            community_id: Community ID
            summary_id: Summary ID from PostgreSQL
            tenant_id: Optional tenant ID
        """
        # First create SUMMARIZES relationship from community to summary
        # Since we don't have a summary node, we store the summary_id as property
        
        if tenant_id:
            query = """
                MATCH (n:Entity {tenant_id: $tenant_id, community_id: $community_id})
                LIMIT 1
                SET n.summary_id = $summary_id
            """
        else:
            query = """
                MATCH (n:Entity {community_id: $community_id})
                LIMIT 1
                SET n.summary_id = $summary_id
            """
        
        async with self.neo4j._driver.session(database=self.neo4j.database) as session:
            await session.run(
                query,
                community_id=community_id,
                summary_id=str(summary_id),
                tenant_id=tenant_id,
            )

    async def get_summary(
        self,
        community_id: int,
        tenant_id: Optional[str] = None,
    ) -> Optional[CommunitySummary]:
        """Get existing summary for a community.
        
        Args:
            community_id: Community ID
            tenant_id: Optional tenant ID
            
        Returns:
            CommunitySummary or None if not found
        """
        if tenant_id:
            query = """
                SELECT * FROM community_summaries
                WHERE community_id = $1 AND tenant_id = $2
            """
            params = (community_id, tenant_id)
        else:
            query = """
                SELECT * FROM community_summaries
                WHERE community_id = $1 AND tenant_id IS NULL
            """
            params = (community_id,)
        
        async with self.postgres._pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
        
        if row:
            return CommunitySummary(
                id=row["id"],
                community_id=row["community_id"],
                tenant_id=row["tenant_id"],
                summary=row["summary"],
                full_context=row["full_context"],
                node_count=row["node_count"],
                edge_count=row["edge_count"],
                generation_method=row["generation_method"],
                llm_model=row["llm_model"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        
        return None

    async def summarize_all_communities(
        self,
        tenant_id: Optional[str] = None,
        min_nodes: int = 2,
    ) -> List[CommunitySummary]:
        """Summarize all communities for a tenant.
        
        Args:
            tenant_id: Optional tenant ID
            min_nodes: Minimum nodes to generate summary
            
        Returns:
            List of generated summaries
        """
        if not self.community_detector:
            self.community_detector = CommunityDetector(self.neo4j)
        
        communities = await self.community_detector.get_all_communities(tenant_id)
        summaries = []
        
        for community_id in communities:
            stats = await self.community_detector.get_community_stats(community_id, tenant_id)
            
            if stats["node_count"] >= min_nodes:
                summary = await self.summarize_community(community_id, tenant_id)
                if summary:
                    summaries.append(summary)
        
        logger.info(f"Generated summaries for {len(summaries)} communities")
        return summaries

    async def search_communities_by_relevance(
        self,
        query: str,
        embedding: Optional[List[float]] = None,
        tenant_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search communities by relevance to query.
        
        Uses vector similarity on community summaries to find
        communities most relevant to a query.
        
        Args:
            query: Search query
            embedding: Pre-computed query embedding (optional)
            tenant_id: Optional tenant filter
            limit: Maximum results
            
        Returns:
            List of communities with relevance scores
        """
        # If embedding not provided, generate it
        if not embedding:
            if hasattr(self, "embedding_service") and self.embedding_service:
                embedding = await self.embedding_service.generate_embedding(query)
            else:
                # Fall back to text search
                return await self._text_search_communities(query, tenant_id, limit)
        
        # Vector search on summaries
        query_sql = """
            SELECT community_id, summary, 
                   (summary_embedding <=> $1) as distance
            FROM community_summaries
            WHERE $2 IS NULL OR tenant_id = $2
            ORDER BY summary_embedding <=> $1
            LIMIT $3
        """
        
        async with self.postgres._pool.acquire() as conn:
            rows = await conn.fetch(query_sql, embedding, tenant_id, limit)
        
        results = []
        for row in rows:
            results.append({
                "community_id": row["community_id"],
                "summary": row["summary"],
                "relevance_score": 1 - row["distance"],  # Convert distance to similarity
            })
        
        return results

    async def _text_search_communities(
        self,
        query: str,
        tenant_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Fallback text search for communities.
        
        Args:
            query: Search query
            tenant_id: Optional tenant filter
            limit: Maximum results
            
        Returns:
            List of communities matching query
        """
        if tenant_id:
            query_sql = """
                SELECT community_id, summary
                FROM community_summaries
                WHERE tenant_id = $1
                AND summary ILIKE $2
                LIMIT $3
            """
            rows = await self.postgres._pool.fetch(query_sql, tenant_id, f"%{query}%", limit)
        else:
            query_sql = """
                SELECT community_id, summary
                FROM community_summaries
                WHERE summary ILIKE $1
                LIMIT $2
            """
            rows = await self.postgres._pool.fetch(query_sql, f"%{query}%", limit)
        
        return [{"community_id": r["community_id"], "summary": r["summary"]} for r in rows]


# Type hint for PostgresClient to avoid circular import
from ..storage.postgres import PostgresClient

def summarize_all(tenant_id=None, **kwargs):
    """Module-level entry point called by the TypeScript bridge.
    Returns existing community summaries from PostgreSQL (no LLM call)."""
    import os, psycopg2, psycopg2.extras
    url = os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL") or os.getenv("DATABASE_URL")
    if not url:
        return {"status": "no_db", "summaries": [], "total": 0}
    try:
        conn = psycopg2.connect(url)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if tenant_id:
            cur.execute("SELECT community_id, tenant_id, summary, node_count, edge_count FROM community_summaries WHERE tenant_id = %s ORDER BY community_id", (tenant_id,))
        else:
            cur.execute("SELECT community_id, tenant_id, summary, node_count, edge_count FROM community_summaries ORDER BY community_id")
        rows = cur.fetchall(); conn.close()
        return {"status": "ok", "summaries": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        return {"status": "error", "error": str(e), "summaries": [], "total": 0}
