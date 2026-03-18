import { getLogger } from "../logging.js";
/**
 * Background service for community summarization.
 */
export const summarizerService = {
    id: "brainclaw-summarizer",
    description: "Periodically generates and updates LLM summaries for graph communities.",
    start(ctx) {
        const logger = getLogger();
        logger.info('summarizer', 'start', 'Community summarizer service active');
        const interval = setInterval(async () => {
            try {
                // Placeholder for real summarization
                // In a real implementation: await callPythonBackend("graph.summarize", "summarize_all", {});
                logger.debug('summarizer', 'run', 'Checking for new communities to summarize');
            }
            catch (error) {
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
export function registerSummarizerService(api) {
    api.registerBackgroundService?.(summarizerService);
}
