/**
 * Structured logging and error categorization for BrainClaw Plugin.
 * Enables OpenClaw self-improvement through observable, categorized events.
 */
/**
 * Error categories for self-improvement and automated handling.
 */
export type ErrorCategory = 'TRANSIENT' | 'CONFIGURATION' | 'SECURITY' | 'INFRASTRUCTURE' | 'VALIDATION';
/**
 * PluginLogger interface from OpenClaw plugin SDK.
 */
export type PluginLogger = {
    debug?: (message: string) => void;
    info: (message: string) => void;
    warn: (message: string) => void;
    error: (message: string) => void;
};
/**
 * Structured log entry for machine-readable logging.
 */
export interface StructuredLogEntry {
    timestamp: string;
    level: 'debug' | 'info' | 'warn' | 'error';
    plugin: 'brainclaw';
    module: string;
    operation: string;
    message: string;
    category?: ErrorCategory;
    correlationId?: string;
    tenantId?: string;
    durationMs?: number;
    error?: {
        category: ErrorCategory;
        code: string;
        message: string;
        stack?: string;
    };
    metadata?: Record<string, unknown>;
}
/**
 * Error classification for automated handling.
 */
export interface ClassifiedError {
    category: ErrorCategory;
    code: string;
    message: string;
    retry: boolean;
    retryDelayMs?: number;
    userAction?: string;
}
/**
 * Classify an error for self-improvement handling.
 */
export declare function classifyError(error: Error | string): ClassifiedError;
/**
 * Structured logger that outputs machine-readable logs for OpenClaw.
 */
export declare class PluginStructuredLogger {
    private logger;
    private pluginId;
    constructor(logger: PluginLogger);
    /**
     * Format a structured log entry as JSON for machine parsing.
     */
    private formatEntry;
    /**
     * Log debug message (only shown in debug mode).
     */
    debug(module: string, operation: string, message: string, metadata?: Record<string, unknown>): void;
    /**
     * Log info message.
     */
    info(module: string, operation: string, message: string, metadata?: Record<string, unknown>): void;
    /**
     * Log warning message.
     */
    warn(module: string, operation: string, message: string, metadata?: Record<string, unknown>): void;
    /**
     * Log error with classification for self-improvement.
     */
    error(module: string, operation: string, error: Error | string, metadata?: Record<string, unknown>): ClassifiedError;
    /**
     * Log operation timing for performance observability.
     */
    timing(module: string, operation: string, durationMs: number, metadata?: Record<string, unknown>): void;
    /**
     * Log security event for audit and monitoring.
     */
    security(module: string, operation: string, message: string, metadata?: Record<string, unknown>): void;
    /**
     * Log infrastructure event for health monitoring.
     */
    infrastructure(module: string, operation: string, message: string, metadata?: Record<string, unknown>): void;
    /**
     * Create a correlation context for tracing operations.
     */
    correlate(correlationId: string): {
        debug: (module: string, operation: string, message: string, metadata?: Record<string, unknown>) => void;
        info: (module: string, operation: string, message: string, metadata?: Record<string, unknown>) => void;
        warn: (module: string, operation: string, message: string, metadata?: Record<string, unknown>) => void;
        error: (module: string, operation: string, error: Error | string, metadata?: Record<string, unknown>) => ClassifiedError;
    };
}
/**
 * Initialize the global structured logger.
 */
export declare function initLogger(logger: PluginLogger): PluginStructuredLogger;
/**
 * Get the global logger. Throws if not initialized.
 */
export declare function getLogger(): PluginStructuredLogger;
