"""
Active learning loop for memory system improvement.

This module provides feedback-driven confidence adjustment for memories,
enabling the system to learn from retrieval success/failure patterns.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import math


@dataclass
class RetrievalFeedback:
    """Feedback from a retrieval event."""
    memory_id: str
    query: str
    retrieved: bool
    clicked: bool = False
    used: bool = False
    user_rating: Optional[int] = None  # 1-5 stars
    session_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LearningConfig:
    """Configuration for active learning."""
    confidence_boost_used: float = 0.05  # Boost when memory is used
    confidence_boost_clicked: float = 0.03  # Boost when memory is clicked
    confidence_decay_rate: float = 0.001  # Daily decay
    min_confidence: float = 0.1
    max_confidence: float = 1.0
    mention_boost_threshold: int = 3  # Boost after N mentions


class ActiveLearningService:
    """Manage learning from retrieval feedback."""

    def __init__(self, config: LearningConfig, storage_client):
        self.config = config
        self._storage = storage_client
        self._pending_feedback: List[RetrievalFeedback] = []

    async def record_retrieval(
        self,
        memory_id: str,
        query: str,
        session_id: str
    ) -> None:
        """Record that a memory was retrieved."""
        feedback = RetrievalFeedback(
            memory_id=memory_id,
            query=query,
            retrieved=True,
            session_id=session_id
        )
        self._pending_feedback.append(feedback)

    async def record_click(
        self,
        memory_id: str,
        query: str,
        session_id: str
    ) -> None:
        """Record that a user clicked on a retrieved memory."""
        feedback = RetrievalFeedback(
            memory_id=memory_id,
            query=query,
            retrieved=True,
            clicked=True,
            session_id=session_id
        )
        self._pending_feedback.append(feedback)

    async def record_usage(
        self,
        memory_id: str,
        query: str,
        session_id: str
    ) -> None:
        """Record that a memory was actually used (cited, referenced, acted upon)."""
        feedback = RetrievalFeedback(
            memory_id=memory_id,
            query=query,
            retrieved=True,
            clicked=True,
            used=True,
            session_id=session_id
        )
        self._pending_feedback.append(feedback)

        # Immediately boost confidence for usage
        await self._boost_confidence(memory_id, self.config.confidence_boost_used)

    async def record_rating(
        self,
        memory_id: str,
        query: str,
        rating: int,
        session_id: str
    ) -> None:
        """Record user rating for a memory."""
        feedback = RetrievalFeedback(
            memory_id=memory_id,
            query=query,
            retrieved=True,
            clicked=True,
            user_rating=rating,
            session_id=session_id
        )
        self._pending_feedback.append(feedback)

        # Boost based on rating (1-5 stars)
        boost = (rating - 3) * 0.02  # -0.04 to +0.04
        if boost > 0:
            await self._boost_confidence(memory_id, boost)

    async def _boost_confidence(self, memory_id: str, boost: float) -> None:
        """Boost memory confidence."""
        # Get current confidence
        current = await self._storage.get_confidence(memory_id)
        new_confidence = min(
            self.config.max_confidence,
            current + boost
        )
        await self._storage.update_confidence(memory_id, new_confidence)

    async def process_pending_feedback(self) -> int:
        """Process all pending feedback and update confidences."""
        processed = 0

        for feedback in self._pending_feedback:
            # Calculate confidence change
            delta = 0.0

            if feedback.used:
                delta += self.config.confidence_boost_used
            elif feedback.clicked:
                delta += self.config.confidence_boost_clicked

            if feedback.user_rating:
                delta += (feedback.user_rating - 3) * 0.01

            # Apply decay based on time since last update
            delta = delta * (1.0 - self.config.confidence_decay_rate)

            # Update confidence
            if delta != 0:
                await self._boost_confidence(feedback.memory_id, delta)

            processed += 1

        # Clear pending feedback
        self._pending_feedback.clear()

        return processed

    async def apply_decay(self) -> int:
        """Apply time-based confidence decay to all memories."""
        # Get all memories
        memories = await self._storage.get_all_memories()

        decayed = 0
        for memory in memories:
            # Calculate days since creation
            days_old = (datetime.utcnow() - memory.created_at).days

            # Apply exponential decay
            decay = math.exp(-self.config.confidence_decay_rate * days_old)
            new_confidence = max(
                self.config.min_confidence,
                memory.confidence * decay
            )

            if new_confidence != memory.confidence:
                await self._storage.update_confidence(memory.id, new_confidence)
                decayed += 1

        return decayed

    async def promote_high_confidence(self) -> int:
        """Promote memories that exceed confidence threshold from Raw to Active."""
        # Get Raw memories with high confidence
        threshold = 0.7  # Promotion threshold
        raw_memories = await self._storage.get_memories_by_state("raw")

        promoted = 0
        for memory in raw_memories:
            if memory.confidence >= threshold:
                await self._storage.update_state(memory.id, "active")
                promoted += 1

        return promoted

    async def get_learning_stats(self) -> Dict[str, Any]:
        """Get statistics about learning progress."""
        return {
            "pending_feedback": len(self._pending_feedback),
            "total_stored": await self._storage.count_memories(),
            "average_confidence": await self._storage.get_average_confidence(),
            "by_state": await self._storage.count_by_state(),
            "by_class": await self._storage.count_by_memory_class()
        }