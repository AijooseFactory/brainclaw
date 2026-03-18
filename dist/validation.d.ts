/**
 * Validation utilities for BrainClaw Plugin.
 */
/**
 * Validates a tenant URL against a host allowlist to prevent data exfiltration.
 */
export declare function validateTenantUrl(url: string | undefined): boolean;
/**
 * Checks if a sensitive configuration field contains a plaintext secret
 * instead of a safe environment variable reference (e.g., ${VAR}).
 */
export declare function warnIfPlaintextSecret(key: string, value: any): void;
export declare function validateRouting(module: string, funct: string): boolean;
