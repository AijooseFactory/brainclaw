import { registerSearchTool } from "./tools/search.js";
import { registerMemorySearchTool } from "./tools/memory_search.js";
import { registerMemoryGetTool } from "./tools/memory_get.js";
import { registerIngestTool } from "./tools/ingest.js";
import { registerGraphHealthTool } from "./tools/graph_health.js";
import { registerContradictionTool } from "./tools/contradiction_check.js";
import { registerSummarizerService } from "./services/summarizer.js";
import { registerAuditLoggerService } from "./services/audit_logger.js";
import { registerEntityExtractorService } from "./services/entity_extractor.js";
import { registerContradictionDetectorService } from "./services/contradiction_detector.js";
import { registerLosslessClawIntegrationService } from "./services/lossless_claw_integration.js";
import { registerOperationalMemorySyncService } from "./services/operational_memory_sync.js";
import { registerMemoryFileWatcherService } from "./services/memory_file_watcher.js";
import { registerPromptRecallHook } from "./hooks/prompt_recall.js";
import { registerBootstrapFilterHook } from "./hooks/bootstrap_filter.js";
import { registerAgentEndCaptureHook } from "./hooks/agent_end_capture.js";
import { registerLcmExpandTool } from "./tools/lcm_expand.js";
import { registerLcmDescribeTool } from "./tools/lcm_describe.js";
import { registerLeidenDetectionTool } from "./tools/leiden_detection.js";
import { registerIntelDistillTool } from "./tools/intel_distill.js";
import { registerIntelligenceService } from "./services/intelligence.js";
import { initLogger } from "./logging.js";
import { BRAINCLAW_FEATURES, BRAINCLAW_VERSION } from "./plugin_metadata.js";
import { registerBrainclawCli } from "./register_cli.js";

/**
 * BrainClaw Plugin for OpenClaw
 * 
 * Provides hierarchical Leiden community detection, 
 * immutable audit ledgers, and hybrid search (Vector + BM25 + Graph).
 * 
 * Background Services (Lore Integration):
 * - Entity Extractor: Extracts entities/relationships from memories (30min)
 * - Summarizer: Generates LLM summaries for graph communities (1h)
 * - Contradiction Detector: Scans for contradictory claims (2h)
 * - Audit Logger: Logs all memory access for compliance
 */
export default function hybridGraphRagPlugin(api: any) {
  // 0. Initialize structured logging with OpenClaw's logger
  const logger = initLogger(api.logger);
  
  // 1. Register Agent Tools
  registerMemorySearchTool(api);
  registerMemoryGetTool(api);
  registerSearchTool(api);
  registerIngestTool(api);
  registerGraphHealthTool(api);
  registerContradictionTool(api);
  registerPromptRecallHook(api);
  registerAgentEndCaptureHook(api);
  registerBootstrapFilterHook(api);
  registerLcmExpandTool(api);
  registerLcmDescribeTool(api);
  registerLeidenDetectionTool(api);
  registerIntelDistillTool(api);

  // 2. Register Background Services
  registerSummarizerService(api);
  registerAuditLoggerService(api);
  registerEntityExtractorService(api);
  registerContradictionDetectorService(api);
  registerLosslessClawIntegrationService(api);
  registerOperationalMemorySyncService(api);
  registerMemoryFileWatcherService(api);
  registerIntelligenceService(api);
  registerBrainclawCli(api);

  logger.info('plugin', 'init', 'BrainClaw plugin initialized successfully', {
    version: BRAINCLAW_VERSION,
    features: BRAINCLAW_FEATURES,
    lore_integration: 'Entity extraction + Auto-summarization + Contradiction detection'
  });
}
