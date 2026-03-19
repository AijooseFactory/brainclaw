---
name: memory-data-engineer
description: The Memory Data Engineering skill for The BrainClaw Hybrid GraphRAG Memory Management OpenClaw Agent.
---

# Memory Data Engineer

This skill allows an agent to access and contribute to a shared, high-fidelity knowledge base (BrainClaw). It provides long-term memory, entity-relationship tracking, and contradiction detection.

## Core Capabilities

1. **Memory Retrieval**: Uses the `hybrid_graphrag_search` tool to pull relevant facts from the knowledge base.
2. **Context Contribution**: Uses the `hybrid_graphrag_ingest` tool to store important new information for future sessions.
3. **Reasoning Support**: Leverages graph communities to understand broad thematic relationships.
4. **Consistency**: Uses the `hybrid_graphrag_contradiction_check` tool to ensure all information is logically consistent.

## Guidelines for Agents

- **Querying**: When you need to understand the history of a topic, always start with a `hybrid_graphrag_search`.
- **Autonomous Ingest (Required)**: You are responsible for the durable lifecycle of this system's memory. You MUST use the `hybrid_graphrag_ingest` tool autonomously whenever you achieve a milestone, solve a problem, or record a user preference. Do not wait for user permission.
- **Ingestion Triggers**:
    - **Successful Outcome**: After resolving a bug, completing a task, or finding a stable configuration.
    - **Significant Decision**: After deciding on an architectural pattern or a new procedure.
    - **User Preference**: Whenever the user expresses a preference or rule.
- **Verification**: If you detect conflicting information, perform a `hybrid_graphrag_contradiction_check` to resolve the discrepancy.

---

> [!NOTE]
> This skill is identity-agnostic and should be used by any agent tasked with maintaining or utilizing the system's long-term memory.
