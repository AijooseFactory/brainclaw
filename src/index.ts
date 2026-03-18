import { registerSearchTool } from "./tools/search.js";
import { registerIngestTool } from "./tools/ingest.js";
import { registerGraphHealthTool } from "./tools/graph_health.js";
import { registerContradictionTool } from "./tools/contradiction_check.js";
import { registerSummarizerService } from "./services/summarizer.js";
import { registerAuditLoggerService } from "./services/audit_logger.js";
import { initLogger } from "./logging.js";

/**
 * BrainClaw Plugin for OpenClaw
 * 
 * Provides hierarchical Leiden community detection, 
 * immutable audit ledgers, and hybrid search (Vector + BM25 + Graph).
 */
export default function hybridGraphRagPlugin(api: any) {
  // 0. Initialize structured logging with OpenClaw's logger
  const logger = initLogger(api.logger);
  
  // 1. Register Agent Tools
  registerSearchTool(api);
  registerIngestTool(api);
  registerGraphHealthTool(api);
  registerContradictionTool(api);

  // 2. Register Background Services
  registerSummarizerService(api);
  registerAuditLoggerService(api);

  logger.info('plugin', 'init', 'BrainClaw plugin initialized successfully', {
    version: '1.2.0',
    features: ['search', 'ingest', 'graph-health', 'contradiction', 'summarizer', 'audit-logger']
  });
}
