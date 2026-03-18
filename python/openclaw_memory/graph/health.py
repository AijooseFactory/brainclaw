"""Graph health statistics for BrainClaw.

Called synchronously by the TypeScript bridge via:
    from openclaw_memory.graph.health import get_health_stats
"""
import os
import logging

logger = logging.getLogger(__name__)


def get_health_stats(tenant_id: str = None, **kwargs) -> dict:
    """Return health statistics for the Neo4j knowledge graph.

    Reads NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE from env.
    Fails gracefully if Neo4j is unreachable (returns degraded status).
    """
    neo4j_url = os.getenv("NEO4J_URL", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    neo4j_database = os.getenv("NEO4J_DATABASE", "neo4j")

    stats = {
        "status": "unknown",
        "neo4j_url": neo4j_url,
        "neo4j_database": neo4j_database,
        "node_count": 0,
        "edge_count": 0,
        "community_count": 0,
        "tenant_id": tenant_id,
    }

    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(neo4j_url, auth=(neo4j_user, neo4j_password))
        with driver.session(database=neo4j_database) as session:
            stats["node_count"] = session.run(
                "MATCH (n) RETURN count(n) AS cnt"
            ).single()["cnt"]

            stats["edge_count"] = session.run(
                "MATCH ()-[r]->() RETURN count(r) AS cnt"
            ).single()["cnt"]

            stats["community_count"] = session.run(
                "MATCH (n) WHERE n.community_id IS NOT NULL "
                "RETURN count(DISTINCT n.community_id) AS cnt"
            ).single()["cnt"]

            stats["status"] = "healthy"
        driver.close()

    except Exception as e:
        logger.warning("Neo4j health check failed: %s", e)
        stats["status"] = "degraded"
        stats["error"] = str(e)

    return stats
