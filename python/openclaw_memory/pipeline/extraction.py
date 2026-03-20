"""Entity and relationship extraction pipeline module."""
from dataclasses import dataclass, field
from typing import List, Optional, Set
from uuid import uuid4
import re


# Entity types supported by extraction (FR-014: 14 domain-relevant types)
ENTITY_TYPES = [
    "person", "agent", "system", "project", "repository", "file",
    "decision", "command", "organization", "resource", "environment",
    "policy", "event", "tool", "concept",
]

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
            self.canonical_name = self.name.lower().strip().replace(" ", "-")


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
    r'|OpenClaw|BrainClaw|Lossless-Claw|ChatGPT|Claude|GPT-\d|BERT|Transformer'
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


# --- FR-014 additional entity extractors ---

# Agent patterns (named AI agents/assistants)
AGENT_PATTERN = re.compile(
    r'\b(Albert|Einstein|Blackwell|Babatunde|Zeke|Lore|Oliver Wendell|Agent Zero)\b'
)


def extract_agents(text: str) -> List[Entity]:
    """Extract agent entities (named AI agents/assistants)."""
    entities = []
    seen: Set[str] = set()
    for match in AGENT_PATTERN.finditer(text):
        name = match.group(0)
        if name.lower() not in seen:
            seen.add(name.lower())
            entities.append(Entity(
                entity_type="agent", name=name, confidence=0.9,
            ))
    return entities


# Repository patterns
REPO_PATTERN = re.compile(
    r'\b([A-Za-z][A-Za-z0-9_-]+/[A-Za-z][A-Za-z0-9_-]+)\b'  # org/repo
    r'|\b([a-z][a-z0-9_-]+\.git)\b',  # foo.git
)


def extract_repositories(text: str) -> List[Entity]:
    """Extract repository entities."""
    entities = []
    seen: Set[str] = set()
    for match in REPO_PATTERN.finditer(text):
        name = match.group(1) or match.group(2)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            entities.append(Entity(
                entity_type="repository", name=name, confidence=0.85,
            ))
    return entities


def extract_decisions(text: str) -> List[Entity]:
    """Extract decision entities from decision-indicating phrases."""
    entities = []
    seen: Set[str] = set()
    for phrase in DECISION_PHRASES:
        idx = text.lower().find(phrase)
        if idx >= 0:
            # Extract the clause after the decision phrase
            rest = text[idx + len(phrase):].strip()
            clause = rest.split(".")[0].strip()[:120]
            if clause and clause.lower() not in seen:
                seen.add(clause.lower())
                entities.append(Entity(
                    entity_type="decision", name=clause, confidence=0.7,
                ))
    return entities


# Command patterns
COMMAND_PATTERN = re.compile(
    r'`([a-z][a-z0-9_-]*(?:\s+[a-z0-9_./-]+){0,5})`',
    re.IGNORECASE,
)


def extract_commands(text: str) -> List[Entity]:
    """Extract command entities (CLI commands in backticks)."""
    entities = []
    seen: Set[str] = set()
    for match in COMMAND_PATTERN.finditer(text):
        name = match.group(1).strip()
        if len(name) > 3 and name.lower() not in seen:
            seen.add(name.lower())
            entities.append(Entity(
                entity_type="command", name=name, confidence=0.8,
            ))
    return entities


ORG_PATTERN = re.compile(
    r'\b(AijooseFactory|Ai joose Factory|OpenAI|Google|Microsoft|Meta|Anthropic)\b',
    re.IGNORECASE,
)


def extract_organizations(text: str) -> List[Entity]:
    """Extract organization entities."""
    entities = []
    seen: Set[str] = set()
    for match in ORG_PATTERN.finditer(text):
        name = match.group(0)
        if name.lower() not in seen:
            seen.add(name.lower())
            entities.append(Entity(
                entity_type="organization", name=name, confidence=0.85,
            ))
    return entities


def extract_resources(text: str) -> List[Entity]:
    """Extract resource entities (URLs, endpoints, services)."""
    entities = []
    seen: Set[str] = set()
    url_pattern = re.compile(r'https?://[^\s)>"]+', re.IGNORECASE)
    for match in url_pattern.finditer(text):
        url = match.group(0).rstrip(".,;:")
        if url.lower() not in seen:
            seen.add(url.lower())
            entities.append(Entity(
                entity_type="resource", name=url, confidence=0.9,
            ))
    return entities


ENV_PATTERN = re.compile(
    r'\b(production|staging|development|dev|prod|local|ci|test)\s*(?:environment|env|server|cluster)\b',
    re.IGNORECASE,
)


def extract_environments(text: str) -> List[Entity]:
    """Extract environment entities."""
    entities = []
    seen: Set[str] = set()
    for match in ENV_PATTERN.finditer(text):
        name = match.group(0).strip()
        if name.lower() not in seen:
            seen.add(name.lower())
            entities.append(Entity(
                entity_type="environment", name=name.title(), confidence=0.75,
            ))
    return entities


def extract_policies(text: str) -> List[Entity]:
    """Extract policy entities (rules, constraints, requirements)."""
    entities = []
    seen: Set[str] = set()
    policy_markers = [
        "must not", "must never", "must always", "required to",
        "policy:", "rule:", "constraint:", "do not",
    ]
    for marker in policy_markers:
        idx = text.lower().find(marker)
        if idx >= 0:
            clause = text[idx:].split(".")[0].strip()[:120]
            if clause and clause.lower() not in seen:
                seen.add(clause.lower())
                entities.append(Entity(
                    entity_type="policy", name=clause, confidence=0.7,
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
    
    # Extract each entity type (FR-014: all 14 domain types + concept)
    all_entities.extend(extract_persons(text))
    all_entities.extend(extract_agents(text))
    all_entities.extend(extract_projects(text))
    all_entities.extend(extract_systems(text))
    all_entities.extend(extract_tools(text))
    all_entities.extend(extract_files(text))
    all_entities.extend(extract_concepts(text))
    all_entities.extend(extract_repositories(text))
    all_entities.extend(extract_decisions(text))
    all_entities.extend(extract_commands(text))
    all_entities.extend(extract_organizations(text))
    all_entities.extend(extract_resources(text))
    all_entities.extend(extract_environments(text))
    all_entities.extend(extract_policies(text))
    
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
    seen_relationships: Set[tuple[str, str, str]] = set()

    if not text or not entities or len(entities) < 2:
        return relationships

    def append_relationship(source_name: str, target_name: str, relationship_type: str, confidence: float, evidence: str) -> None:
        for source_entity in entities:
            if source_name.lower() not in source_entity.name.lower():
                continue
            for target_entity in entities:
                if source_entity.id == target_entity.id:
                    continue
                if target_name.lower() not in target_entity.name.lower():
                    continue
                key = (source_entity.id, target_entity.id, relationship_type)
                if key in seen_relationships:
                    continue
                seen_relationships.add(key)
                relationships.append(Relationship(
                    source_entity_id=source_entity.id,
                    target_entity_id=target_entity.id,
                    relationship_type=relationship_type,
                    confidence=confidence,
                    evidence=evidence,
                ))

    # Simple rule-based relationship detection
    
    # works_on pattern: "X works on Y"
    works_on_pattern = re.compile(
        r'(\w+(?:\s+\w+)?)\s+(?:works?|working)\s+on\s+(\w+(?:\s+\w+)?)',
        re.IGNORECASE
    )
    
    for match in works_on_pattern.finditer(text):
        append_relationship(
            match.group(1).strip(),
            match.group(2).strip(),
            "works_on",
            0.7,
            match.group(0),
        )
    
    # depends_on pattern
    depends_pattern = re.compile(
        r'(\w+(?:\s+\w+)?)\s+depends\s+on\s+(\w+(?:\s+\w+)?)',
        re.IGNORECASE
    )
    
    for match in depends_pattern.finditer(text):
        append_relationship(
            match.group(1).strip(),
            match.group(2).strip(),
            "depends_on",
            0.8,
            match.group(0),
        )

    uses_pattern = re.compile(
        r'([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)?)\s+(?:uses?|using)\s+([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)?)',
        re.IGNORECASE,
    )
    for match in uses_pattern.finditer(text):
        append_relationship(
            match.group(1).strip(),
            match.group(2).strip(),
            "uses",
            0.82,
            match.group(0),
        )

    # integrates_with pattern
    integrates_pattern = re.compile(
        r'([A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)*)\s+(?:integrates?\s+with|works?\s+with|paired\s+with)\s+([A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)*)',
        re.IGNORECASE,
    )
    for match in integrates_pattern.finditer(text):
        append_relationship(
            match.group(1).strip(),
            match.group(2).strip(),
            "collaborates_with",
            0.76,
            match.group(0),
        )

    # implements pattern: "X implements Y"
    implements_pattern = re.compile(
        r'([A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)*)\s+(?:implements?|implementing)\s+([A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)*)',
        re.IGNORECASE,
    )
    for match in implements_pattern.finditer(text):
        append_relationship(
            match.group(1).strip(),
            match.group(2).strip(),
            "implements",
            0.85,
            match.group(0),
        )

    # part_of pattern: "X is part of Y"
    part_of_pattern = re.compile(
        r'([A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)*)\s+is\s+part\s+of\s+([A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)*)',
        re.IGNORECASE,
    )
    for match in part_of_pattern.finditer(text):
        append_relationship(
            match.group(1).strip(),
            match.group(2).strip(),
            "part_of",
            0.8,
            match.group(0),
        )

    for sentence in re.split(r'(?<=[.!?])\s+', text):
        lowered = sentence.lower()
        mentions = []
        for entity in entities:
            idx = lowered.find(entity.name.lower())
            if idx >= 0:
                mentions.append((idx, entity.name))
        mentions.sort(key=lambda item: item[0])
        ordered_names = []
        for _, name in mentions:
            if name not in ordered_names:
                ordered_names.append(name)
        if len(ordered_names) < 2:
            continue
        if re.search(r'\buses?\b|\busing\b', lowered):
            append_relationship(
                ordered_names[0],
                ordered_names[1],
                "uses",
                0.82,
                sentence.strip(),
            )
        elif re.search(r'\b(integrates?\s+with|works?\s+with|paired\s+with)\b', lowered):
            append_relationship(
                ordered_names[0],
                ordered_names[1],
                "collaborates_with",
                0.76,
                sentence.strip(),
            )

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
