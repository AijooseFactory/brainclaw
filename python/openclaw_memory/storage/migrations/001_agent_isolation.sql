-- Migration: 001_agent_isolation.sql
-- Description: Ensures memory_items table exists and adds agent_id + RLS for multi-agent isolation

-- 0. Create memory_items table if it does not already exist (safe for fresh and existing DBs)
CREATE TABLE IF NOT EXISTS memory_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id         UUID,
    visibility_scope TEXT NOT NULL DEFAULT 'agent',
    content          TEXT NOT NULL,
    metadata         JSONB,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 1. Add agent_id column (idempotent — safe if already exists)
ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS agent_id UUID;

-- 2. Create index for performance
CREATE INDEX IF NOT EXISTS idx_memory_items_agent_id ON memory_items(agent_id);

-- 3. Enable Row-Level Security
ALTER TABLE memory_items ENABLE ROW LEVEL SECURITY;

-- 4. Drop policy if it already exists so we can recreate it (idempotent)
DROP POLICY IF EXISTS agent_isolation_policy ON memory_items;

-- 5. Create Policy: Agent Isolation
--    Uses current_setting(..., TRUE) so it does not fail when the setting is absent
CREATE POLICY agent_isolation_policy ON memory_items
    FOR ALL
    USING (
        agent_id::TEXT = current_setting('app.current_agent_id', TRUE)
        OR (agent_id IS NULL AND visibility_scope IN ('tenant', 'public'))
        OR visibility_scope IN ('tenant', 'public')
    );

-- 6. Team members table for future team-scoped sharing
CREATE TABLE IF NOT EXISTS team_members (
    agent_id  UUID NOT NULL,
    team_id   TEXT NOT NULL,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_id, team_id)
);
