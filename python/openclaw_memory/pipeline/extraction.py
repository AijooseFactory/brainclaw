"""Entity and relationship extraction pipeline module."""
from dataclasses import dataclass, field
from typing import List, Optional, Set
from uuid import uuid4
import re


# Entity types supported by extraction
ENTITY_TYPES = ["person", "project", "system", "concept", "tool", "file"]

# Relationship types supported
RELATIONSHIP_TYPES = [
    "works_on",
    "depends_on",
    "part_of",
    "uses",
    "created_by",
    "related_to",
    "collaborates_with",
    "implements",
    "manages",
]


@dataclass
class Entity:
    """Extracted entity from content.
    
    Attributes:
        id: Unique identifier
        entity_type: Type (person, project, system, concept, tool, file)
        name: Entity name
        canonical_name: Normalized name for matching
        description: Optional description
        properties: Additional properties
        aliases: List of aliases
        confidence: Extraction confidence (0.0-1.0)
        source_memory_ids: Source memory item IDs
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    entity_type: str = ""
    name: str = ""
    canonical_name: str = ""
    description: str = ""
    properties: dict = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    confidence: float = 0.5
    source_memory_ids: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.canonical_name and self.name:
            self.canonical_name = self.name.lower().strip()


@dataclass
class Relationship:
    """Extracted relationship between entities.
    
    Attributes:
        id: Unique identifier
        source_entity_id: Source entity UUID
        target_entity_id: Target entity UUID
        relationship_type: Type of relationship
        properties: Additional properties
        confidence: Extraction confidence (0.0-1.0)
        evidence: Evidence text for the relationship
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    source_entity_id: str = ""
    target_entity_id: str = ""
    relationship_type: str = ""
    properties: dict = field(default_factory=dict)
    confidence: float = 0.5
    evidence: str = ""


@dataclass
class ExtractionResult:
    """Result of extraction containing entities and relationships."""
    entities: List[Entity] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    
    @property
    def has_content(self) -> bool:
        return len(self.entities) > 0 or len(self.relationships) > 0


# Common patterns for rule-based extraction

# Person name patterns (capitalized words)
PERSON_PATTERN = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
)

# Project names (capitalized with possible hyphens)
PROJECT_PATTERN = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:System|Project|Memory|System))\b'
)

# System names (specific technologies)
SYSTEM_PATTERN = re.compile(
    r'\b(PostgreSQL|Neo4j|Weaviate|Redis|MongoDB|Elasticsearch|Kafka|Docker|Kubernetes)'
    r'|OpenClaw|ChatGPT|Claude|GPT-\d|BERT|Transformer'
    r'(?:DB|Store|Server|API)?\b',
    re.IGNORECASE
)

# Tool names (common tool patterns)
TOOL_PATTERN = re.compile(
    r'\b(memory_query|memory_store|memory_decide|memory_entity)'
    r'|(?:memory|query|store|fetch|search|execute|run)_[a-z_]+'
    r'|(?:git|python|node|npm|pnpm|docker|kubectl)\b',
    re.IGNORECASE
)

# File patterns
FILE_PATTERN = re.compile(
    r'\b([a-zA-Z_][a-zA-Z0-9_]*\.(?:py|md|yaml|yml|json|sql|js|ts|toml))\b'
)

# Decision phrases
DECISION_PHRASES = [
    "we decided",
    "let's go with",
    "agreed on",
    "the decision was",
    "will use",
    "going with",
    "chose to use",
    "selected",
]

# Preference phrases
PREFERENCE_PHRASES = [
    "remember this",
    "i prefer",
    "i like",
    "my preference",
    "i always",
    "don't forget",
]


def extract_persons(text: str) -> List[Entity]:
    """Extract person entities using pattern matching."""
    entities = []
    seen_names: Set[str] = set()
    
    for match in PERSON_PATTERN.finditer(text):
        name = match.group(1)
        # Filter out common false positives
        if name.lower() in ["the", "this", "that", "will be", "can be"]:
            continue
        
        if name not in seen_names:
            seen_names.add(name)
            entities.append(Entity(
                entity_type="person",
                name=name,
                confidence=0.7,
            ))
    
    return entities


def extract_projects(text: str) -> List[Entity]:
    """Extract project entities."""
    entities = []
    seen: Set[str] = set()
    
    # Look for known project patterns
    project_indicators = [
        "the memory system",
        "graphrag",
        "hybrid graphrag",
        "openclaw",
        "the project",
    ]
    
    for indicator in project_indicators:
        if indicator.lower() in text.lower():
            name = indicator.title()
            if name not in seen:
                seen.add(name)
                entities.append(Entity(
                    entity_type="project",
                    name=name,
                    confidence=0.6,
                ))
    
    return entities


def extract_systems(text: str) -> List[Entity]:
    """Extract system/technology entities."""
    entities = []
    seen: Set[str] = set()
    
    for match in SYSTEM_PATTERN.finditer(text):
        name = match.group(0)
        if name.lower() not in seen:
            seen.add(name.lower())
            entities.append(Entity(
                entity_type="system",
                name=name,
                confidence=0.85,
            ))
    
    return entities


def extract_tools(text: str) -> List[Entity]:
    """Extract tool entities."""
    entities = []
    seen: Set[str] = set()
    
    for match in TOOL_PATTERN.finditer(text):
        name = match.group(0)
        if name.lower() not in seen:
            seen.add(name.lower())
            entities.append(Entity(
                entity_type="tool",
                name=name,
                confidence=0.75,
            ))
    
    return entities


def extract_files(text: str) -> List[Entity]:
    """Extract file entities."""
    entities = []
    seen: Set[str] = set()
    
    for match in FILE_PATTERN.finditer(text):
        name = match.group(1)
        if name.lower() not in seen:
            seen.add(name.lower())
            entities.append(Entity(
                entity_type="file",
                name=name,
                confidence=0.9,
            ))
    
    return entities


def extract_concepts(text: str) -> List[Entity]:
    """Extract concept entities (abstract nouns/ideas)."""
    entities = []
    seen: Set[str] = set()
    
    concept_indicators = [
        "knowledge graph",
        "vector embedding",
        "semantic search",
        "memory",
        "retrieval",
        "extraction",
        "chunking",
        "sync",
        "lifecycle",
    ]
    
    for concept in concept_indicators:
        if concept in text.lower():
            if concept not in seen:
                seen.add(concept)
                entities.append(Entity(
                    entity_type="concept",
                    name=concept.title(),
                    confidence=0.5,
                ))
    
    return entities


def extract_entities(text: str, method: str = "rule") -> List[Entity]:
    """Extract all entities from text using specified method.
    
    Args:
        text: Input text to extract entities from
        method: Extraction method ('rule' or 'llm')
        
    Returns:
        List of extracted Entity objects
    """
    if not text:
        return []
    
    # Rule-based extraction (primary)
    all_entities = []
    
    # Extract each entity type
    all_entities.extend(extract_persons(text))
    all_entities.extend(extract_projects(text))
    all_entities.extend(extract_systems(text))
    all_entities.extend(extract_tools(text))
    all_entities.extend(extract_files(text))
    all_entities.extend(extract_concepts(text))
    
    # Deduplicate by name
    seen: Set[str] = set()
    unique_entities = []
    for entity in all_entities:
        key = f"{entity.entity_type}:{entity.name.lower()}"
        if key not in seen:
            seen.add(key)
            unique_entities.append(entity)
    
    return unique_entities


def extract_relationships(text: str, entities: Optional[List[Entity]] = None) -> List[Relationship]:
    """Extract relationships between entities.
    
    Args:
        text: Source text
        entities: Optional list of pre-extracted entities to link
        
    Returns:
        List of Relationship objects
    """
    relationships = []
    
    if not text or not entities or len(entities) < 2:
        return relationships
    
    # Simple rule-based relationship detection
    
    # works_on pattern: "X works on Y"
    works_on_pattern = re.compile(
        r'(\w+(?:\s+\w+)?)\s+(?:works?|working)\s+on\s+(\w+(?:\s+\w+)?)',
        re.IGNORECASE
    )
    
    for match in works_on_pattern.finditer(text):
        source_name = match.group(1).strip()
        target_name = match.group(2).strip()
        
        # Find matching entities
        for e in entities:
            if source_name.lower() in e.name.lower():
                for t in entities:
                    if target_name.lower() in t.name.lower():
                        relationships.append(Relationship(
                            source_entity_id=e.id,
                            target_entity_id=t.id,
                            relationship_type="works_on",
                            confidence=0.7,
                            evidence=match.group(0),
                        ))
    
    # depends_on pattern
    depends_pattern = re.compile(
        r'(\w+(?:\s+\w+)?)\s+depends\s+on\s+(\w+(?:\s+\w+)?)',
        re.IGNORECASE
    )
    
    for match in depends_pattern.finditer(text):
        source_name = match.group(1).strip()
        target_name = match.group(2).strip()
        
        for e in entities:
            if source_name.lower() in e.name.lower():
                for t in entities:
                    if target_name.lower() in t.name.lower():
                        relationships.append(Relationship(
                            source_entity_id=e.id,
                            target_entity_id=t.id,
                            relationship_type="depends_on",
                            confidence=0.8,
                            evidence=match.group(0),
                        ))
    
    return relationships


def extract_all(text: str, method: str = "rule") -> ExtractionResult:
    """Extract both entities and relationships from text.
    
    Args:
        text: Input text
        method: Extraction method ('rule' or 'llm')
        
    Returns:
        ExtractionResult with entities and relationships
    """
    entities = extract_entities(text, method)
    relationships = extract_relationships(text, entities)
    
    return ExtractionResult(
        entities=entities,
        relationships=relationships,
    )


# Alias for backwards compatibility
extract_from_text = extract_all