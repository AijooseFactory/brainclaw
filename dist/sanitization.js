/**
 * Sanitization utilities for BrainClaw Plugin.
 */
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
/**
 * Strips sensitive Python stack traces and environment-specific
 * information from error messages before returning them to the UI.
 */
export function sanitizeError(error) {
    const message = error.message || String(error);
    // Strip common Python path patterns (e.g., /Users/george/...)
    const sanitized = message.replace(/\/Users\/[^/]+\/.*?\//g, '<HIDDEN_PATH>/');
    // Generic fallback if the error looks too detailed
    if (sanitized.includes('Traceback (most recent call last)')) {
        return 'Internal Python backend error occurred. Please check system logs for details.';
    }
    return sanitized;
}
let cachedSensitiveFields = null;
function getSensitiveFields() {
    if (cachedSensitiveFields)
        return cachedSensitiveFields;
    try {
        const manifestPath = path.join(__dirname, '../openclaw.plugin.json');
        if (fs.existsSync(manifestPath)) {
            const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
            const props = manifest.configSchema?.properties || {};
            const fields = Object.keys(props).filter(k => props[k].sensitive);
            // Safety: Always include critical database URLs
            ['postgresUrl', 'weaviateUrl', 'neo4jUrl'].forEach(u => {
                if (!fields.includes(u))
                    fields.push(u);
            });
            cachedSensitiveFields = fields;
            return fields;
        }
    }
    catch (e) {
        // Fallback to defaults if manifest cannot be read
    }
    return ['postgresUrl', 'weaviateUrl', 'neo4jUrl', 'neo4jPassword'];
}
/**
 * Redacts sensitive fields from a configuration object for safe logging.
 */
export function redactConfigForLogs(config) {
    if (!config || typeof config !== 'object')
        return config;
    const redacted = { ...config };
    const sensitiveFields = getSensitiveFields();
    for (const field of sensitiveFields) {
        if (redacted[field]) {
            redacted[field] = '[REDACTED]';
        }
    }
    return redacted;
}
