-- Migration: 004_lossless_claw_integration.sql
-- Description: Canonical BrainClaw tables for Lossless-Claw detection,
--              source artifact ingestion, candidate promotion, checkpoints,
--              dead-letter handling, and derived-store rebuild tracking.

CREATE TABLE IF NOT EXISTS source_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_plugin TEXT NOT NULL,
    source_artifact_type TEXT NOT NULL,
    source_artifact_id TEXT NOT NULL,
    source_scope_key TEXT NOT NULL,
    source_created_at TIMESTAMP WITH TIME ZONE,
    source_session_id TEXT,
    source_summary_id TEXT,
    source_conversation_id TEXT,
    source_parent_summary_id TEXT,
    summary_depth INTEGER,
    artifact_hash TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    topic_hints JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_anchor_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    signer_identity TEXT,
    plugin_hash TEXT,
    runtime_hash TEXT,
    verification_result TEXT,
    compatibility_state TEXT NOT NULL,
    reason_code TEXT,
    workspace_id UUID,
    agent_id UUID,
    session_id UUID,
    project_id UUID,
    user_id UUID,
    visibility_scope TEXT NOT NULL DEFAULT 'owner',
    owner_id UUID,
    statefulness TEXT NOT NULL DEFAULT 'stateful',
    access_control JSONB NOT NULL DEFAULT '{}'::jsonb,
    import_status TEXT NOT NULL DEFAULT 'pending',
    import_error TEXT,
    imported_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (
        source_plugin,
        source_scope_key,
        source_artifact_type,
        source_artifact_id,
        source_created_at,
        artifact_hash
    )
);

CREATE INDEX IF NOT EXISTS idx_source_artifacts_plugin ON source_artifacts(source_plugin);
CREATE INDEX IF NOT EXISTS idx_source_artifacts_session ON source_artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_source_artifacts_import_status ON source_artifacts(import_status);

CREATE TABLE IF NOT EXISTS memory_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_artifact_id UUID NOT NULL REFERENCES source_artifacts(id) ON DELETE CASCADE,
    candidate_type TEXT NOT NULL,
    memory_class_target TEXT NOT NULL,
    memory_type_target TEXT,
    content TEXT NOT NULL,
    structured_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_extraction_confidence DOUBLE PRECISION,
    interpretive_confidence DOUBLE PRECISION,
    topic_hint_match_score DOUBLE PRECISION,
    interpretation_flag TEXT,
    contradiction_detected BOOLEAN NOT NULL DEFAULT FALSE,
    blocked_reason_code TEXT,
    promotion_status TEXT NOT NULL DEFAULT 'pending',
    promoted_memory_item_id UUID REFERENCES memory_items(id) ON DELETE SET NULL,
    extractor_version TEXT,
    derivation_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    topic_hints JSONB NOT NULL DEFAULT '[]'::jsonb,
    original_message_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    supersession_id UUID,
    workspace_id UUID,
    agent_id UUID,
    session_id UUID,
    project_id UUID,
    user_id UUID,
    visibility_scope TEXT NOT NULL DEFAULT 'owner',
    owner_id UUID,
    statefulness TEXT NOT NULL DEFAULT 'stateful',
    access_control JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_candidates_type ON memory_candidates(candidate_type);
CREATE INDEX IF NOT EXISTS idx_memory_candidates_status ON memory_candidates(promotion_status);
CREATE INDEX IF NOT EXISTS idx_memory_candidates_blocked_reason ON memory_candidates(blocked_reason_code);

CREATE TABLE IF NOT EXISTS source_sync_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    checkpoint_position TEXT,
    last_created_at TIMESTAMP WITH TIME ZONE,
    last_artifact_id TEXT,
    last_successful_import_ref UUID REFERENCES source_artifacts(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    replay_marker TEXT,
    failed_range JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_id, source_type)
);

CREATE TABLE IF NOT EXISTS integration_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    compatibility_state TEXT NOT NULL,
    reason_code TEXT,
    last_successful_gate_evaluated_at TIMESTAMP WITH TIME ZONE,
    last_degraded_reason_code TEXT,
    last_degraded_transition_at TIMESTAMP WITH TIME ZONE,
    last_successful_supported_profile TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_id, source_type)
);

CREATE TABLE IF NOT EXISTS promotion_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES memory_candidates(id) ON DELETE CASCADE,
    actor_id UUID,
    justification TEXT NOT NULL,
    approval_state TEXT NOT NULL DEFAULT 'pending',
    approval_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dead_letter_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_plugin TEXT NOT NULL,
    source_artifact_type TEXT NOT NULL,
    source_artifact_id TEXT,
    artifact_hash TEXT,
    reason_code TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    replay_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rebuild_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target TEXT NOT NULL,
    checkpoint_ref TEXT,
    last_validated_at TIMESTAMP WITH TIME ZONE,
    last_validated_target_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (target)
);

CREATE TABLE IF NOT EXISTS derived_backfill_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_item_id UUID REFERENCES memory_items(id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    last_error TEXT,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (memory_item_id, target)
);
