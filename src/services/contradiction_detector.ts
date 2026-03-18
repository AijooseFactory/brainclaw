import { getLogger } from "../logging.js";
import { callPythonBackend } from "../bridge.js";

/**
 * Background service for contradiction detection in the knowledge base.
 * Runs periodically to scan for contradictory claims or inconsistent entity properties.
 */
export const contradictionDetectorService = {
  id: "brainclaw-contradiction-detector",
  description: "Periodically scans the knowledge base for contradictory claims.",
  start(ctx: any) {
    const logger = getLogger();
    const config = ctx.config || {};
    logger.info('contradiction_detector', 'start', 'Contradiction detector service active');

    // Run contradiction detection every 2 hours
    const interval = setInterval(async () => {
      try {
        logger.debug('contradiction_detector', 'run', 'Running contradiction detection pass');

        const result = await callPythonBackend("bridge_entrypoints", "check_contradictions", {
          tenant_id: config.tenantId || process.env.OPENCLAW_TENANT_ID,
          limit: 50
        }, config, ctx);

        logger.info('contradiction_detector', 'run', 'Contradiction detection pass complete', {
          memories_checked: result?.checked_count || 0,
          contradiction_count: result?.contradictions?.length || 0,
          status: result?.status || 'UNKNOWN'
        });
      } catch (error: any) {
        logger.error('contradiction_detector', 'run', error, { interval: '2h' });
      }
    }, 7200000); // Every 2 hours

    return {
      stop() {
        clearInterval(interval);
        logger.info('contradiction_detector', 'stop', 'Contradiction detector service stopped');
      }
    };
  }
};

export function registerContradictionDetectorService(api: any) {
  api.registerBackgroundService?.(contradictionDetectorService);
}
