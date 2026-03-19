"""Intent classification for query routing in BrainClaw Memory System.

This module classifies user queries into intent types to enable policy-based
retrieval across PostgreSQL, Weaviate, and Neo4j stores.
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple


class Intent(str, Enum):
    """Supported intent types for memory retrieval (FR-021)."""
    FACT_LOOKUP = "fact_lookup"
    DECISION_RECALL = "decision_recall"
    RELATIONSHIP_QUERY = "relationship_query"
    CHANGE_DETECTION = "change_detection"
    OWNERSHIP_QUERY = "ownership_query"
    PROCEDURAL_RECALL = "procedural_recall"
    # FR-021 additions:
    ISSUE_EVENT_RECALL = "issue_event_recall"
    PREFERENCE_CONSTRAINT_RECALL = "preference_constraint_recall"
    CONTRADICTION_REVIEW = "contradiction_review"
    DRILL_DOWN_REQUEST = "drill_down_request"


@dataclass
class ClassificationResult:
    """Result of intent classification."""
    primary_intent: Intent
    confidence: float
    all_intents: List[Tuple[Intent, float]] = field(default_factory=list)
    route_log: str = ""  # FR-021: observable route selection


# Intent patterns based on spec
INTENT_PATTERNS: Dict[Intent, List[str]] = {
    Intent.FACT_LOOKUP: [
        r'\bwhat is\b',
        r'\bwhat are\b',
        r'\bdefine\b',
        r'\btell me about\b',
        r'\bexplain\b',
        r'\bdescribe\b',
        r'\bwhat does\b',
        r'\bwhat do you know about\b',
    ],
    Intent.DECISION_RECALL: [
        r'\bwhat did we decide\b',
        r'\bwhat was decided\b',
        r'\bwhy did we\b',
        r'\bwhy did they\b',
        r'\bdecision about\b',
        r'\bchose to\b',
        r'\bwent with\b',
        r'\bagreed to\b',
        r'\bdecided to\b',
        r'\bwe decided\b',
        r'\bdecision\b',
    ],
    Intent.RELATIONSHIP_QUERY: [
        r'\bhow does\b',
        r'\bhow is\b',
        r'\brelated to\b',
        r'\bconnected to\b',
        r'\bdepends on\b',
        r'\blink to\b',
        r'\bdepends upon\b',
        r'\brelationship\b',
        r'\bassociation\b',
    ],
    Intent.CHANGE_DETECTION: [
        r'\bwhat changed\b',
        r'\bwhen did\b',
        r'\bhistory of\b',
        r'\bevolution of\b',
        r'\bprogression\b',
        r'\bupdates?\b',
        r'\bmodified\b',
        r'\bchanged\b',
    ],
    Intent.OWNERSHIP_QUERY: [
        r'\bwho knows\b',
        r'\bwho has\b',
        r'\bwho worked on\b',
        r'\bwho decided\b',
        r'\bwho created\b',
        r'\bwho owns\b',
        r'\bwho is responsible\b',
        r'\bwho can\b',
        r'\bwhose\b',
    ],
    Intent.PROCEDURAL_RECALL: [
        r'\bhow do i\b',
        r'\bhow to\b',
        r'\bsteps to\b',
        r'\bprocess for\b',
        r'\bworkflow for\b',
        r'\binstructions\b',
        r'\btutorial\b',
        r'\b guide\b',
    ],
    # FR-021 additions:
    Intent.ISSUE_EVENT_RECALL: [
        r'\bwhat issue\b',
        r'\bwhat error\b',
        r'\bwhat bug\b',
        r'\bwhat happened\b',
        r'\bwhat event\b',
        r'\bwhat problem\b',
        r'\bincident\b',
        r'\bfailure\b',
        r'\bissue with\b',
    ],
    Intent.PREFERENCE_CONSTRAINT_RECALL: [
        r'\bwhat.*prefer\b',
        r'\bpreference for\b',
        r'\bconstraint on\b',
        r'\brule about\b',
        r'\bmust not\b',
        r'\brequired to\b',
        r'\bnever.*should\b',
        r'\balways.*must\b',
        r'\bguideline\b',
    ],
    Intent.CONTRADICTION_REVIEW: [
        r'\bcontradiction\b',
        r'\bconflict.*with\b',
        r'\binconsisten\b',
        r'\bdisagree\b',
        r'\bcontradicts\b',
        r'\bopposite of\b',
        r'\bpreviously said\b',
    ],
    Intent.DRILL_DOWN_REQUEST: [
        r'\btell me more\b',
        r'\bexpand on\b',
        r'\bdetails about\b',
        r'\bmore detail\b',
        r'\bdrill down\b',
        r'\bfull context\b',
        r'\boriginal conversation\b',
        r'\bsource of\b',
    ],
}

# Additional context words that can boost confidence
INTENT_BOOSTERS: Dict[Intent, List[str]] = {
    Intent.DECISION_RECALL: [
        'decision', 'decided', 'chose', 'agreed', 'chosen', 'alternative'
    ],
    Intent.RELATIONSHIP_QUERY: [
        'relationship', 'connect', 'link', 'depend', 'relate', '关联', '联系'
    ],
    Intent.CHANGE_DETECTION: [
        'change', 'update', 'evolve', 'history', 'timeline', 'previous', 'before', 'after'
    ],
    Intent.OWNERSHIP_QUERY: [
        'who', 'owner', 'responsible', 'created by', 'author', 'maintainer'
    ],
    Intent.PROCEDURAL_RECALL: [
        'how', 'steps', 'process', 'procedure', 'method', 'guide', 'tutorial'
    ],
    Intent.ISSUE_EVENT_RECALL: [
        'issue', 'bug', 'error', 'problem', 'incident', 'failure', 'event', 'happened'
    ],
    Intent.PREFERENCE_CONSTRAINT_RECALL: [
        'prefer', 'preference', 'constraint', 'rule', 'must', 'never', 'always', 'guideline'
    ],
    Intent.CONTRADICTION_REVIEW: [
        'contradiction', 'conflict', 'inconsistent', 'disagree', 'opposite'
    ],
    Intent.DRILL_DOWN_REQUEST: [
        'expand', 'detail', 'more', 'drill', 'source', 'original', 'context'
    ],
}


class IntentClassifier:
    """Classifier for determining user query intent.
    
    Uses pattern matching and keyword boosting to classify queries
    into intent types for policy-based retrieval routing.
    """
    
    def __init__(self):
        """Initialize the classifier with compiled regex patterns."""
        self._compiled_patterns: Dict[Intent, List[re.Pattern]] = {}
        for intent, patterns in INTENT_PATTERNS.items():
            self._compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    def classify(self, query: str) -> ClassificationResult:
        """Classify a query into intent types.
        
        Args:
            query: The user's query string.
            
        Returns:
            ClassificationResult with primary intent, confidence, and all matches.
        """
        query_lower = query.lower()
        
        # Score each intent based on pattern matches
        intent_scores: Dict[Intent, float] = {}
        
        for intent, patterns in self._compiled_patterns.items():
            score = 0.0
            matches = 0
            
            for pattern in patterns:
                if pattern.search(query):
                    score += 1.0
                    matches += 1
            
            # Apply boosters for context words
            if intent in INTENT_BOOSTERS:
                for booster in INTENT_BOOSTERS[intent]:
                    if booster.lower() in query_lower:
                        score += 0.3
            
            if matches > 0:
                # Normalize score based on number of patterns
                base_score = min(score / max(len(patterns), 1), 1.0)
                intent_scores[intent] = base_score
        
        if not intent_scores:
            # Default to FACT_LOOKUP for unknown queries
            return ClassificationResult(
                primary_intent=Intent.FACT_LOOKUP,
                confidence=0.3,
                all_intents=[(Intent.FACT_LOOKUP, 0.3)]
            )
        
        # Sort by score and get top intent
        sorted_intents = sorted(
            intent_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        primary_intent = sorted_intents[0][0]
        primary_score = sorted_intents[0][1]
        
        # Add slight boost to primary if it has strong matches
        confidence = min(primary_score * 0.9 + 0.1, 1.0)
        
        # Format all intents as tuples
        all_intents = [(intent, score) for intent, score in sorted_intents]
        
        # FR-021: Log route selection for observability and testability
        route_log = (
            f"intent={primary_intent.value} confidence={confidence:.3f} "
            f"candidates={len(sorted_intents)} query_len={len(query)}"
        )

        return ClassificationResult(
            primary_intent=primary_intent,
            confidence=confidence,
            all_intents=all_intents,
            route_log=route_log,
        )
    
    def classify_multiple(self, query: str, top_k: int = 2) -> List[Tuple[Intent, float]]:
        """Classify and return top-k matching intents.
        
        Args:
            query: The user's query string.
            top_k: Number of top intents to return.
            
        Returns:
            List of (Intent, confidence) tuples sorted by confidence.
        """
        result = self.classify(query)
        return result.all_intents[:top_k]


# Default classifier instance for convenience
_default_classifier: IntentClassifier = IntentClassifier()


def classify(query: str) -> ClassificationResult:
    """Convenience function for classifying a query using default classifier.
    
    Args:
        query: The user's query string.
        
    Returns:
        ClassificationResult with intent classification.
    """
    return _default_classifier.classify(query)


def classify_multiple(query: str, top_k: int = 2) -> List[Tuple[Intent, float]]:
    """Convenience function for multiple intent classification.
    
    Args:
        query: The user's query string.
        top_k: Number of top intents to return.
        
    Returns:
        List of (Intent, confidence) tuples.
    """
    return _default_classifier.classify_multiple(query, top_k)