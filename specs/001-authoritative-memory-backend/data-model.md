# Data Model: Authoritative OpenClaw Memory Backend

## Canonical Store

### PostgreSQL

PostgreSQL is the authoritative ledger for:

- raw events and messages
- promoted memory items
- decision records
- provenance and extraction metadata
- lifecycle and supersession state
- visibility, tenancy, and access metadata
- retrieval and promotion audit logs

Weaviate and Neo4j are derived from PostgreSQL-backed history and must be
rebuildable.

## Core Entities

### Raw Event

- `event_id`
- `session_id`
- `message_id`
- `agent_id`
- `tenant_id`
- `content`
- `metadata`
- `created_at`

Purpose: lossless canonical capture of conversations, tool runs, and other
session events.

### Memory Item

- `memory_id`
- `memory_class`
- `content`
- `summary`
- `confidence`
- `visibility_scope`
- `lifecycle_state`
- `user_confirmed`
- `promotion_status`
- `created_at`
- `updated_at`

Purpose: durable memory record representing promoted knowledge, with links back
to canonical raw history and retrieval/audit metadata.

### Decision Record

- `decision_id`
- `decision_summary`
- `rationale`
- `alternatives_considered`
- `current_status`
- `topic`
- `effective_at`
- `superseded_by`
- `supersession_reason`
- `evidence_refs`

Purpose: durable representation of what was decided, why, what changed, and
what is active now.

### Provenance Bundle

- `source_session_id`
- `source_message_id`
- `extraction_timestamp`
- `extractor_name`
- `extractor_version`
- `confidence`
- `memory_class`
- `visibility_scope`
- `user_confirmation_state`

Purpose: trace any durable memory or answer back to source material and trust
signals.

### Promotion Policy State

- `confidence_score`
- `contradiction_state`
- `repeat_count`
- `evidence_count`
- `explicit_remember`
- `promotion_block_reason`
- `review_required`

Purpose: determine whether raw history becomes durable memory while preserving
why a promotion was allowed or blocked.

### Supersession Link

- `from_memory_id`
- `to_memory_id`
- `reason`
- `effective_at`
- `evidence_refs`

Purpose: preserve temporal explanation of what changed and why without
overwriting prior records.

### Retrieval Log

- `retrieval_id`
- `query`
- `intent`
- `retrieval_plan`
- `result_refs`
- `agent_id`
- `tenant_id`
- `created_at`

Purpose: audit why information was returned and support continuous improvement
of routing and promotion.

## Memory Classes

BrainClaw must support at least these first-class memory classes:

- episodic
- semantic
- procedural
- relational
- decision
- identity_governance

## Derived Index Responsibilities

### Weaviate

Derived semantic/hybrid index for:

- chunks
- summaries
- concepts
- decisions
- tasks
- procedures
- preference-oriented memory

### Neo4j

Derived graph index for:

- entities
- concepts
- decisions
- tasks
- dependencies
- contradiction/support edges
- supersession chains
- temporal relations

## Lifecycle States

Memory records and decisions must support:

- `created`
- `active`
- `superseded`
- `expired`
- `archived`
