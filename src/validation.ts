/**
 * Validation utilities for BrainClaw Plugin.
 */

import { getLogger } from './logging.js';

const ALLOWED_HOSTS = process.env.ALLOWED_DB_HOSTS?.split(',') || ['localhost', '127.0.0.1'];
const ENV_BACKED_SECRET_KEYS: Record<string, string> = {
  postgresUrl: 'POSTGRES_URL',
  neo4jPassword: 'NEO4J_PASSWORD',
};

function looksLikeEnvReference(value: string): boolean {
  return value.startsWith('${') && value.endsWith('}');
}

function matchesResolvedEnvValue(key: string, value: string): boolean {
  const envVarName = ENV_BACKED_SECRET_KEYS[key];
  if (!envVarName) return false;

  const envValue = process.env[envVarName];
  return Boolean(envValue) && envValue === value;
}

/**
 * Validates a tenant URL against a host allowlist to prevent data exfiltration.
 */
export function validateTenantUrl(url: string | undefined): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname;
    
    return ALLOWED_HOSTS.some(host => 
      hostname === host || hostname.endsWith('.' + host)
    );
  } catch {
    return false;
  }
}

/**
 * Checks if a sensitive configuration field contains a plaintext secret
 * instead of a safe environment variable reference (e.g., ${VAR}).
 */
export function warnIfPlaintextSecret(key: string, value: any): void {
  if (typeof value !== 'string') return;

  if (!value || looksLikeEnvReference(value) || matchesResolvedEnvValue(key, value)) {
    return;
  }

  if (value) {
    getLogger().security('validation', 'plaintextSecret', 
      `Configuration field "${key}" appears to contain a plaintext secret`,
      { key, hint: 'Use environment variable references (e.g., ${VAR_NAME})' });
  }
}

/**
 * Validates module and function names against an allowlist to prevent code injection.
 */
const ALLOWED_ROUTING: Record<string, string[]> = {
  'retrieval': ['classify', 'retrieve_sync', 'get_retrieval_plan'],
  'pipeline': ['ingest_event', 'determine_memory_class', 'chunk_content', 'extract_entities'],
  'bridge_entrypoints': [
    'ingest_event',
    'retrieve_sync',
    'classify',
    'get_memory',
    'check_contradictions',
    'verify_audit_integrity',
    'lcm_status',
    'lcm_sync',
    'lcm_rebuild',
    'sync_operational_memory_files',
  ],
  'graph.health': ['get_health_stats'],
  'graph.communities': ['detect_communities'],
  'graph.summarize': ['summarize_all'],
  'learning.auto_summarize': ['run_summarization', 'find_summarizable_memories'],
  'learning.active_learning': ['record_retrieval', 'record_click', 'record_usage', 'apply_feedback'],
  'embeddings': ['generate_embedding', 'generate_batch'],
  'audit.audit_log': ['verify_integrity', 'log_access']
};

export function validateRouting(module: string, funct: string): boolean {
  const allowedFuncs = ALLOWED_ROUTING[module];
  return allowedFuncs?.includes(funct) ?? false;
}
