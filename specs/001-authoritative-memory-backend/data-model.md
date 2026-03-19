# Data Model: BrainClaw Canonical Ledger + Lossless-Claw Integration

## Canonical Authority

PostgreSQL is canonical for all durable memory truth.

- Weaviate and Neo4j are derived and rebuildable from PostgreSQL.
- Lossless-Claw artifacts are ingested as source evidence, never canonical truth.

## Canonical Integration Tables

BrainClaw canonical records for Lossless-Claw integration must include:

- `source_artifacts`
- `memory_candidates`
- `source_sync_checkpoints`
- `integration_states`
- `promotion_overrides`
- `dead_letter_artifacts`
- `rebuild_checkpoints`
- `derived_backfill_state`

## Exact-Once and Replay Contract

Each imported source artifact must store:

- `artifact_hash` (deterministic content hash)

And must be deduplicated by a composite unique key on:

- `source_plugin`
- `source_scope_key`
- `source_artifact_type`
- `source_artifact_id`
- `source_created_at`
- `artifact_hash`

Checkpoint watermarks (`source_id`, `last_created_at`, `last_artifact_id`) are for scan efficiency only.  
Replay correctness depends on hash + unique key.

## ACL / Scope Contract

Persist these fields as first-class canonical columns on:

- `source_artifacts`
- `memory_candidates`
- `memory_items`
- `promotion_overrides`

Required fields:

- `workspace_id`
- `agent_id`
- `session_id`
- `project_id`
- `user_id`
- `visibility_scope`
- `owner_id`
- `statefulness`
- `access_control`

Default write policy is owner-only unless explicitly authorized.

## Candidate Taxonomy

Required candidate types:

- `EntityCandidate`
- `RelationshipCandidate`
- `DecisionCandidate`
- `ProcedureCandidate`
- `PreferenceCandidate`
- `IssueCandidate`
- `EventCandidate`
- `ConstraintCandidate`

## Candidate -> Memory Mapping

- `EntityCandidate` -> identity + semantic
- `RelationshipCandidate` -> relational + semantic
- `DecisionCandidate` -> decision + episodic
- `ProcedureCandidate` -> procedural + semantic
- `PreferenceCandidate` -> semantic (soft)
- `IssueCandidate` -> episodic + semantic
- `EventCandidate` -> episodic
- `ConstraintCandidate` -> semantic + policy/governance

## Promotion Threshold Contract

Use explicit PRD thresholds:

- auto-promote when `raw_extraction_confidence >= 0.85`
- interpretive promote when `interpretive_confidence >= 0.70` AND `topic_hint_match_score >= 0.60`

Otherwise block as low-confidence unless stronger corroboration or privileged override applies.

## Provenance Payload Contract

Every LCM-derived promoted memory must preserve:

- `source_artifact_ref`
- `source_summary_id`
- `source_session_id`
- `original_message_ids`
- `import_timestamp`
- `extractor_version`
- `raw_extraction_confidence`
- `interpretive_confidence`
- `topic_hint_match_score`
- `topic_hints`
- `derivation_path`
- `interpretation_flag` (`EXTRACTIVE` | `INTERPRETIVE`)
- `user_confirmation_state`
- `supersession_id`
- `verification_result`
- signer/plugin/runtime trust fields when available

## Integration State Contract

`integration_states` must persist:

- `compatibility_state`
- `reason_code`
- `last_successful_gate_evaluated_at`
- `last_degraded_reason_code`
- `last_degraded_transition_at`
- `last_successful_supported_profile`

Allowed compatibility state values:

- `not_installed`
- `installed_compatible`
- `installed_degraded`
- `installed_incompatible`
- `installed_unreachable`

## Reason Code Contract

Enumerated reason codes for degraded state, dead-letter, and blocked promotion:

- `SCHEMA_FINGERPRINT_UNKNOWN`
- `SCOPE_AMBIGUOUS`
- `STATELESS_SESSION`
- `TOOL_UNAVAILABLE`
- `ACL_DENIED`
- `LOW_CONFIDENCE`
- `CONTRADICTED`
- `SOURCE_UNREACHABLE`

## Rollback / Failure Semantics

- PostgreSQL failure aborts canonical durable writes.
- Weaviate/Neo4j failure preserves canonical write and marks derived backfill required.
- Repeated import failures are quarantined in `dead_letter_artifacts`.
- Repair/replay is deterministic and must not duplicate already-promoted memory.
