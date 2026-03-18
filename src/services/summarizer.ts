import { getLogger } from "../logging.js";
import { callPythonBackend } from "../bridge.js";

/**
 * Background service for community summarization — wired to real Python backend.
 */
export const summarizerService = {
  id: "brainclaw-summarizer",
  description: "Periodically generates and updates LLM summaries for graph communities.",
  start(ctx: any) {
    const logger = getLogger();
    const config = ctx.config || {};
    logger.info('summarizer', 'start', 'Community summarizer service active');

    const interval = setInterval(async () => {
      try {
        logger.debug('summarizer', 'run', 'Running community summarization pass');
        await callPythonBackend("graph.summarize", "summarize_all", {
          tenant_id: config.tenantId || process.env.OPENCLAW_TENANT_ID || 'tenant-default'
        }, config, ctx);
        logger.info('summarizer', 'run', 'Community summarization pass complete');
      } catch (error: any) {
        logger.error('summarizer', 'run', error, { interval: '1h' });
      }
    }, 3600000); // Once per hour

    return {
      stop() {
        clearInterval(interval);
        logger.info('summarizer', 'stop', 'Community summarizer service stopped');
      }
    };
  }
};

export function registerSummarizerService(api: any) {
  api.registerBackgroundService?.(summarizerService);
}
