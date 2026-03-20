"""Prometheus metric exporter for BrainClaw Hybrid GraphRAG."""
import os
import time
import logging
import asyncio
from typing import Dict
from prometheus_client import start_http_server, Gauge, Histogram, Counter

# Configure logging
logger = logging.getLogger("brainclaw.observability.prometheus")

# Prometheus Metrics
BRAINCLAW_GRAPH_NODES = Gauge('brainclaw_graph_nodes_total', 'Total number of entities (nodes) in the graph')
BRAINCLAW_GRAPH_EDGES = Gauge('brainclaw_graph_edges_total', 'Total number of relationships (edges) in the graph')
BRAINCLAW_GRAPH_COMMUNITIES = Gauge('brainclaw_graph_communities_total', 'Total number of detected thematic communities')
BRAINCLAW_SYNC_LATENCY = Histogram('brainclaw_sync_latency_seconds', 'Average memory synchronization latency')
BRAINCLAW_RETRIEVAL_PRECISION = Gauge('brainclaw_retrieval_precision', 'Top-5 retrieval precision metric')
BRAINCLAW_CONTRADICTIONS_TOTAL = Counter('brainclaw_contradictions_detected_total', 'Total number of detected knowledge contradictions')

class BrainClawExporter:
    """Manages the collection and export of BrainClaw metrics."""
    def __init__(self, port: int = 9090):
        self.port = port
        self.running = False
        
    def start(self):
        """Starts the Prometheus HTTP server."""
        if not self.running:
            logger.info(f"Starting BrainClaw Prometheus Exporter on port {self.port}")
            start_http_server(self.port)
            self.running = True

    async def update_metrics(self, data: Dict):
        """Updates Gauges with current system values.
        
        Args:
            data: dict containing current 'nodes', 'edges', 'communities', 'precision'.
        """
        BRAINCLAW_GRAPH_NODES.set(data.get('nodes', 0))
        BRAINCLAW_GRAPH_EDGES.set(data.get('edges', 0))
        BRAINCLAW_GRAPH_COMMUNITIES.set(data.get('communities', 0))
        BRAINCLAW_RETRIEVAL_PRECISION.set(data.get('precision', 0.0))

    def record_sync_latency(self, duration: float):
        """Records a synchronization event duration."""
        BRAINCLAW_SYNC_LATENCY.observe(duration)

    def record_contradiction(self):
        """Increments the contradiction counter."""
        BRAINCLAW_CONTRADICTIONS_TOTAL.inc()

# Singleton instance
exporter = BrainClawExporter(port=int(os.environ.get("PROMETHEUS_PORT", 9090)))
