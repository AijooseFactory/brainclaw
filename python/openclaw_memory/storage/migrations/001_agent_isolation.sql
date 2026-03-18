-- Migration: 001_agent_isolation.sql
-- Description: Adds agent_id to memory_items and enables Row-Level Security (RLS)

-- 1. Add agent_id column
ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS agent_id UUID;

-- 2. Create index for performance
CREATE INDEX IF NOT EXISTS idx_memory_items_agent_id ON memory_items(agent_id);

-- 3. Enable Row-Level Security
ALTER TABLE memory_items ENABLE ROW LEVEL SECURITY;

-- 4. Create Policy: Agent Isolation
-- Managers (coordinator) can see everything, other agents see their own or team-shared
CREATE POLICY agent_isolation_policy ON memory_items
    FOR ALL
    TO openclaw
    USING (
        -- 1. Owner can see their own
        agent_id = current_setting('app.current_agent_id')::UUID
        OR 
        -- 2. Backward Compatibility: Allow access to legacy data (NULL agent_id)
        -- We assume legacy data is 'public' within the tenant if no agent is assigned
        (agent_id IS NULL AND visibility_scope IN ('tenant', 'public'))
        OR
        -- 3. Team shared (if agent is in the team)
        (visibility_scope = 'team' AND EXISTS (
            SELECT 1 FROM team_members 
            WHERE team_id = current_setting('app.current_team_id') 
            AND agent_id = current_setting('app.current_agent_id')::UUID
        ))
        OR
        -- 4. Tenant/Public (explicitly marked)
        visibility_scope IN ('tenant', 'public')
    );

-- 5. Add team_members table for verification
CREATE TABLE IF NOT EXISTS team_members (
    agent_id UUID NOT NULL,
    team_id TEXT NOT NULL,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_id, team_id)
);
