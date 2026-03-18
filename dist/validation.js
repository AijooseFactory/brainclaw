/**
 * Validation utilities for BrainClaw Plugin.
 */
import { getLogger } from './logging.js';
const ALLOWED_HOSTS = process.env.ALLOWED_DB_HOSTS?.split(',') || ['localhost', '127.0.0.1'];
/**
 * Validates a tenant URL against a host allowlist to prevent data exfiltration.
 */
export function validateTenantUrl(url) {
    if (!url)
        return false;
    try {
        const parsed = new URL(url);
        const hostname = parsed.hostname;
        return ALLOWED_HOSTS.some(host => hostname === host || hostname.endsWith('.' + host));
    }
    catch {
        return false;
    }
}
/**
 * Checks if a sensitive configuration field contains a plaintext secret
 * instead of a safe environment variable reference (e.g., ${VAR}).
 */
export function warnIfPlaintextSecret(key, value) {
    if (typeof value !== 'string')
        return;
    // If the value doesn't look like an env var reference and is not empty
    if (value && !value.startsWith('${') && !value.endsWith('}')) {
        getLogger().security('validation', 'plaintextSecret', `Configuration field "${key}" appears to contain a plaintext secret`, { key, hint: 'Use environment variable references (e.g., ${VAR_NAME})' });
    }
}
/**
 * Validates module and function names against an allowlist to prevent code injection.
 */
const ALLOWED_ROUTING = {
    'retrieval': ['classify', 'retrieve_sync', 'get_retrieval_plan'],
    'pipeline': ['ingest_event', 'determine_memory_class', 'chunk_content'],
    'graph.communities': ['detect_communities'],
    'graph.summarize': ['summarize_all'],
    'audit.audit_log': ['verify_integrity']
};
export function validateRouting(module, funct) {
    const allowedFuncs = ALLOWED_ROUTING[module];
    return allowedFuncs?.includes(funct) ?? false;
}
