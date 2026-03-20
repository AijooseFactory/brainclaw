"""Knowledge distillation service for BrainClaw.

This module implements the 'Continual Intelligence' loop, synthesizing 
high-level Knowledge Items (KIs) from memory clusters (Leiden communities).
Follows research standards for Trajectory-Informed Memory and LazyGraphRAG.
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from ..storage.postgres import PostgresClient, MemoryItem
from ..storage.neo4j_client import Neo4jClient
from ..graph.communities import CommunityDetector
from ..graph.summarize import CommunitySummarizer

logger = logging.getLogger("openclaw.learning.distiller")

# Translation from research sub-kinds to memory_type
KNOWLEDGE_SUBTYPES = {
    "best_practice": "Best Practice",
    "recovery_tip": "Recovery Tip",
    "rule_of_thumb": "Rule of Thumb",
    "optimization_tip": "Optimization Tip"
}

class KnowledgeDistiller:
    """Distills hierarchical knowledge from GraphRAG communities.
    
    Implements a 'Lazy' trigger policy and provenance-heavy synthesis.
    """
    
    def __init__(
        self,
        postgres: PostgresClient,
        neo4j: Neo4jClient,
        llm_client: Any,
        data_dir: str = "/tmp/brainclaw_intel",
        lazy_threshold: int = 50,
        cooldown_hours: int = 4
    ):
        self.postgres = postgres
        self.neo4j = neo4j
        self.llm = llm_client
        self.data_dir = data_dir
        self.lazy_threshold = lazy_threshold
        self.cooldown_hours = cooldown_hours
        self.detector = CommunityDetector(neo4j)
        self.summarizer = CommunitySummarizer(llm_client, postgres, neo4j, self.detector)
        
        os.makedirs(self.data_dir, exist_ok=True)
        self.state_path = os.path.join(self.data_dir, "distillation_state.json")
        self._load_state()

    def _load_state(self):
        """Load the lazy distillation state."""
        if os.path.exists(self.state_path):
            with open(self.state_path, "r") as f:
                self.state = json.load(f)
        else:
            self.state = {
                "last_distillation_at": None,
                "promoted_since_last": 0,
                "community_cooldowns": {}
            }

    def _save_state(self):
        """Save the lazy distillation state."""
        with open(self.state_path, "w") as f:
            json.dump(self.state, f)

    async def record_promotion(self, count: int = 1):
        """Record that new memories have been promoted to 'Active'."""
        self.state["promoted_since_last"] += count
        self._save_state()

    async def should_distill(self) -> bool:
        """Check if distillation should run based on the Lazy policy."""
        # Policy: 50 promoted OR 4-6 hours passed
        if self.state["promoted_since_last"] >= self.lazy_threshold:
            return True
            
        if not self.state["last_distillation_at"]:
            return True
            
        last_run = datetime.fromisoformat(self.state["last_distillation_at"])
        if datetime.utcnow() - last_run >= timedelta(hours=self.cooldown_hours):
            return True
            
        return False

    async def distill(self, tenant_id: Optional[str] = None) -> List[MemoryItem]:
        """Run the incremental distillation loop."""
        if not await self.should_distill():
            logger.info("Skipping distillation: threshold not met (Lazy policy).")
            return []

        logger.info("Starting 'Continual Intelligence' distillation loop...")
        
        # 1. Selection: Find high-quality communities
        communities = await self.detector.get_all_communities(tenant_id)
        selected_communities = []
        
        for cid in communities:
            # Check cooldown for this specific community
            cooldown_key = f"{tenant_id or 'global'}_{cid}"
            last_cid_run = self.state["community_cooldowns"].get(cooldown_key)
            if last_cid_run:
                last_dt = datetime.fromisoformat(last_cid_run)
                if datetime.utcnow() - last_dt < timedelta(hours=self.cooldown_hours * 2):
                    continue

            stats = await self.detector.get_community_stats(cid, tenant_id)
            
            # Criteria: Support Threshold (>3 nodes) and Stability (Density > 0.1)
            if stats["node_count"] >= 3 and stats["density"] >= 0.1:
                selected_communities.append(cid)

        # Limit to top 5 per run for budget/rate limit safety
        selected_communities = selected_communities[:5]
        
        new_kis = []
        for cid in selected_communities:
            ki = await self._synthesize_ki(cid, tenant_id)
            if ki:
                new_kis.append(ki)
                self.state["community_cooldowns"][f"{tenant_id or 'global'}_{cid}"] = datetime.utcnow().isoformat()

        # Update state
        self.state["last_distillation_at"] = datetime.utcnow().isoformat()
        self.state["promoted_since_last"] = 0
        self._save_state()
        
        return new_kis

    async def _synthesize_ki(self, community_id: int, tenant_id: Optional[str]) -> Optional[MemoryItem]:
        """Synthesize a Knowledge Item from a community subgraph."""
        subgraph = await self.detector.get_community_subgraph(community_id, tenant_id)
        context = self.summarizer._format_community_context(community_id, subgraph["nodes"], subgraph["edges"])
        
        prompt = f"""You are a 'Knowledge Distiller' for the BrainClaw Memory System.
Your task is to transform a cluster of related memories (a community) into a high-level, actionable Knowledge Item.

CONTEXT FROM COMMUNITY {community_id}:
{context}

FOLLOW THESE RULES:
1. Identify the 'Wisdom': What is the recurring successful strategy or common recovery procedure here?
2. categorize the knowledge into exactly ONE of these types:
   - best_practice: A general policy for success.
   - recovery_tip: How to fix a specific known error or failure pattern.
   - rule_of_thumb: A useful heuristic for decision making.
   - optimization_tip: How to improve performance or reliability.
3. Be concise and authoritative. 

OUTPUT FORMAT (JSON):
{{
  "subtype": "one of the types above",
  "title": "A short, descriptive title",
  "content": "The actionable rule or advice",
  "confidence": 0.0 to 1.0 based on how consistent the community is
}}
"""

        try:
            # Use the summarizer's existing LLM logic as a bridge
            response_text = await self.summarizer._generate_summary_with_llm(prompt)
            # Find the JSON block in case of markdown wrapping
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "{" in response_text:
                response_text = response_text[response_text.find("{"):response_text.rfind("}")+1]
                
            data = json.loads(response_text)
            
            # Map provenance
            supporting_ids = [n["id"] for n in subgraph["nodes"]]
            
            ki_item = MemoryItem(
                tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
                memory_class="knowledge",
                memory_type=K_SUBTYPES.get(data["subtype"], "K-Item"),
                content=f"[{data['title']}] {data['content']}",
                confidence=float(data.get("confidence", 0.7)),
                extracted_by="brainclaw_distiller",
                extraction_method="leiden_synthesis_v1",
                extraction_metadata={
                    "source_community_id": community_id,
                    "supporting_memory_ids": supporting_ids,
                    "subtype": data["subtype"],
                    "last_validated": datetime.utcnow().isoformat(),
                    "contradiction_status": "stable" # Initial assumption
                }
            )
            
            # Store in Postgres
            stored_ki = await self.postgres.insert_memory_item(ki_item)
            
            # Store in Neo4j as a first-class Knowledge node linked to the Community
            cypher = """
            MATCH (e:Entity {community_id: $cid})
            WITH DISTINCT e.community_id as community_id
            CREATE (k:Knowledge {
                id: $id,
                content: $content,
                subtype: $subtype,
                confidence: $confidence,
                community_id: $cid,
                created_at: $created_at
            })
            WITH k
            MATCH (e:Entity {community_id: $cid})
            CREATE (k)-[:DISTILLED_FROM]->(e)
            """
            await self.neo4j.query(cypher, {
                "id": str(stored_ki.id),
                "content": stored_ki.content,
                "subtype": data["subtype"],
                "confidence": stored_ki.confidence,
                "cid": community_id,
                "created_at": stored_ki.created_at.isoformat()
            })
            
            return stored_ki
            
        except Exception as e:
            logger.error(f"Failed to synthesize KI for community {community_id}: {e}")
            return None

# Mapping for subtype display names
K_SUBTYPES = KNOWLEDGE_SUBTYPES
