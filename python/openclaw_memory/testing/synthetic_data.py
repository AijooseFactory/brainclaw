"""
Synthetic Data Generators for BrainClaw Testing.

This module provides public-facing synthetic data generation functions
for E2E testing of the BrainClaw memory system.

Usage:
    from openclaw_memory.testing import (
        generate_synthetic_documents,
        generate_contradictory_documents,
        generate_entity_rich_documents,
        SyntheticDataConfig,
    )

    # Generate 10 standard synthetic documents
    docs = generate_synthetic_documents(10)

    # Generate with custom config
    config = SyntheticDataConfig(seed=42, min_entities=3, max_entities=10)
    docs = generate_entity_rich_documents(20, config=config)
"""

import random
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4


# Entity and relationship templates for generation
PERSON_NAMES = [
    "Alice Chen", "Bob Martinez", "Carol Williams", "David Kim", "Emma Johnson",
    "Frank Brown", "Grace Lee", "Henry Davis", "Ivy Wilson", "Jack Taylor",
]

PROJECT_NAMES = [
    "Phoenix", "Aurora", "Orion", "Nebula", "Horizon", "Spectrum", "Vertex",
    "Quantum", "Apex", "Nova", "Echo", "Fusion", "Prism", "Titan", "Zenith",
]

TECHNOLOGIES = [
    "Python", "TypeScript", "Rust", "Go", "Kubernetes", "PostgreSQL",
    "Redis", "RabbitMQ", "Elasticsearch", "Docker", "TensorFlow", "GraphQL",
    "gRPC", "WebSocket", "MongoDB", "React", "Vue.js", "FastAPI", "Django",
]

TOPICS = [
    "machine learning", "data pipelines", "authentication", "caching",
    "microservices", "API design", "database optimization", "CI/CD",
    "observability", "security", "performance", "scalability",
    "error handling", "testing", "documentation", "deployment",
]

ACTIONS = [
    "developed", "implemented", "designed", "analyzed", "optimized",
    "refactored", "documented", "deployed", "tested", "reviewed",
    "architected", "researched", "debugged", "maintained", "upgraded",
]

# Contradictory statement pairs for contradiction testing
CONTRADICTORY_PAIRS = [
    ("The system uses synchronous processing for all requests.", 
     "The system uses asynchronous processing for all requests."),
    ("All data is stored in a single database.",
     "Data is distributed across multiple databases."),
    ("The API has a rate limit of 100 requests per second.",
     "The API has a rate limit of 1000 requests per second."),
    ("Authentication is handled via JWT tokens.",
     "Authentication is handled via OAuth2 only."),
    ("The cache has a TTL of 5 minutes.",
     "The cache has a TTL of 60 minutes."),
    ("All services communicates via REST API.",
     "All services communicate via gRPC."),
    ("The system uses eventual consistency.",
     "The system uses strong consistency."),
    ("Database writes are synchronous.",
     "Database writes are asynchronous."),
]


def _generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid4())


def _random_timestamp(days_back: int = 30) -> str:
    """Generate a random timestamp within the past N days."""
    offset = random.randint(0, days_back * 24 * 60)
    ts = datetime.utcnow() - timedelta(minutes=offset)
    return ts.isoformat() + "Z"


@dataclass
class SyntheticDataConfig:
    """
    Configuration for synthetic data generation.
    
    Attributes:
        seed: Random seed for reproducibility.
        min_entities: Minimum number of entities per document.
        max_entities: Maximum number of entities per document.
        min_content_length: Minimum content length in characters.
        max_content_length: Maximum content length in characters.
    """
    seed: Optional[int] = None
    min_entities: int = 1
    max_entities: int = 5
    min_content_length: int = 100
    max_content_length: int = 800
    include_embeddings: bool = False  # Embeddings require actual vectorization
    
    def __post_init__(self):
        if self.seed is not None:
            random.seed(self.seed)
        if self.min_entities > self.max_entities:
            self.min_entities = self.max_entities
        if self.min_content_length > self.max_content_length:
            self.min_content_length = self.max_content_length


def _generate_content(
    topics: List[str],
    actions: List[str],
    technologies: List[str],
    names: List[str],
    config: SyntheticDataConfig,
) -> str:
    """Generate content for a synthetic document."""
    num_topics = random.randint(1, 3)
    selected_topics = random.sample(topics, min(num_topics, len(topics)))
    
    action = random.choice(actions)
    tech = random.choice(technologies)
    name = random.choice(names)
    
    templates = [
        f"{name} {action} a new {tech} system for {selected_topics[0]}.",
        f"Research on {selected_topics[0]} was completed using {tech} by {name}.",
        f"The {tech} implementation for {selected_topics[0]} was {action} by the team.",
        f"{name} analyzed the {tech} pipeline for {selected_topics[0]} optimization.",
        f"A {tech} solution for {selected_topics[0]} was {action} last week.",
    ]
    
    content = random.choice(templates)
    
    if len(selected_topics) > 1:
        content += f" This relates to {', '.join(selected_topics[1:])}."
    
    # Add more context to meet min length
    while len(content) < config.min_content_length:
        extra = f" The project also involves {random.choice(topics)}."
        content += extra
    
    # Trim to max length
    if len(content) > config.max_content_length:
        content = content[:config.max_content_length - 3] + "..."
    
    return content


def _extract_entities_from_content(content: str) -> List[Dict[str, str]]:
    """Simple entity extraction from content (for entity-rich docs)."""
    entities = []
    
    for name in PERSON_NAMES:
        if name.split()[0] in content or name.split()[-1] in content:
            entities.append({"name": name, "type": "person"})
    
    for tech in TECHNOLOGIES:
        if tech.lower() in content.lower():
            entities.append({"name": tech, "type": "technology"})
    
    for topic in TOPICS:
        if topic in content.lower():
            entities.append({"name": topic, "type": "topic"})
    
    return entities[:10]  # Limit to 10 entities


def generate_synthetic_documents(
    count: int,
    seed: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Generate N synthetic documents for testing.
    
    Args:
        count: Number of documents to generate.
        seed: Optional random seed for reproducibility.
    
    Returns:
        List of dictionaries representing BrainClaw-compatible documents.
        
    Example:
        >>> docs = generate_synthetic_documents(5, seed=123)
        >>> len(docs)
        5
        >>> docs[0]["content"]
        'Alice Chen developed a new Python system for machine learning.'
    """
    if seed is not None:
        random.seed(seed)
    
    config = SyntheticDataConfig(seed=seed)
    documents = []
    
    for i in range(count):
        content = _generate_content(TOPICS, ACTIONS, TECHNOLOGIES, PERSON_NAMES, config)
        
        doc = {
            "id": _generate_uuid(),
            "tenant_id": _generate_uuid(),
            "agent_id": _generate_uuid(),
            "memory_class": "semantic",
            "memory_type": random.choice(["fact", "concept", "domain_knowledge"]),
            "status": "active",
            "content": content,
            "content_embedding": None,  # Set to actual embedding if needed
            "source_session_id": _generate_uuid(),
            "source_message_id": _generate_uuid(),
            "extraction_timestamp": _random_timestamp(),
            "extractor_name": "synthetic_generator",
            "extractor_version": "1.0.0",
            "confidence": round(random.uniform(0.7, 1.0), 2),
            "valid_from": _random_timestamp(),
            "is_current": True,
            "visibility_scope": "tenant",
            "created_at": _random_timestamp(),
            "updated_at": _random_timestamp(),
        }
        documents.append(doc)
    
    return documents


def generate_contradictory_documents(
    count: int,
    seed: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Generate documents with intentional contradictions for testing.
    
    These documents contain pairs of contradictory statements that can be
    used to test the contradiction detection system.
    
    Args:
        count: Number of document pairs to generate (2 docs per pair).
        seed: Optional random seed for reproducibility.
    
    Returns:
        List of dictionaries with contradictory statement pairs.
        
    Example:
        >>> docs = generate_contradictory_documents(3, seed=42)
        >>> len(docs)
        6  # 3 pairs = 6 documents
    """
    if seed is not None:
        random.seed(seed)
    
    documents = []
    
    for i in range(count):
        # Select a random contradictory pair
        statement_a, statement_b = random.choice(CONTRADICTORY_PAIRS)
        
        # Create two documents with contradictory content
        for idx, statement in enumerate([statement_a, statement_b]):
            doc = {
                "id": _generate_uuid(),
                "tenant_id": _generate_uuid(),
                "agent_id": _generate_uuid(),
                "memory_class": "semantic",
                "memory_type": "fact",
                "status": "active",
                "content": statement,
                "content_embedding": None,
                "source_session_id": _generate_uuid(),
                "source_message_id": _generate_uuid(),
                "extraction_timestamp": _random_timestamp(),
                "extractor_name": "synthetic_generator",
                "extractor_version": "1.0.0",
                "confidence": round(random.uniform(0.8, 1.0), 2),
                "valid_from": _random_timestamp(),
                "is_current": True,
                "visibility_scope": "tenant",
                # Tags for contradiction testing
                "contradiction_group": f"pair_{i}",
                "contradiction_position": idx,  # 0 or 1
                "created_at": _random_timestamp(),
                "updated_at": _random_timestamp(),
            }
            documents.append(doc)
    
    return documents


def generate_entity_rich_documents(
    count: int,
    seed: Optional[int] = None,
    config: Optional[SyntheticDataConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Generate documents with many entities and relationships.
    
    These documents contain rich entity data including persons, technologies,
    and topics, along with extracted relationships for graph testing.
    
    Args:
        count: Number of documents to generate.
        seed: Optional random seed for reproducibility.
        config: Optional configuration for document generation.
    
    Returns:
        List of dictionaries with entity-rich content and relationships.
        
    Example:
        >>> docs = generate_entity_rich_documents(10, seed=42)
        >>> doc = docs[0]
        >>> len(doc.get("entities", [])) > 0
        True
    """
    if seed is not None:
        random.seed(seed)
    
    if config is None:
        config = SyntheticDataConfig(seed=seed)
    
    documents = []
    
    for i in range(count):
        # Generate content with multiple entities
        content = _generate_content(
            TOPICS, ACTIONS, TECHNOLOGIES, PERSON_NAMES, config
        )
        
        # Extract entities from content
        entities = _extract_entities_from_content(content)
        
        # Generate relationships between entities
        relationships = []
        if len(entities) >= 2:
            num_rels = random.randint(1, min(3, len(entities) - 1))
            for _ in range(num_rels):
                ent1, ent2 = random.sample(entities, 2)
                relationships.append({
                    "from": ent1["name"],
                    "to": ent2["name"],
                    "type": random.choice(["depends_on", "uses", "related_to", "implements"]),
                })
        
        doc = {
            "id": _generate_uuid(),
            "tenant_id": _generate_uuid(),
            "agent_id": _generate_uuid(),
            "memory_class": "semantic",
            "memory_type": random.choice(["fact", "concept", "domain_knowledge", "rule"]),
            "status": "active",
            "content": content,
            "content_embedding": None,
            "source_session_id": _generate_uuid(),
            "source_message_id": _generate_uuid(),
            "extraction_timestamp": _random_timestamp(),
            "extractor_name": "synthetic_generator",
            "extractor_version": "1.0.0",
            "confidence": round(random.uniform(0.7, 1.0), 2),
            "valid_from": _random_timestamp(),
            "is_current": True,
            "visibility_scope": "tenant",
            # Rich entity data for graph testing
            "entities": entities,
            "relationships": relationships,
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "created_at": _random_timestamp(),
            "updated_at": _random_timestamp(),
        }
        documents.append(doc)
    
    return documents