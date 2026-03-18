/**
 * Sanitization utilities for BrainClaw Plugin.
 */
/**
 * Strips sensitive Python stack traces and environment-specific
 * information from error messages before returning them to the UI.
 */
export declare function sanitizeError(error: any): string;
/**
 * Redacts sensitive fields from a configuration object for safe logging.
 */
export declare function redactConfigForLogs(config: any): any;
