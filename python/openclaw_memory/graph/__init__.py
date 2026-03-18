"""Graph-based community detection and summarization.

This module provides:
- CommunityDetector: Leiden algorithm for community detection in Neo4j graph
- CommunitySummarizer: LLM-based summarization for communities

Based on the GraphRAG paper's approach to hierarchical community summarization.
"""

from .communities import CommunityDetector
from .summarize import CommunitySummarizer

__all__ = ["CommunityDetector", "CommunitySummarizer"]