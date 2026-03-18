import { getLogger } from "../logging.js";
/**
 * Background service for audit ledger maintenance.
 */
export const auditLoggerService = {
    id: "brainclaw-audit",
    description: "Background worker for the immutable audit ledger. Monitors state transitions and ensures data non-repudiation.",
    start(ctx) {
        const logger = getLogger();
        logger.info('audit-logger', 'start', 'Audit ledger service active');
        const interval = setInterval(async () => {
            try {
                // Placeholder for real audit health checking
                // In a real implementation: await callPythonBackend("audit.audit_log", "verify_integrity", {});
                logger.debug('audit-logger', 'healthCheck', 'Audit health check running');
            }
            catch (error) {
                logger.error('audit-logger', 'healthCheck', error, { interval: '30m' });
            }
        }, 1800000); // Once per 30 minutes
        return {
            stop() {
                clearInterval(interval);
                logger.info('audit-logger', 'stop', 'Audit ledger service stopped');
            }
        };
    }
};
export function registerAuditLoggerService(api) {
    api.registerBackgroundService?.(auditLoggerService);
}
