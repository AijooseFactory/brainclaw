"""
Write Policy for the BrainClaw Memory System.

 Implements promotion rules for determining what should be stored
 in memory versus discarded. Based on the spec requirements:

 Always Store (Raw Events):
 - user_messages
 - assistant_messages
 - system_messages
 - tool_calls

 Selectively Promote:
 - Facts: confidence >= 0.7 OR user_confirmed
 - Decisions: explicitly marked OR inferred from phrases
 - Preferences: "remember this" OR stated 2+ times
 - Procedures: successful execution trace + explicit success signal
 - Entities: mentioned 2+ times OR explicitly introduced

 Never Promote:
 - low_confidence_extractions
 - contradicted_claims
 - chit_chat

 IMPORTANT: Low-quality extractions are NEVER deleted.
 They remain in the raw history tables (messages, tool_calls) with full provenance.
 Only promoted memories appear in memory_items.

 Promotion is SELECTIVE, not destructive.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from uuid import uuid4

from .classes import MemoryClass, Memory, DecisionStatus, AgentMemory, DecisionMemory

# Forward declaration for type hints
LLMExtractionService = None


class ContentType(str, Enum):
    """Types of content that can be processed."""
    # Always stored
    USER_MESSAGE = "user_messages"
    ASSISTANT_MESSAGE = "assistant_messages"
    SYSTEM_MESSAGE = "system_messages"
    TOOL_CALL = "tool_calls"

    # Extracted content types
    FACT = "fact"
    DECISION = "decision"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    ENTITY = "entity"
    CONCEPT = "concept"

    # Never promote
    LOW_CONFIDENCE_EXTRACTION = "low_confidence_extractions"
    CONTRADICTED_CLAIM = "contradicted_claims"
    CHIT_CHAT = "chit_chat"
    TEMPORARY_CONTEXT = "temporary_context"
    UNCONFIRMED_SPECULATION = "unconfirmed_speculation"


# Decision detection phrases as defined in spec
DECISION_PHRASES: List[str] = [
    "we decided",
    "let's go with",
    "agreed on",
    "chose to",
    "going with",
    "decided to",
    "the decision was",
    "we will use",
    "we'll use",
    "adopted",
    "selected",
    "agreed to",
    "settled on",
]

# Preference detection phrases
PREFERENCE_PHRASES: List[str] = [
    "remember this",
    "i prefer",
    "i like",
    "my preference",
    "always",
    "never",
    "don't forget",
    "make sure to",
    "important to me",
    "i don't like",
    "avoid",
]

# Chit-chat patterns (never promote)
CHIT_CHAT_PATTERNS: List[str] = [
    r"\b(hi|hello|hey|howdy)\b",
    r"\b(thanks|thank you|thx)\b",
    r"\b(bye|goodbye|see you)\b",
    r"\b(how are you|what's up|howdy)\b",
    r"\bnice\b.*\bweather\b",
    r"\bweather\b.*\bnice\b",
]


@dataclass
class ExtractionResult:
    """
    Result from content extraction/pipeline.

    Contains metadata about the extracted content.
    """
    content: str
    content_type: ContentType
    confidence: float = 0.5
    memory_class: Optional[MemoryClass] = None
    memory_type: Optional[str] = None

    # Additional metadata
    is_explicit: bool = False  # Is this explicitly marked (e.g., "remember this")
    mention_count: int = 1  # How many times was this mentioned
    has_success_signal: bool = False  # For procedures: was it explicitly successful?
    is_contradicted: bool = False  # Has this been contradicted by newer info
    user_confirmed: bool = False  # Has user confirmed this information


@dataclass
class WritePolicy:
    """
    Write Policy implementation for determining what to store and promote.

    Implements the spec requirements:
    - always_store: items that are always stored as raw events
    - never_promote: items that are never promoted to memory
    - promotion_rules: rules for selectively promoting to memory
    """

    # Always store these content types (raw events)
    always_store: Set[str] = field(default_factory=lambda: {
        "user_messages",
        "assistant_messages",
        "system_messages",
        "tool_calls",
    })

    # Never promote these content types
    never_promote: Set[str] = field(default_factory=lambda: {
        "low_confidence_extractions",
        "contradicted_claims",
        "chit_chat",
        "temporary_context",
        "unconfirmed_speculation",
    })

    # Minimum confidence threshold for facts
    fact_confidence_threshold: float = 0.7

    def should_always_store(self, content_type: ContentType) -> bool:
        """
        Check if content should always be stored as raw event.

        Args:
            content_type: Type of content to check

        Returns:
            True if content should always be stored
        """
        return content_type.value in self.always_store

    def should_never_promote(
        self,
        content_type: Optional[ContentType] = None,
        is_contradicted: bool = False,
        is_chit_chat: bool = False,
    ) -> bool:
        """
        Check if content should never be promoted to memory.

        Args:
            content_type: Type of content (if known)
            is_contradicted: Whether the claim has been contradicted
            is_chit_chat: Whether the content is chit-chat

        Returns:
            True if content should never be promoted
        """
        if content_type and content_type.value in self.never_promote:
            return True

        if is_contradicted:
            return True

        if is_chit_chat:
            return True

        return False

    def should_promote(
        self,
        memory,
        extraction_confidence: Optional[float] = None,
        user_confirmed: bool = False,
        mention_count: int = 1,
    ) -> bool:
        """
        Determine if content should be promoted to memory.

        This is the main decision method that applies all promotion rules.

        Promotion rules per spec:
        - Facts: confidence >= 0.7 OR user_confirmed
        - Decisions: explicitly marked OR phrases ("we decided", "let's go with", "agreed on")
        - Preferences: "remember this" OR stated 2+ times
        - Procedures: successful execution trace + explicit success signal
        - Entities: mentioned 2+ times OR explicitly introduced

        Args:
            memory: Memory object to evaluate
            extraction_confidence: Confidence score from extraction
            user_confirmed: Whether user explicitly confirmed
            mention_count: How many times this was mentioned

        Returns:
            True if content should be promoted to memory
        """
        # If already user confirmed, always promote
        if user_confirmed or (hasattr(memory, "user_confirmed") and memory.user_confirmed):
            return True

        # Get memory class
        memory_class = getattr(memory, "memory_class", None)
        if memory_class is None:
            return False

        # Get memory type for specific rules
        memory_type = getattr(memory, "memory_type", None)

        # Apply class-specific promotion rules
        if memory_class == MemoryClass.SEMANTIC:
            return self._promote_fact(extraction_confidence, user_confirmed)

        elif memory_class == MemoryClass.DECISION:
            return self._promote_decision(memory)

        elif memory_class == MemoryClass.IDENTITY:
            return self._promote_preference(memory, mention_count)

        elif memory_class == MemoryClass.PROCEDURAL:
            return self._promote_procedure(memory)

        elif memory_class == MemoryClass.RELATIONAL:
            return self._promote_entity(memory, mention_count)

        elif memory_class == MemoryClass.EPISODIC:
            # Episodic memories are always promoted (they are the raw events)
            return True

        elif memory_class == MemoryClass.SUMMARY:
            # Summaries are always promoted (generated from raw events)
            return True

        # Default: promote based on confidence
        if extraction_confidence is not None:
            return extraction_confidence >= self.fact_confidence_threshold

        return False

    def _promote_fact(
        self,
        extraction_confidence: Optional[float],
        user_confirmed: bool,
    ) -> bool:
        """
        Promotion rule for facts: confidence >= 0.7 OR user_confirmed.

        Args:
            extraction_confidence: Confidence score from extraction
            user_confirmed: Whether user explicitly confirmed

        Returns:
            True if fact should be promoted
        """
        if user_confirmed:
            return True

        if extraction_confidence is not None:
            return extraction_confidence >= self.fact_confidence_threshold

        return False

    def _promote_decision(self, memory) -> bool:
        """
        Promotion rule for decisions: explicitly marked OR phrases.

        Checks content against decision phrase patterns.

        Args:
            memory: Memory object to evaluate

        Returns:
            True if decision should be promoted
        """
        content = getattr(memory, "content", "").lower()

        # Check for explicit marking (could be metadata)
        if getattr(memory, "is_explicit", False):
            return True

        # Check for decision phrases in content
        for phrase in DECISION_PHRASES:
            if phrase in content:
                return True

        # If explicitly marked decision type, promote
        memory_type = getattr(memory, "memory_type", None)
        if memory_type in ["architectural", "process", "technical", "preference"]:
            return True

        return False

    def _promote_preference(
        self,
        memory,
        mention_count: int,
    ) -> bool:
        """
        Promotion rule for preferences: "remember this" OR stated 2+ times.

        Args:
            memory: Memory object to evaluate
            mention_count: How many times mentioned

        Returns:
            True if preference should be promoted
        """
        content = getattr(memory, "content", "").lower()

        # Check for explicit preference markers
        for phrase in PREFERENCE_PHRASES:
            if phrase in content:
                return True

        # Check mention count
        if mention_count >= 2:
            return True

        # If marked as explicit preference type
        if getattr(memory, "is_explicit", False):
            return True

        return False

    def _promote_procedure(self, memory) -> bool:
        """
        Promotion rule for procedures: successful execution trace + explicit success signal.

        Args:
            memory: Memory object to evaluate

        Returns:
            True if procedure should be promoted
        """
        # Check for success signal
        has_success_signal = getattr(memory, "has_success_signal", False)

        # For procedures, can also check for workflow steps + success count
        has_workflow = hasattr(memory, "workflow_steps") and memory.workflow_steps
        has_success_count = hasattr(memory, "success_count") and memory.success_count > 0

        # Must have explicit success signal OR (workflow with successful execution)
        if has_success_signal:
            return True

        if has_workflow and has_success_count:
            return True

        return False

    def _promote_entity(
        self,
        memory,
        mention_count: int,
    ) -> bool:
        """
        Promotion rule for entities: mentioned 2+ times OR explicitly introduced.

        Args:
            memory: Memory object to evaluate
            mention_count: How many times mentioned

        Returns:
            True if entity should be promoted
        """
        # Check mention count
        if mention_count >= 2:
            return True

        # Check if explicitly introduced
        if getattr(memory, "is_explicit", False):
            return True

        # Check for introduction phrases
        content = getattr(memory, "content", "").lower()
        intro_phrases = ["this is", "i am", "meet", "introducing", "presented"]
        for phrase in intro_phrases:
            if phrase in content:
                return True

        return False

    def check_write_policy(
        self,
        content: str,
        extraction_result: Optional[ExtractionResult] = None,
    ) -> Dict[str, Any]:
        """
        Check write policy for given content.

        Args:
            content: The content to check
            extraction_result: Optional extraction result with metadata

        Returns:
            Dictionary with policy decision and details
        """
        result = {
            "should_store": False,
            "should_promote": False,
            "reason": "",
            "policy_details": {},
        }

        content_type = None
        if extraction_result:
            content_type = extraction_result.content_type

        # Step 1: Check if should always store
        if content_type and self.should_always_store(content_type):
            result["should_store"] = True
            result["should_promote"] = True  # Always store as raw events
            result["reason"] = f"always_store: {content_type.value}"
            result["policy_details"]["storage_type"] = "raw_event"
            return result

        # Step 2: Check if should never promote
        is_chit_chat = self._is_chit_chat(content)
        is_contradicted = (
            extraction_result.is_contradicted if extraction_result else False
        )

        if self.should_never_promote(
            content_type=content_type,
            is_contradicted=is_contradicted,
            is_chit_chat=is_chit_chat,
        ):
            result["should_store"] = False
            result["should_promote"] = False
            result["reason"] = "never_promote: " + (
                "contradicted" if is_contradicted else
                "chit_chat" if is_chit_chat else
                content_type.value if content_type else "unknown"
            )
            result["policy_details"]["violation"] = (
                "contradicted_claim" if is_contradicted else
                "chit_chat" if is_chit_chat else
                content_type.value if content_type else "unknown"
            )
            return result

        # Step 3: Check if should be promoted (selective promotion)
        if extraction_result:
            memory_class = extraction_result.memory_class or MemoryClass.SEMANTIC

            # Create a temporary memory object for promotion check
            temp_memory = type('TempMemory', (), {
                'memory_class': memory_class,
                'memory_type': extraction_result.memory_type,
                'content': content,
                'user_confirmed': extraction_result.user_confirmed,
                'confidence': extraction_result.confidence,
                'is_explicit': extraction_result.is_explicit,
                'has_success_signal': extraction_result.has_success_signal,
            })()

            should_promote = self.should_promote(
                temp_memory,
                extraction_confidence=extraction_result.confidence,
                user_confirmed=extraction_result.user_confirmed,
                mention_count=extraction_result.mention_count,
            )

            result["should_store"] = True
            result["should_promote"] = should_promote
            result["reason"] = "selective_promotion" if should_promote else "failed_promotion_criteria"
            result["policy_details"] = {
                "storage_type": "memory_item",
                "memory_class": memory_class.value,
                "confidence": extraction_result.confidence,
                "user_confirmed": extraction_result.user_confirmed,
                "mention_count": extraction_result.mention_count,
            }
        else:
            # No extraction result, default to storing but not promoting
            result["should_store"] = True
            result["should_promote"] = False
            result["reason"] = "store_only: no extraction metadata"

        return result

    def _is_chit_chat(self, content: str) -> bool:
        """
        Check if content is chit-chat.

        Args:
            content: Content to check

        Returns:
            True if content appears to be chit-chat
        """
        content_lower = content.lower()

        for pattern in CHIT_CHAT_PATTERNS:
            if re.search(pattern, content_lower):
                return True

        return False

    def classify_content_type(
        self,
        content: str,
        extraction_metadata: Optional[Dict[str, Any]] = None,
    ) -> ContentType:
        """
        Classify content type based on content and metadata.

        Args:
            content: Content to classify
            extraction_metadata: Optional metadata from extraction

        Returns:
            Classified ContentType
        """
        # Check extraction metadata first
        if extraction_metadata:
            explicit_type = extraction_metadata.get("content_type")
            if explicit_type:
                try:
                    return ContentType(explicit_type)
                except ValueError:
                    pass

        # Check for decision phrases
        content_lower = content.lower()
        for phrase in DECISION_PHRASES:
            if phrase in content_lower:
                return ContentType.DECISION

        # Check for preference phrases
        for phrase in PREFERENCE_PHRASES:
            if phrase in content_lower:
                return ContentType.PREFERENCE

        # Check for chit-chat
        if self._is_chit_chat(content):
            return ContentType.CHIT_CHAT

        # Default based on extraction metadata confidence
        if extraction_metadata:
            confidence = extraction_metadata.get("confidence", 0.5)
            if confidence < 0.5:
                return ContentType.LOW_CONFIDENCE_EXTRACTION

        return ContentType.FACT

    def compute_confidence(self, extraction_result: Dict) -> float:
        """
        Compute confidence score from extraction result.

        Factors: extraction_confidence, source_reliability, cross_references.

        Args:
            extraction_result: Dictionary with extraction metadata

        Returns:
            Computed confidence score between 0.0 and 1.0
        """
        extraction_confidence = extraction_result.get("extraction_confidence", 0.5)
        source_reliability = extraction_result.get("source_reliability", 0.5)
        cross_references = extraction_result.get("cross_references", 0.0)
        
        # Weighted average with emphasis on cross_references
        confidence = (
            extraction_confidence * 0.4 +
            source_reliability * 0.3 +
            min(cross_references, 1.0) * 0.3
        )
        
        return max(0.0, min(1.0, confidence))

    def detect_contradiction(
        self,
        new_fact: str,
        existing_facts: List[str],
    ) -> Optional[str]:
        """
        Detect if new fact contradicts existing facts.

        Args:
            new_fact: The new fact to check
            existing_facts: List of existing facts to compare against

        Returns:
            Contradiction reason string or None if no contradiction
        """
        new_fact_lower = new_fact.lower()
        
        # Simple keyword-based contradiction detection
        negation_words = {"not", "never", "no", "none", "without", "don't", "didn't", "won't", "can't"}
        
        for existing in existing_facts:
            existing_lower = existing.lower()
            
            # Check for direct negation patterns
            # e.g., "X is true" vs "X is not true"
            for neg_word in negation_words:
                if neg_word in existing_lower and neg_word not in new_fact_lower:
                    # Check if they share significant content words
                    new_words = set(new_fact_lower.split())
                    existing_words = set(existing_lower.split())
                    
                    # Remove common words
                    common_words = new_words & existing_words
                    significant_overlap = len([w for w in common_words if len(w) > 3])
                    
                    if significant_overlap >= 2:
                        return f"Contradicts existing fact: '{existing[:50]}...'"
            
            # Check for numeric contradictions (simple)
            import re
            new_nums = re.findall(r'\d+(?:\.\d+)?', new_fact)
            existing_nums = re.findall(r'\d+(?:\.\d+)?', existing)
            
            for nn in new_nums:
                for en in existing_nums:
                    if nn != en:
                        # Check if numbers relate to same subject
                        if any(w in existing_lower for w in new_fact_lower.split()[:3]):
                            return f"Numerical contradiction: {nn} vs {en}"
        
        return None

    async def detect_contradictions_with_llm(
        self,
        new_content: str,
        existing_memories: List[Dict[str, Any]],
        llm_service: Any = None
    ) -> List[Dict[str, Any]]:
        """Detect contradictions using LLM if available.

        Args:
            new_content: The new fact/content to check
            existing_memories: List of memory objects to compare against
            llm_service: Optional LLMExtractionService instance for LLM-based detection

        Returns:
            List of contradictions detected, each with details
        """
        # Import here to avoid circular imports
        from ..pipeline.llm_extraction import LLMExtractionService

        # Fall back to basic keyword matching if no LLM service
        if not llm_service:
            existing_facts = [m.get("content", "") for m in existing_memories]
            result = self.detect_contradiction(new_content, existing_facts)
            if result:
                return [{"existing_fact": result, "contradiction": True, "reason": result}]
            return []

        # Use LLM for enhanced contradiction detection
        existing_contents = [m.get("content", "") for m in existing_memories]

        # Check if llm_service is the class or an instance
        if isinstance(llm_service, type):
            # It's a class, try to create an instance
            try:
                llm_instance = llm_service()
                await llm_instance.initialize()
                contradictions = await llm_instance.detect_contradictions(new_content, existing_contents)
                await llm_instance.close()
                return contradictions
            except Exception:
                # Fall back to basic detection
                existing_facts = [m.get("content", "") for m in existing_memories]
                result = self.detect_contradiction(new_content, existing_facts)
                if result:
                    return [{"existing_fact": result, "contradiction": True, "reason": result}]
                return []
        else:
            # It's an instance, use it directly
            try:
                return await llm_service.detect_contradictions(new_content, existing_contents)
            except Exception:
                # Fall back to basic detection
                existing_facts = [m.get("content", "") for m in existing_memories]
                result = self.detect_contradiction(new_content, existing_facts)
                if result:
                    return [{"existing_fact": result, "contradiction": True, "reason": result}]
                return []

    def count_mentions(self, entity: str, session_history: List[Dict]) -> int:
        """
        Count how many times entity was mentioned in session history.

        Args:
            entity: The entity to count mentions of
            session_history: List of session messages/dicts

        Returns:
            Number of times the entity was mentioned
        """
        count = 0
        entity_lower = entity.lower()
        
        for item in session_history:
            if isinstance(item, dict):
                content = item.get("content", "")
                if isinstance(content, str) and entity_lower in content.lower():
                    count += 1
            elif isinstance(item, str):
                if entity_lower in item.lower():
                    count += 1
        
        return count

    def should_block_promotion(
        self,
        memory: Memory,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if promotion should be blocked and why.

        Checks: low confidence, contradiction, never_promote list.

        Args:
            memory: Memory object to evaluate

        Returns:
            Tuple of (should_block: bool, reason: Optional[str])
        """
        # Check confidence threshold
        if memory.confidence < 0.3:
            return True, f"Low confidence: {memory.confidence}"
        
        # Check if in never_promote (via content type detection)
        content = getattr(memory, "content", "")
        if self._is_chit_chat(content):
            return True, "Content is chit-chat"
        
        # Check for contradicted status
        if hasattr(memory, "status"):
            status = memory.status
            if isinstance(status, DecisionStatus) and status == DecisionStatus.REJECTED:
                return True, "Decision was rejected"
        
        # Check for extraction source
        extractor = getattr(memory, "extractor_name", "")
        if extractor in self.never_promote:
            return True, f"Extractor '{extractor}' is in never_promote list"
        
        return False, None

    def requires_human_confirmation(self, memory: Memory) -> bool:
        """
        Determine if human confirmation is required before promotion.

        Requires for: confidence < 0.5, contradiction detected, sensitive topics.

        Args:
            memory: Memory object to evaluate

        Returns:
            True if human confirmation is required
        """
        # Low confidence
        if memory.confidence < 0.5:
            return True
            
        # Decisions always require human confirmation in the current policy
        if isinstance(memory, DecisionMemory):
            return True
        
        # Sensitive topics detection
        sensitive_keywords = [
            "password", "secret", "api_key", "token", "credential",
            "personal", "private", "confidential", "admin", "root",
        ]
        content = getattr(memory, "content", "").lower()
        if any(keyword in content for keyword in sensitive_keywords):
            return True
        
        # Check memory class specific rules
        memory_class = getattr(memory, "memory_class", None)
        if memory_class == MemoryClass.DECISION:
            # Decisions always need verification
            return True
        
        if memory_class == MemoryClass.IDENTITY:
            # Identity changes need human confirmation
            return True
        
        return False

    # Raw history preservation methods
    
    def persist_raw_extraction(self, extraction: Dict) -> str:
        """
        Persist extraction to raw history (always called, regardless of promotion).
        
        IMPORTANT: This ensures low-quality extractions are NEVER deleted.
        They remain in the raw history tables with full provenance.
        
        Args:
            extraction: Dictionary containing extraction data
            
        Returns:
            Extraction ID (for later promotion lookup)
        """
        extraction_id = str(uuid4())
        
        # Store raw extraction data (in real implementation, this would be a DB call)
        # For now, we track it in memory
        if not hasattr(self, '_raw_extractions'):
            self._raw_extractions: Dict[str, Dict] = {}
        
        self._raw_extractions[extraction_id] = {
            "id": extraction_id,
            "data": extraction,
            "persisted_at": datetime.utcnow(),
            "promoted": False,
            "promotion_blocked": False,
            "block_reason": None,
        }
        
        return extraction_id

    def promote_to_memory(
        self,
        extraction_id: str,
        memory: Optional[Memory] = None,
    ) -> Optional[str]:
        """
        Promote a raw extraction to durable memory if policy allows.
        
        Args:
            extraction_id: ID of the raw extraction to promote
            memory: Optional pre-created Memory object
            
        Returns:
            Memory item ID if promoted, None if blocked
        """
        if not hasattr(self, '_raw_extractions'):
            return None
            
        raw_extraction = self._raw_extractions.get(extraction_id)
        if not raw_extraction:
            return None
        
        # Check if promotion should be blocked
        if memory:
            should_block, reason = self.should_block_promotion(memory)
            if should_block:
                raw_extraction["promotion_blocked"] = True
                raw_extraction["block_reason"] = reason
                return None
        
        # Mark as promoted
        raw_extraction["promoted"] = True
        raw_extraction["promoted_at"] = datetime.utcnow()
        
        # Return a memory item ID (in real implementation, this would be a DB insert)
        return str(uuid4())


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT ISOLATION & MEMORY ACCESS CONTROL
# ═══════════════════════════════════════════════════════════════════════════════


class AgentIsolationPolicy:
    """
    Agent-specific memory isolation and access control.

    Provides methods for:
    - Checking if agent is the coordinator (Albert)
    - Checking if memory is private to an agent
    - Determining if an agent can access a memory
    - Promoting agent memory to team-shared
    - Managing team-based memory access

    Privacy Rules:
    - Agent-private: only the owner can access
    - Team-shared: accessible to all team members
    - Coordinator (Albert) cannot see other agents' private memories by default
    - Memories must be explicitly shared to be visible across agents
    """

    # Coordinator agent ID - Albert has full team visibility
    COORDINATOR_ID = 'agent-albert-uuid'

    def is_coordinator(self, agent_id: str) -> bool:
        """
        Check if agent is the coordinator (Albert).

        The coordinator has visibility into all team members' private memories,
        in addition to standard team+own access.

        Args:
            agent_id: The agent ID to check

        Returns:
            True if agent is the coordinator
        """
        return agent_id == self.COORDINATOR_ID

    def is_agent_private(self, memory, agent_id: str) -> bool:
        """
        Check if memory is private to this agent.

        Args:
            memory: Memory object to check
            agent_id: The agent ID to check against

        Returns:
            True if memory is private to this agent
        """
        agent_id_field = getattr(memory, "agent_id", None)
        visibility = getattr(memory, "visibility", getattr(memory, "visibility_scope", "agent"))

        if agent_id_field is None:
            return False

        return str(agent_id_field) == agent_id and visibility == "agent"

    def can_agent_access(self, memory, agent_id: str, team_member_ids: List[str]) -> bool:
        """
        Check if agent can access this memory.

        Coordinator Exception: Albert (coordinator) can access all team members'
        private memories in addition to standard visibility rules.

        Args:
            memory: Memory object to check
            agent_id: The agent ID requesting access
            team_member_ids: List of team member agent IDs

        Returns:
            True if the agent can access this memory
        """
        visibility = getattr(memory, "visibility", getattr(memory, "visibility_scope", "agent"))
        agent_id_field = getattr(memory, "agent_id", None)
        shared_with = getattr(memory, "shared_with", [])

        # Public is accessible to everyone
        if visibility == "public":
            return True

        # Check if explicitly shared with this agent
        if agent_id in shared_with:
            return True

        # Agent-private: only the owner can access
        # Even coordinator (Albert) cannot see other agents' private memories by default
        if visibility == "agent":
            if agent_id_field is None:
                return True  # No agent_id means it's not agent-specific
            # Owner can always access their own private memory
            if str(agent_id_field) == agent_id:
                return True
            # No exceptions - private is private
            return False

        # Team-shared: accessible to team members
        if visibility == "team":
            return agent_id in team_member_ids or str(agent_id_field) == agent_id

        # Tenant/org/project: check if agent belongs to same tenant
        if visibility in ("tenant", "org", "project"):
            return True

        # Personal scope
        if visibility == "personal":
            return str(agent_id_field) == agent_id if agent_id_field else True

        return False

    def promote_to_team_memory(
        self,
        memory,
        team_member_ids: List[str],
    ) -> Memory:
        """
        Promote an agent's memory to team-shared.

        Args:
            memory: Memory object to promote
            team_member_ids: List of team member agent IDs

        Returns:
            The modified memory object with team sharing enabled
        """
        memory.visibility = "team"
        memory.is_team_memory = True
        memory.shared_with = list(team_member_ids)

        # Also update visibility_scope for compatibility
        if hasattr(memory, "visibility_scope"):
            memory.visibility_scope = "team"

        return memory

    def demote_to_agent_private(self, memory) -> Memory:
        """
        Demote a team memory to agent-private.

        Args:
            memory: Memory object to demote

        Returns:
            The modified memory object with agent-only access
        """
        memory.visibility = "agent"
        memory.is_team_memory = False
        memory.shared_with = []

        if hasattr(memory, "visibility_scope"):
            memory.visibility_scope = "agent"

        return memory

    def filter_memories_for_agent(
        self,
        memories: List[Memory],
        agent_id: str,
        team_member_ids: List[str],
    ) -> List[Memory]:
        """
        Filter a list of memories to only those accessible by the agent.

        Args:
            memories: List of memory objects to filter
            agent_id: The agent ID requesting access
            team_member_ids: List of team member agent IDs

        Returns:
            List of memories the agent can access
        """
        return [
            mem for mem in memories
            if self.can_agent_access(mem, agent_id, team_member_ids)
        ]

    def get_agent_private_memories(
        self,
        memories: List[Memory],
        agent_id: str,
    ) -> List[Memory]:
        """
        Get memories that are private to a specific agent.

        Args:
            memories: List of memory objects
            agent_id: The agent ID to filter by

        Returns:
            List of memories private to that agent
        """
        return [
            mem for mem in memories
            if self.is_agent_private(mem, agent_id)
        ]

    def get_team_shared_memories(
        self,
        memories: List[Memory],
        team_member_ids: List[str],
    ) -> List[Memory]:
        """
        Get memories that are shared with the team.

        Args:
            memories: List of memory objects
            team_member_ids: List of team member agent IDs

        Returns:
            List of team-shared memories
        """
        return [
            mem for mem in memories
            if getattr(mem, "visibility", "") == "team" or getattr(mem, "is_team_memory", False)
        ]

    def share_with_agent(
        self,
        memory,
        target_agent_id: str,
    ) -> Memory:
        """
        Share a memory with a specific agent.

        Args:
            memory: Memory object to share
            target_agent_id: Agent ID to share with

        Returns:
            The modified memory object
        """
        if not hasattr(memory, "shared_with"):
            memory.shared_with = []

        if target_agent_id not in memory.shared_with:
            memory.shared_with.append(target_agent_id)

        return memory

    def revoke_from_agent(
        self,
        memory,
        target_agent_id: str,
    ) -> Memory:
        """
        Revoke a memory from a specific agent.

        Args:
            memory: Memory object to revoke
            target_agent_id: Agent ID to revoke from

        Returns:
            The modified memory object
        """
        if hasattr(memory, "shared_with") and target_agent_id in memory.shared_with:
            memory.shared_with.remove(target_agent_id)

        return memory


# Default agent isolation policy instance
default_agent_isolation = AgentIsolationPolicy()


# ═══════════════════════════════════════════════════════════════════════════════
# WRITE POLICY INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

# Default write policy instance
default_write_policy = WritePolicy()


def should_promote(
    memory,
    extraction_confidence: Optional[float] = None,
    user_confirmed: bool = False,
    mention_count: int = 1,
) -> bool:
    """Convenience function to check promotion."""
    return default_write_policy.should_promote(
        memory, extraction_confidence, user_confirmed, mention_count
    )


def check_write_policy(
    content: str,
    extraction_result: Optional[ExtractionResult] = None,
) -> Dict[str, Any]:
    """Convenience function to check write policy."""
    return default_write_policy.check_write_policy(content, extraction_result)


def classify_content_type(
    content: str,
    extraction_metadata: Optional[Dict[str, Any]] = None,
) -> ContentType:
    """Convenience function to classify content type."""
    return default_write_policy.classify_content_type(content, extraction_metadata)