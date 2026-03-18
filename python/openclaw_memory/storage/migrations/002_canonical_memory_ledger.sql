-- Migration: 002_canonical_memory_ledger.sql
-- Description: Expands BrainClaw's canonical PostgreSQL ledger without
--              removing or rewriting existing memory_items rows.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS tenant_id UUID;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS memory_class TEXT NOT NULL DEFAULT 'semantic';

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS memory_type TEXT;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS content_embedding DOUBLE PRECISION[];

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS source_message_id UUID;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS source_session_id UUID;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS source_tool_call_id UUID;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS extracted_by TEXT;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS extraction_method TEXT;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS extraction_timestamp TIMESTAMP WITH TIME ZONE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS extractor_name TEXT NOT NULL DEFAULT 'brainclaw';

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS extractor_version TEXT NOT NULL DEFAULT '1.3.0';

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS extraction_confidence DOUBLE PRECISION;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS extraction_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS user_confirmed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS user_confirmed_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS user_confirmed_by UUID;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS valid_from TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS valid_to TIMESTAMP WITH TIME ZONE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS superseded_by UUID;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS supersession_reason TEXT;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS access_control JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'default';

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS retention_until TIMESTAMP WITH TIME ZONE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS weaviate_id TEXT;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS neo4j_id TEXT;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS weaviate_synced BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS neo4j_synced BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS weaviate_synced_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS neo4j_synced_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS sync_version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS prev_hash BYTEA;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS row_hash BYTEA;

ALTER TABLE memory_items
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE memory_items
SET extraction_metadata = COALESCE(extraction_metadata, metadata, '{}'::jsonb),
    extracted_by = COALESCE(extracted_by, extractor_name, 'brainclaw'),
    extraction_timestamp = COALESCE(extraction_timestamp, created_at),
    extractor_name = COALESCE(extractor_name, extracted_by, 'brainclaw'),
    confidence = COALESCE(confidence, 0.5),
    valid_from = COALESCE(valid_from, created_at, CURRENT_TIMESTAMP),
    status = COALESCE(status, CASE WHEN is_current THEN 'active' ELSE 'archived' END),
    retention_policy = COALESCE(retention_policy, 'default'),
    access_control = COALESCE(access_control, '{}'::jsonb)
WHERE extraction_metadata = '{}'::jsonb
   OR extracted_by IS NULL
   OR extraction_timestamp IS NULL
   OR confidence IS NULL
   OR valid_from IS NULL
   OR status IS NULL
   OR retention_policy IS NULL
   OR access_control IS NULL;

CREATE INDEX IF NOT EXISTS idx_memory_items_tenant_id ON memory_items(tenant_id);
CREATE INDEX IF NOT EXISTS idx_memory_items_memory_class ON memory_items(memory_class);
CREATE INDEX IF NOT EXISTS idx_memory_items_status ON memory_items(status);
CREATE INDEX IF NOT EXISTS idx_memory_items_is_current ON memory_items(is_current);
CREATE INDEX IF NOT EXISTS idx_memory_items_source_session_id ON memory_items(source_session_id);
CREATE INDEX IF NOT EXISTS idx_memory_items_visibility_scope ON memory_items(visibility_scope);
CREATE INDEX IF NOT EXISTS idx_memory_items_superseded_by ON memory_items(superseded_by);

CREATE TABLE IF NOT EXISTS memory_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_item_id UUID NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_agent_id UUID,
    actor_tenant_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_memory_events_memory_item_id ON memory_events(memory_item_id);
CREATE INDEX IF NOT EXISTS idx_memory_events_event_type ON memory_events(event_type);
CREATE INDEX IF NOT EXISTS idx_memory_events_event_timestamp ON memory_events(event_timestamp);

CREATE TABLE IF NOT EXISTS retrieval_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID,
    agent_id UUID,
    session_id UUID,
    intent TEXT,
    query_text TEXT NOT NULL,
    query_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_count INTEGER NOT NULL DEFAULT 0,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_retrieval_logs_tenant_id ON retrieval_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_logs_agent_id ON retrieval_logs(agent_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_logs_created_at ON retrieval_logs(created_at);
