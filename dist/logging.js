/**
 * Structured logging and error categorization for BrainClaw Plugin.
 * Enables OpenClaw self-improvement through observable, categorized events.
 */
/**
 * Error classification rules for self-improvement.
 */
const ERROR_CLASSIFICATION_RULES = [
    // TRANSIENT errors (retry-able)
    { pattern: /timeout|timed out|ETIMEDOUT/i, category: 'TRANSIENT', code: 'TIMEOUT', retry: true, retryDelayMs: 1000 },
    { pattern: /ECONNRESET|ECONNREFUSED|ENOTFOUND/i, category: 'TRANSIENT', code: 'NETWORK', retry: true, retryDelayMs: 2000 },
    { pattern: /rate limit|429|too many requests/i, category: 'TRANSIENT', code: 'RATE_LIMIT', retry: true, retryDelayMs: 5000 },
    // INFRASTRUCTURE errors (backend down)
    { pattern: /postgresql|postgres|database|connection refused/i, category: 'INFRASTRUCTURE', code: 'POSTGRES_DOWN', retry: false, userAction: 'Check PostgreSQL connection and ensure database is running' },
    { pattern: /weaviate|vector store|embedding/i, category: 'INFRASTRUCTURE', code: 'WEAVIATE_DOWN', retry: false, userAction: 'Check Weaviate connection and ensure service is running' },
    { pattern: /neo4j|graph database|bolt:/i, category: 'INFRASTRUCTURE', code: 'NEO4J_DOWN', retry: false, userAction: 'Check Neo4j connection and ensure database is running' },
    // SECURITY errors
    { pattern: /Security Block|Unauthorized|blocked|invalid (url|host)/i, category: 'SECURITY', code: 'UNAUTHORIZED', retry: false, userAction: 'Check ALLOWED_HOSTS configuration' },
    { pattern: /plaintext secret|secret exposed|credential leak/i, category: 'SECURITY', code: 'CREDENTIAL_EXPOSURE', retry: false, userAction: 'Use environment variable references (${VAR}) instead of plaintext' },
    // CONFIGURATION errors
    { pattern: /missing|required|not (configured|set)|invalid config/i, category: 'CONFIGURATION', code: 'MISSING_CONFIG', retry: false, userAction: 'Check openclaw.json plugin configuration' },
    { pattern: /python (process|backend) (not found|exited)/i, category: 'CONFIGURATION', code: 'PYTHON_BACKEND', retry: false, userAction: 'Ensure Python virtual environment is set up correctly' },
    // VALIDATION errors
    { pattern: /invalid (parameters|input|query)|missing (field|param)/i, category: 'VALIDATION', code: 'INVALID_INPUT', retry: false, userAction: 'Check tool parameters' },
];
/**
 * Classify an error for self-improvement handling.
 */
export function classifyError(error) {
    const message = typeof error === 'string' ? error : error.message;
    const stack = typeof error === 'object' ? error.stack : undefined;
    for (const rule of ERROR_CLASSIFICATION_RULES) {
        if (rule.pattern.test(message)) {
            return {
                category: rule.category,
                code: rule.code,
                message,
                retry: rule.retry,
                retryDelayMs: rule.retryDelayMs,
                userAction: rule.userAction,
            };
        }
    }
    // Default classification
    return {
        category: 'TRANSIENT',
        code: 'UNKNOWN',
        message,
        retry: false,
    };
}
/**
 * Structured logger that outputs machine-readable logs for OpenClaw.
 */
export class PluginStructuredLogger {
    logger;
    pluginId = 'brainclaw';
    constructor(logger) {
        this.logger = logger;
    }
    /**
     * Format a structured log entry as JSON for machine parsing.
     */
    formatEntry(level, module, operation, message, options) {
        const entry = {
            timestamp: new Date().toISOString(),
            level,
            plugin: this.pluginId,
            module,
            operation,
            message,
            ...options,
        };
        return JSON.stringify(entry);
    }
    /**
     * Log debug message (only shown in debug mode).
     */
    debug(module, operation, message, metadata) {
        const formatted = this.formatEntry('debug', module, operation, message, { metadata });
        this.logger.debug?.(formatted);
    }
    /**
     * Log info message.
     */
    info(module, operation, message, metadata) {
        const formatted = this.formatEntry('info', module, operation, message, { metadata });
        this.logger.info(formatted);
    }
    /**
     * Log warning message.
     */
    warn(module, operation, message, metadata) {
        const formatted = this.formatEntry('warn', module, operation, message, { metadata });
        this.logger.warn(formatted);
    }
    /**
     * Log error with classification for self-improvement.
     */
    error(module, operation, error, metadata) {
        const classified = classifyError(error);
        const formatted = this.formatEntry('error', module, operation, classified.message, {
            category: classified.category,
            error: classified,
            metadata,
        });
        this.logger.error(formatted);
        return classified;
    }
    /**
     * Log operation timing for performance observability.
     */
    timing(module, operation, durationMs, metadata) {
        const formatted = this.formatEntry('info', module, operation, `Operation completed in ${durationMs}ms`, {
            durationMs,
            metadata,
        });
        this.logger.info(formatted);
    }
    /**
     * Log security event for audit and monitoring.
     */
    security(module, operation, message, metadata) {
        const formatted = this.formatEntry('warn', module, operation, message, {
            category: 'SECURITY',
            metadata,
        });
        this.logger.warn(formatted);
    }
    /**
     * Log infrastructure event for health monitoring.
     */
    infrastructure(module, operation, message, metadata) {
        const formatted = this.formatEntry('error', module, operation, message, {
            category: 'INFRASTRUCTURE',
            metadata,
        });
        this.logger.error(formatted);
    }
    /**
     * Create a correlation context for tracing operations.
     */
    correlate(correlationId) {
        return {
            debug: (m, o, msg, meta) => this.debug(m, o, msg, { ...meta, correlationId }),
            info: (m, o, msg, meta) => this.info(m, o, msg, { ...meta, correlationId }),
            warn: (m, o, msg, meta) => this.warn(m, o, msg, { ...meta, correlationId }),
            error: (m, o, err, meta) => this.error(m, o, err, { ...meta, correlationId }),
        };
    }
}
/**
 * Global logger instance (set during plugin initialization).
 */
let globalLogger = null;
/**
 * Initialize the global structured logger.
 */
export function initLogger(logger) {
    globalLogger = new PluginStructuredLogger(logger);
    return globalLogger;
}
/**
 * Get the global logger. Throws if not initialized.
 */
export function getLogger() {
    if (!globalLogger) {
        // Fallback to console if not initialized
        console.warn('[brainclaw] Logger not initialized, using console fallback');
        globalLogger = new PluginStructuredLogger({
            debug: (msg) => console.debug(msg),
            info: (msg) => console.log(msg),
            warn: (msg) => console.warn(msg),
            error: (msg) => console.error(msg),
        });
    }
    return globalLogger;
}
