"""Relationship Enhancement Service for increasing graph density."""
from typing import List, Set
from .extraction import ExtractionResult, Relationship, Entity
import re

class RelationshipEnhancer:
    """Enhances extracted relationships using contextual analysis."""
    
    def __init__(self, confidence_threshold: float = 0.4):
        self.confidence_threshold = confidence_threshold

    def enhance(self, text: str, result: ExtractionResult) -> ExtractionResult:
        """Adds implicit relationships based on contextual proximity.
        
        Args:
            text: Original source text
            result: Existing extraction result to enhance
            
        Returns:
            Enhanced ExtractionResult
        """
        if not text or not result.entities:
            return result
            
        # 1. Deduplicate existing relationships
        existing_keys = {
            (r.source_entity_id, r.target_entity_id, r.relationship_type)
            for r in result.relationships
        }
        
        # 2. Co-occurrence discovery (entities in same sentence/paragraph)
        # We look for entities mentioned together that don't already have an edge.
        sentences = re.split(r'(?<=[.!?])\s+', text)
        entities = result.entities
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            # Find which entities are in this sentence
            sentence_entities = []
            for entity in entities:
                if entity.name.lower() in sentence_lower:
                    sentence_entities.append(entity)
            
            # If 2+ entities in same sentence, link them as 'related_to' if no edge exists
            if len(sentence_entities) >= 2:
                for i in range(len(sentence_entities)):
                    for j in range(i + 1, len(sentence_entities)):
                        e1 = sentence_entities[i]
                        e2 = sentence_entities[j]
                        
                        # Only add if no existing relation exists in either direction
                        rel_key = (e1.id, e2.id, "related_to")
                        reverse_key = (e2.id, e1.id, "related_to")
                        
                        has_any = any(
                            (r.source_entity_id == e1.id and r.target_entity_id == e2.id) or
                            (r.source_entity_id == e2.id and r.target_entity_id == e1.id)
                            for r in result.relationships
                        )
                        
                        if not has_any:
                            result.relationships.append(Relationship(
                                source_entity_id=e1.id,
                                target_entity_id=e2.id,
                                relationship_type="related_to",
                                confidence=0.45, # Implied proximity
                                evidence=sentence.strip()[:100],
                                properties={"method": "co-occurrence"}
                            ))
        # 3. Agent-Utility linking
        # If an agent is mentioned with a tool or file, link them
        for entity in entities:
            if entity.entity_type == "agent":
                for target in entities:
                    if target.entity_type in ["tool", "file", "command"] and entity.id != target.id:
                        # Link agent -> utility as 'uses' if not already linked
                        has_uses = any(
                            r.source_entity_id == entity.id and 
                            r.target_entity_id == target.id and
                            r.relationship_type == "uses"
                            for r in result.relationships
                        )
                        if not has_uses:
                            result.relationships.append(Relationship(
                                source_entity_id=entity.id,
                                target_entity_id=target.id,
                                relationship_type="uses",
                                confidence=0.5,
                                evidence="Implicit agent-tool context",
                                properties={"method": "agent-utility-link"}
                            ))

        return result
