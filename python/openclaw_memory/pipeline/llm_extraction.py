"""
LLM-powered entity and relationship extraction.

This module provides LLM-based extraction using local Ollama for enhanced
entity and relationship detection beyond basic regex extraction.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import aiohttp
import json
import re


@dataclass
class ExtractedEntity:
    """An extracted entity from content."""
    name: str
    entity_type: str  # Person, Organization, Technology, Concept, Decision, etc.
    canonical_name: str  # Normalized form
    confidence: float
    properties: Dict[str, Any]


@dataclass
class ExtractedRelationship:
    """An extracted relationship between entities."""
    source_entity: str
    target_entity: str
    relationship_type: str  # WORKS_WITH, USES, DECIDED_BY, RELATES_TO, etc.
    confidence: float
    properties: Dict[str, Any]


class LLMExtractionService:
    """Extract entities and relationships using LLM (Ollama)."""

    def __init__(
        self,
        base_url: str = "http://host.docker.internal:11434",
        model: str = "llama3.2"
    ):
        self.base_url = base_url
        self.model = model
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self) -> None:
        """Initialize the HTTP session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def extract_entities(
        self,
        content: str,
        entity_types: Optional[List[str]] = None
    ) -> List[ExtractedEntity]:
        """Extract entities from content using LLM."""
        if not self._session:
            raise RuntimeError("LLM service not initialized. Call initialize() first.")

        if entity_types is None:
            entity_types = [
                "Person", "Organization", "Technology", "Concept",
                "Decision", "Event", "Location", "Date", "Metric"
            ]

        prompt = f"""Extract entities from the following text. Return a JSON array of entities.

Entity types to look for: {', '.join(entity_types)}

Text:
{content}

Return format:
[
  {{"name": "Entity Name", "type": "EntityType", "canonical_name": "normalized form", "confidence": 0.95}}
]

Only return the JSON array, no other text. Be precise and extract only clearly mentioned entities."""

        try:
            async with self._session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for extraction
                        "num_predict": 1024
                    }
                }
            ) as resp:
                if resp.status != 200:
                    return await self._fallback_extract_entities(content, entity_types)

                data = await resp.json()
                response_text = data.get("response", "[]")

                # Parse JSON from response
                entities_json = self._extract_json(response_text)
                if not entities_json:
                    return await self._fallback_extract_entities(content, entity_types)

                entities = []
                for item in entities_json:
                    entities.append(ExtractedEntity(
                        name=item.get("name", ""),
                        entity_type=item.get("type", "Concept"),
                        canonical_name=item.get("canonical_name", item.get("name", "")),
                        confidence=item.get("confidence", 0.8),
                        properties=item.get("properties", {})
                    ))

                return entities

        except Exception:
            # Fallback to regex extraction on error
            return await self._fallback_extract_entities(content, entity_types)

    async def extract_relationships(
        self,
        content: str,
        entities: List[ExtractedEntity]
    ) -> List[ExtractedRelationship]:
        """Extract relationships between entities using LLM."""
        if not self._session:
            raise RuntimeError("LLM service not initialized. Call initialize() first.")

        if len(entities) < 2:
            return []

        entity_names = [e.name for e in entities]

        prompt = f"""Extract relationships between entities from the following text.

Entities: {', '.join(entity_names)}

Text:
{content}

Return format:
[
  {{"source": "Entity1", "target": "Entity2", "relationship": "RELATIONSHIP_TYPE", "confidence": 0.9}}
]

Relationship types: WORKS_WITH, USES, DECIDED_BY, RELATES_TO, LOCATED_AT, CREATED_BY, DEPENDS_ON

Only return the JSON array, no other text."""

        try:
            async with self._session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 512
                    }
                }
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                response_text = data.get("response", "[]")

                relationships_json = self._extract_json(response_text)
                if not relationships_json:
                    return []

                relationships = []
                for item in relationships_json:
                    relationships.append(ExtractedRelationship(
                        source_entity=item.get("source", ""),
                        target_entity=item.get("target", ""),
                        relationship_type=item.get("relationship", "RELATES_TO"),
                        confidence=item.get("confidence", 0.8),
                        properties=item.get("properties", {})
                    ))

                return relationships

        except Exception:
            return []

    async def extract_memories(
        self,
        content: str,
        session_id: str,
        message_id: str
    ) -> List[Dict[str, Any]]:
        """Extract all memories (entities, relationships, facts) from content."""
        entities = await self.extract_entities(content)
        relationships = await self.extract_relationships(content, entities)

        memories = []

        # Add entity memories
        for entity in entities:
            memories.append({
                "memory_type": "entity",
                "name": entity.name,
                "entity_type": entity.entity_type,
                "canonical_name": entity.canonical_name,
                "confidence": entity.confidence,
                "session_id": session_id,
                "message_id": message_id
            })

        # Add relationship memories
        for rel in relationships:
            memories.append({
                "memory_type": "relationship",
                "source": rel.source_entity,
                "target": rel.target_entity,
                "relationship_type": rel.relationship_type,
                "confidence": rel.confidence,
                "session_id": session_id,
                "message_id": message_id
            })

        return memories

    async def detect_contradictions(
        self,
        new_fact: str,
        existing_facts: List[str]
    ) -> List[Dict[str, Any]]:
        """Detect if new fact contradicts existing facts using LLM."""
        if not self._session or not existing_facts:
            return []

        prompt = f"""Detect contradictions between the new fact and existing facts.

New fact: {new_fact}

Existing facts:
{chr(10).join(f"- {f}" for f in existing_facts)}

Return format:
[
  {{"existing_fact": "fact text", "contradiction": true/false, "reason": "explanation"}}
]

Only return the JSON array."""

        try:
            async with self._session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 256
                    }
                }
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                response_text = data.get("response", "[]")

                contradictions_json = self._extract_json(response_text)
                if contradictions_json:
                    return [c for c in contradictions_json if c.get("contradiction")]
                return []

        except Exception:
            return []

    def _extract_json(self, text: str) -> Optional[List[Any]]:
        """Extract JSON array from LLM response."""
        # Try to find JSON array in response
        array_match = re.search(r'\[[\s\S]*\]', text)
        if array_match:
            try:
                return json.loads(array_match.group())
            except json.JSONDecodeError:
                pass

        return None

    async def _fallback_extract_entities(
        self,
        content: str,
        entity_types: Optional[List[str]]
    ) -> List[ExtractedEntity]:
        """Fallback to regex extraction if LLM fails."""
        entities = []

        # Capitalized words (potential entities)
        capitalized = re.findall(r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b', content)
        for name in set(capitalized):
            entities.append(ExtractedEntity(
                name=name,
                entity_type=self._guess_entity_type(name),
                canonical_name=name.lower(),
                confidence=0.6  # Lower confidence for regex
            ))

        return entities

    def _guess_entity_type(self, name: str) -> str:
        """Guess entity type from name."""
        if any(word in name.lower() for word in ["inc", "corp", "llc", "ltd"]):
            return "Organization"
        if name[0].isupper() and len(name.split()) > 1:
            return "Person"
        return "Concept"