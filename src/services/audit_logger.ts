import { getLogger } from "../logging.js";
import { callPythonBackend } from "../bridge.js";

/**
 * Background service for audit ledger maintenance.
 */
export const auditLoggerService = {
  id: "brainclaw-audit",
  description: "Background worker for the immutable audit ledger. Monitors state transitions and ensures data non-repudiation.",
  start(ctx: any) {
    const logger = getLogger();
    const config = ctx.config || {};
    logger.info('audit-logger', 'start', 'Audit ledger service active');
    
    const interval = setInterval(async () => {
      try {
        const result = await callPythonBackend(
          "bridge_entrypoints",
          "verify_audit_integrity",
          {},
          config,
          ctx,
        );
        logger.info('audit-logger', 'healthCheck', 'Audit health check running', {
          status: result?.status || 'UNKNOWN',
          tables: result?.tables || {},
          provenance_gap_count: result?.provenance_gap_count ?? null,
        });
      } catch (error: any) {
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

export function registerAuditLoggerService(api: any) {
  api.registerBackgroundService?.(auditLoggerService);
}
