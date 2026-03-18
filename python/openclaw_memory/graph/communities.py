"""Community detection using Leiden algorithm.

This module implements community detection in the knowledge graph using
the Leiden algorithm, which is more accurate than Louvain for finding
community structure.

Based on the GraphRAG paper's approach to hierarchical community detection.
"""
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import json
import logging

# Try to import igraph and leidenalg
# These are optional dependencies - if not available, falls back to networkx
try:
    import igraph as ig
    import leidenalg as la
    _LEIDEN_AVAILABLE = True
except ImportError:
    _LEIDEN_AVAILABLE = False
    # Will use networkx fallback

try:
    import networkx as nx
    _NETWORKX_AVAILABLE = True
except ImportError:
    _NETWORKX_AVAILABLE = False

from ..storage.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


@dataclass
class Community:
    """Represents a detected community in the graph."""
    community_id: int
    node_ids: List[str]
    node_count: int
    internal_edges: int
    external_edges: int
    density: float
    tenant_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "community_id": self.community_id,
            "node_ids": self.node_ids,
            "node_count": self.node_count,
            "internal_edges": self.internal_edges,
            "external_edges": self.external_edges,
            "density": self.density,
            "tenant_id": self.tenant_id,
        }


@dataclass
class NodeCommunity:
    """Maps a node to its community."""
    node_id: str
    community_id: int
    tenant_id: Optional[str] = None


class CommunityDetector:
    """Detect communities in knowledge graph using Leiden algorithm.
    
    The Leiden algorithm is a community detection method that is more
    accurate than Louvain because it refines partitions after aggregation.
    
    This implementation:
    1. Extracts the graph from Neo4j
    2. Converts to igraph format
    3. Runs Leiden algorithm
    4. Stores community assignments back to Neo4j
    5. Provides methods for retrieving community members and summaries
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        resolution: float = 1.0,
    ):
        """Initialize community detector.
        
        Args:
            neo4j_client: Neo4j client for graph operations
            resolution: Resolution parameter for Leiden (higher = more communities)
        """
        self.neo4j = neo4j_client
        self.resolution = resolution
        self._community_cache: Dict[int, Community] = {}
        self._node_to_community: Dict[str, int] = {}

    async def detect_communities(
        self,
        tenant_id: Optional[str] = None,
        label: str = "Entity",
        min_community_size: int = 2,
    ) -> Dict[str, int]:
        """Detect communities using Leiden algorithm.
        
        Args:
            tenant_id: Optional tenant ID to scope detection
            label: Node label to extract from Neo4j
            min_community_size: Minimum nodes in a community
            
        Returns:
            Dict mapping node IDs to community IDs
        """
        # Extract graph from Neo4j
        graph_data = await self._extract_graph_from_neo4j(tenant_id, label)
        
        if not graph_data["nodes"]:
            logger.warning("No nodes found for community detection")
            return {}
        
        if len(graph_data["nodes"]) < min_community_size:
            logger.warning(f"Not enough nodes for community detection: {len(graph_data['nodes'])} < {min_community_size}")
            return {}
        
        # Run Leiden algorithm
        if _LEIDEN_AVAILABLE:
            community_mapping = await self._detect_leiden(graph_data)
        elif _NETWORKX_AVAILABLE:
            community_mapping = await self._detect_networkx_communities(graph_data)
        else:
            raise RuntimeError("Neither igraph/leidenalg nor networkx available")
        
        # Store community assignments in Neo4j
        await self._store_communities_in_neo4j(community_mapping, tenant_id)
        
        return community_mapping

    async def _extract_graph_from_neo4j(
        self,
        tenant_id: Optional[str] = None,
        label: str = "Entity",
    ) -> Dict[str, Any]:
        """Extract graph data from Neo4j.
        
        Args:
            tenant_id: Optional tenant filter
            label: Node label to extract
            
        Returns:
            Dict with 'nodes' and 'edges' lists
        """
        # Query for all nodes with the given label
        if tenant_id:
            node_query = f"""
                MATCH (n:{label})
                WHERE n.tenant_id = $tenant_id
                RETURN n.id as id, n.name as name, n.tenant_id as tenant_id
            """
            params = {"tenant_id": tenant_id}
        else:
            node_query = f"""
                MATCH (n:{label})
                RETURN n.id as id, n.name as name, n.tenant_id as tenant_id
            """
            params = {}

        async with self.neo4j._driver.session(database=self.neo4j.database) as session:
            result = await session.run(node_query, params)
            nodes = []
            async for record in result:
                nodes.append({
                    "id": record["id"],
                    "name": record["name"],
                    "tenant_id": record.get("tenant_id"),
                })
            
            # Get edges (relationships between entities)
            if tenant_id:
                edge_query = """
                    MATCH (a:Entity {tenant_id: $tenant_id})-[r]->(b:Entity {tenant_id: $tenant_id})
                    RETURN a.id as source, b.id as target, type(r) as type
                """
            else:
                edge_query = """
                    MATCH (a:Entity)-[r]->(b:Entity)
                    RETURN a.id as source, b.id as target, type(r) as type
                """
            
            result = await session.run(edge_query, params)
            edges = []
            async for record in result:
                edges.append({
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["type"],
                })

        # Build node name to ID mapping
        node_name_to_id = {n["name"]: n["id"] for n in nodes}
        
        return {
            "nodes": nodes,
            "edges": edges,
            "node_name_to_id": node_name_to_id,
        }

    async def _detect_leiden(
        self,
        graph_data: Dict[str, Any],
    ) -> Dict[str, int]:
        """Detect communities using igraph + leidenalg.
        
        Args:
            graph_data: Graph data from _extract_graph_from_neo4j
            
        Returns:
            Dict mapping node IDs to community IDs
        """
        nodes = graph_data["nodes"]
        edges = graph_data["edges"]
        
        # Create igraph Graph
        g = ig.Graph()
        
        # Add vertices
        node_indices = {node["id"]: i for i, node in enumerate(nodes)}
        g.add_vertices(len(nodes))
        
        for i, node in enumerate(nodes):
            g.vs[i]["id"] = node["id"]
            g.vs[i]["name"] = node["name"]
            if node.get("tenant_id"):
                g.vs[i]["tenant_id"] = node["tenant_id"]
        
        # Add edges
        valid_edges = []
        for edge in edges:
            source_idx = node_indices.get(edge["source"])
            target_idx = node_indices.get(edge["target"])
            if source_idx is not None and target_idx is not None:
                valid_edges.append((source_idx, target_idx))
        
        g.add_edges(valid_edges)
        
        # Run Leiden algorithm
        partition = la.find_partition(
            g,
            la.RBConfigurationVertexPartition,
            weights=None,
            resolution_parameter=self.resolution,
            seed=42,
        )
        
        # Map results
        community_mapping = {}
        for node in nodes:
            idx = node_indices[node["id"]]
            community_id = partition.membership[idx]
            community_mapping[node["id"]] = community_id
        
        self._node_to_community = community_mapping
        logger.info(f"Detected {len(set(community_mapping.values()))} communities using Leiden")
        
        return community_mapping

    async def _detect_networkx_communities(
        self,
        graph_data: Dict[str, Any],
    ) -> Dict[str, int]:
        """Detect communities using NetworkX (fallback when Leiden not available).
        
        Args:
            graph_data: Graph data from _extract_graph_from_neo4j
            
        Returns:
            Dict mapping node IDs to community IDs
        """
        # Build NetworkX graph
        G = nx.Graph()
        
        for node in graph_data["nodes"]:
            G.add_node(node["id"], name=node["name"], tenant_id=node.get("tenant_id"))
        
        for edge in graph_data["edges"]:
            if edge["source"] in G.nodes and edge["target"] in G.nodes:
                G.add_edge(edge["source"], edge["target"])
        
        # Use Louvain from networkx (closest available algorithm)
        try:
            from networkx.algorithms.community import louvain_communities
            communities = louvain_communities(G, resolution=self.resolution, seed=42)
        except ImportError:
            # Fall back to greedy modularity
            from networkx.algorithms.community import greedy_modularity_communities
            communities = greedy_modularity_communities(G)
        
        # Map communities
        community_mapping = {}
        for community_id, community in enumerate(communities):
            for node_id in community:
                community_mapping[node_id] = community_id
        
        self._node_to_community = community_mapping
        logger.info(f"Detected {len(communities)} communities using NetworkX")
        
        return community_mapping

    async def _store_communities_in_neo4j(
        self,
        community_mapping: Dict[str, int],
        tenant_id: Optional[str] = None,
    ) -> None:
        """Store community assignments in Neo4j.
        
        Args:
            community_mapping: Node ID to community ID mapping
            tenant_id: Optional tenant filter
        """
        # Merge community assignments as node properties
        for node_id, community_id in community_mapping.items():
            query = """
                MATCH (n:Entity {id: $node_id})
                SET n.community_id = $community_id
            """
            async with self.neo4j._driver.session(database=self.neo4j.database) as session:
                await session.run(
                    query,
                    node_id=node_id,
                    community_id=community_id,
                )

    async def get_community_nodes(
        self,
        community_id: int,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get all nodes in a community.
        
        Args:
            community_id: Community ID to retrieve
            tenant_id: Optional tenant filter
            
        Returns:
            List of node properties in the community
        """
        if tenant_id:
            query = """
                MATCH (n:Entity {tenant_id: $tenant_id, community_id: $community_id})
                RETURN n.id as id, n.name as name, n.entity_type as type, 
                       n.description as description, n.properties as properties
            """
            params = {"tenant_id": tenant_id, "community_id": community_id}
        else:
            query = """
                MATCH (n:Entity {community_id: $community_id})
                RETURN n.id as id, n.name as name, n.entity_type as type,
                       n.description as description, n.properties as properties
            """
            params = {"community_id": community_id}

        async with self.neo4j._driver.session(database=self.neo4j.database) as session:
            result = await session.run(query, params)
            nodes = []
            async for record in result:
                nodes.append({
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "description": record.get("description"),
                    "properties": record.get("properties", {}),
                })
        
        return nodes

    async def get_community_edges(
        self,
        community_id: int,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get all edges within a community.
        
        Args:
            community_id: Community ID
            tenant_id: Optional tenant filter
            
        Returns:
            List of relationships in the community
        """
        if tenant_id:
            query = """
                MATCH (a:Entity {tenant_id: $tenant_id, community_id: $community_id})-[r]->(b:Entity {tenant_id: $tenant_id, community_id: $community_id})
                RETURN a.id as source, b.id as target, type(r) as type, properties(r) as properties
            """
            params = {"tenant_id": tenant_id, "community_id": community_id}
        else:
            query = """
                MATCH (a:Entity {community_id: $community_id})-[r]->(b:Entity {community_id: $community_id})
                RETURN a.id as source, b.id as target, type(r) as type, properties(r) as properties
            """
            params = {"community_id": community_id}

        async with self.neo4j._driver.session(database=self.neo4j.database) as session:
            result = await session.run(query, params)
            edges = []
            async for record in result:
                edges.append({
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["type"],
                    "properties": record.get("properties", {}),
                })
        
        return edges

    async def get_community_subgraph(
        self,
        community_id: int,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get the complete subgraph for a community.
        
        Args:
            community_id: Community ID
            tenant_id: Optional tenant filter
            
        Returns:
            Dict with 'nodes' and 'edges' for the community
        """
        nodes = await self.get_community_nodes(community_id, tenant_id)
        edges = await self.get_community_edges(community_id, tenant_id)
        
        return {
            "community_id": community_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }

    async def get_community_summaries(
        self,
        community_id: int,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get summaries for a community from PostgreSQL.
        
        Args:
            community_id: Community ID
            tenant_id: Optional tenant filter
            
        Returns:
            List of summary records for this community
        """
        # This will be implemented in the summarize.py module
        # For now, return empty list - the CommunitySummarizer will populate this
        return []

    async def get_all_communities(
        self,
        tenant_id: Optional[str] = None,
    ) -> List[int]:
        """Get all community IDs.
        
        Args:
            tenant_id: Optional tenant filter
            
        Returns:
            List of unique community IDs
        """
        if tenant_id:
            query = """
                MATCH (n:Entity {tenant_id: $tenant_id})
                WHERE n.community_id IS NOT NULL
                RETURN DISTINCT n.community_id as community_id
                ORDER BY n.community_id
            """
            params = {"tenant_id": tenant_id}
        else:
            query = """
                MATCH (n:Entity)
                WHERE n.community_id IS NOT NULL
                RETURN DISTINCT n.community_id as community_id
                ORDER BY n.community_id
            """
            params = {}

        async with self.neo4j._driver.session(database=self.neo4j.database) as session:
            result = await session.run(query, params)
            communities = []
            async for record in result:
                communities.append(record["community_id"])
        
        return communities

    async def get_node_community(
        self,
        node_id: str,
    ) -> Optional[int]:
        """Get the community ID for a specific node.
        
        Args:
            node_id: Node ID to look up
            
        Returns:
            Community ID or None if not assigned
        """
        # Check cache first
        if node_id in self._node_to_community:
            return self._node_to_community[node_id]
        
        # Query from Neo4j
        query = """
            MATCH (n:Entity {id: $node_id})
            RETURN n.community_id as community_id
        """
        
        async with self.neo4j._driver.session(database=self.neo4j.database) as session:
            result = await session.run(query, node_id=node_id)
            record = await result.single()
            if record:
                community_id = record.get("community_id")
                if community_id is not None:
                    self._node_to_community[node_id] = community_id
                    return community_id
        return None

    async def get_community_stats(
        self,
        community_id: int,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get statistics for a community.
        
        Args:
            community_id: Community ID
            tenant_id: Optional tenant filter
            
        Returns:
            Dict with community statistics
        """
        nodes = await self.get_community_nodes(community_id, tenant_id)
        edges = await self.get_community_edges(community_id, tenant_id)
        
        node_count = len(nodes)
        edge_count = len(edges)
        
        # Calculate density (for simple graph: 2E / N(N-1))
        density = (2 * edge_count) / (node_count * (node_count - 1)) if node_count > 1 else 0
        
        # Count relationship types
        rel_types = {}
        for edge in edges:
            rel_type = edge["type"]
            rel_types[rel_type] = rel_types.get(rel_type, 0) + 1
        
        return {
            "community_id": community_id,
            "node_count": node_count,
            "edge_count": edge_count,
            "density": density,
            "relationship_types": rel_types,
        }