import { getLogger } from "../logging.js";
import { callPythonBackend } from "../bridge.js";

/**
 * Background service for entity extraction from ingested memories.
 * Runs periodically to extract entities and relationships for the knowledge graph.
 */
export const entityExtractorService = {
  id: "brainclaw-entity-extractor",
  description: "Periodically extracts entities and relationships from memories for the knowledge graph.",
  start(ctx: any) {
    const logger = getLogger();
    const config = ctx.config || {};
    logger.info('entity_extractor', 'start', 'Entity extractor service active');

    // Run entity extraction every 30 minutes
    const interval = setInterval(async () => {
      try {
        logger.debug('entity_extractor', 'run', 'Running entity extraction pass');
        
        // Extract entities from memories that haven't been processed
        const result = await callPythonBackend("pipeline", "extract_entities", {
          tenant_id: config.tenantId || process.env.OPENCLAW_TENANT_ID,
          batch_size: 100,
          model: config.extractionModel || process.env.EXTRACTION_MODEL || 'llama3.2'
        }, config, ctx);
        
        logger.info('entity_extractor', 'run', 'Entity extraction pass complete', {
          entities_extracted: result?.entities || 0,
          relationships_created: result?.relationships || 0
        });
      } catch (error: any) {
        logger.error('entity_extractor', 'run', error, { interval: '30m' });
      }
    }, 1800000); // Every 30 minutes

    return {
      stop() {
        clearInterval(interval);
        logger.info('entity_extractor', 'stop', 'Entity extractor service stopped');
      }
    };
  }
};

/**
 * Trigger entity extraction for a specific memory (called by Lore agent).
 */
export async function extractEntitiesForMemory(
  memoryId: string,
  content: string,
  config: Record<string, any> = {},
  ctx: any = {}
): Promise<{ entities: string[]; relationships: Array<{ from: string; to: string; type: string }> }> {
  const logger = getLogger();
  
  logger.info('entity_extractor', 'extract', 'Extracting entities for memory', { memoryId });
  
  const result = await callPythonBackend("pipeline", "extract_entities", {
    memory_id: memoryId,
    content: content,
    tenant_id: config.tenantId || process.env.OPENCLAW_TENANT_ID,
    model: config.extractionModel || process.env.EXTRACTION_MODEL || 'llama3.2'
  }, config, ctx);
  
  return result;
}

export function registerEntityExtractorService(api: any) {
  api.registerBackgroundService?.(entityExtractorService);
}
