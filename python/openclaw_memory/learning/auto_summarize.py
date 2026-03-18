"""
Auto-summarization of old episodic memories.

This module provides automatic summarization of old episodic memories
using LLM to condense multiple events into summary memories.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import aiohttp
import json
import re


@dataclass
class SummarizationConfig:
    """Configuration for auto-summarization."""
    min_memories_to_summarize: int = 5  # Minimum memories to trigger summary
    max_age_days: int = 30  # Summarize memories older than this
    min_confidence: float = 0.5  # Only summarize memories with this confidence
    summary_window_days: int = 7  # Group memories within this window
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2"


class AutoSummarizationService:
    """Automatically summarize old episodic memories."""

    def __init__(self, config: SummarizationConfig, storage_client):
        self.config = config
        self._storage = storage_client
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

    async def find_summarizable_memories(self) -> List[Dict[str, Any]]:
        """Find memories that can be summarized."""
        cutoff_date = datetime.utcnow() - timedelta(days=self.config.max_age_days)

        # Get episodic memories older than cutoff
        memories = await self._storage.get_memories_by_class_and_date(
            memory_class="episodic",
            before_date=cutoff_date,
            min_confidence=self.config.min_confidence
        )

        return memories

    async def group_memories_by_window(
        self,
        memories: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Group memories into time windows for summarization."""
        if not memories:
            return []

        # Sort by creation date
        sorted_memories = sorted(memories, key=lambda m: m["created_at"])

        windows = []
        current_window = [sorted_memories[0]]
        window_start = sorted_memories[0]["created_at"]

        for memory in sorted_memories[1:]:
            # Check if within window
            if (memory["created_at"] - window_start).days <= self.config.summary_window_days:
                current_window.append(memory)
            else:
                # Start new window
                if len(current_window) >= self.config.min_memories_to_summarize:
                    windows.append(current_window)
                current_window = [memory]
                window_start = memory["created_at"]

        # Add last window
        if len(current_window) >= self.config.min_memories_to_summarize:
            windows.append(current_window)

        return windows

    async def summarize_window(
        self,
        memories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Summarize a window of memories using LLM."""
        memory_contents = [m["content"] for m in memories]
        memory_ids = [m["id"] for m in memories]

        prompt = f"""Summarize the following memories into a concise summary. 
Extract key facts, decisions, and relationships.

Memories:
{chr(10).join(f"- {c}" for c in memory_contents)}

Return format:
{{
  "summary": "Concise summary of the memories",
  "key_facts": ["fact1", "fact2"],
  "decisions": ["decision1", "decision2"],
  "entities": ["entity1", "entity2"]
}}

Only return the JSON object."""

        try:
            async with self._session.post(
                f"{self.config.ollama_base_url}/api/generate",
                json={
                    "model": self.config.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 512
                    }
                }
            ) as resp:
                if resp.status != 200:
                    return self._fallback_summary(memories)

                data = await resp.json()
                response_text = data.get("response", "{}")

                # Extract JSON
                summary_json = self._extract_json(response_text)
                if not summary_json:
                    return self._fallback_summary(memories)

                return {
                    "content": summary_json.get("summary", ""),
                    "key_facts": summary_json.get("key_facts", []),
                    "decisions": summary_json.get("decisions", []),
                    "entities": summary_json.get("entities", []),
                    "source_memory_ids": memory_ids,
                    "confidence": 0.8,  # Summaries have reasonable confidence
                    "created_at": datetime.utcnow()
                }

        except Exception:
            return self._fallback_summary(memories)

    def _fallback_summary(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fallback to simple concatenation if LLM fails."""
        contents = [m["content"] for m in memories]
        return {
            "content": " ".join(contents[:3]) + ("..." if len(contents) > 3 else ""),
            "key_facts": [],
            "decisions": [],
            "entities": [],
            "source_memory_ids": [m["id"] for m in memories],
            "confidence": 0.5,  # Lower confidence for fallback
            "created_at": datetime.utcnow()
        }

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON object from LLM response."""
        # Look for JSON object
        obj_match = re.search(r'\{[\s\S]*\}', text)
        if obj_match:
            try:
                return json.loads(obj_match.group())
            except json.JSONDecodeError:
                pass

        return None

    async def run_summarization(self) -> Dict[str, Any]:
        """Run auto-summarization process."""
        # Find summarizeable memories
        memories = await self.find_summarizable_memories()

        if len(memories) < self.config.min_memories_to_summarize:
            return {
                "status": "skipped",
                "reason": "Not enough memories to summarize",
                "memory_count": len(memories)
            }

        # Group by time window
        windows = await self.group_memories_by_window(memories)

        summaries_created = 0
        memories_summarized = 0

        for window in windows:
            # Generate summary
            summary = await self.summarize_window(window)

            # Store summary memory
            summary_id = await self._storage.insert_memory({
                "memory_class": "summary",
                "content": summary["content"],
                "confidence": summary["confidence"],
                "metadata": {
                    "key_facts": summary["key_facts"],
                    "decisions": summary["decisions"],
                    "entities": summary["entities"],
                    "source_memory_ids": summary["source_memory_ids"],
                    "summarized_at": summary["created_at"].isoformat()
                }
            })

            # Mark source memories as summarized (superseded)
            for memory in window:
                await self._storage.update_state(
                    memory["id"],
                    "superseded",
                    reason=f"Summarized into {summary_id}"
                )
                memories_summarized += 1

            summaries_created += 1

        return {
            "status": "success",
            "summaries_created": summaries_created,
            "memories_summarized": memories_summarized,
            "windows_processed": len(windows)
        }