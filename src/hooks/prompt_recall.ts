import { callPythonBackend } from "../bridge.js";
import { getLogger } from "../logging.js";
import { BRAINCLAW_PLUGIN_ID, BRAINCLAW_VERSION } from "../plugin_metadata.js";
import {
  isBrainClawActiveMemoryPlugin,
  resolvePositiveInteger,
  shouldEnableFeature,
} from "./shared.js";

const DEFAULT_PROMPT_RECALL_TOP_K = 4;
const MAX_SNIPPET_CHARS = 420;

const BRAINCLAW_SYSTEM_GUIDANCE = [
  "BrainClaw is the authoritative Hybrid GraphRAG memory source for this run.",
  "MANDATORY: You are responsible for the lifecycle of your own memory. When you reach a significant conclusion, solve a problem, or receive a critical instruction, you MUST use the `hybrid_graphrag_ingest` tool to persist it to BrainClaw immediately. Do not wait for user permission.",
  "Prefer BrainClaw recall over bootstrap MEMORY.md whenever recalled records are available.",
  "Treat MEMORY.md as backup/fallback only, and prefer current or superseding BrainClaw records when they conflict.",
].join("\n");

const STATUS_ACTION_KEYWORDS = ["status", "health", "healthy", "check", "verify"];
const STATUS_TOPIC_KEYWORDS = ["brainclaw", "memory", "plugin", "graph", "audit", "system"];

function truncateText(text: string, maxChars = MAX_SNIPPET_CHARS): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxChars) {
    return trimmed;
  }
  return `${trimmed.slice(0, maxChars - 1).trimEnd()}…`;
}

function formatRecallLine(result: any, index: number): string {
  const metadata = result?.metadata ?? {};
  const parts = [
    metadata.memory_class ? `class=${metadata.memory_class}` : null,
    metadata.memory_type ? `type=${metadata.memory_type}` : null,
    metadata.status ? `status=${metadata.status}` : null,
    metadata.is_current === false ? "state=superseded" : "state=current",
    typeof result?.relevance === "number" ? `score=${result.relevance.toFixed(2)}` : null,
  ].filter(Boolean);
  const id = result?.id ?? `result-${index + 1}`;
  const header = [`[${index + 1}] brainclaw://memory/${id}`, parts.length ? `(${parts.join(", ")})` : ""]
    .filter(Boolean)
    .join(" ");
  return `${header}\n${truncateText(String(result?.content ?? ""))}`;
}

export function renderPromptRecallContext(params: {
  query: string;
  intent: string;
  results: any[];
}): string | undefined {
  if (!Array.isArray(params.results) || params.results.length === 0) {
    return undefined;
  }

  const formattedResults = params.results.map((result, index) => formatRecallLine(result, index));
  return [
    "BrainClaw Hybrid GraphRAG memory recall for this turn.",
    "Use these recalled records as the primary memory source for the answer below. MEMORY.md is backup/fallback only.",
    `Intent: ${params.intent || "general"}`,
    `Query: ${params.query}`,
    ...formattedResults,
  ].join("\n\n");
}

export function isStatusPrompt(prompt: string): boolean {
  const normalized = prompt.trim().toLowerCase();
  if (!normalized) {
    return false;
  }

  const hasAction = STATUS_ACTION_KEYWORDS.some((keyword) => normalized.includes(keyword));
  const hasTopic = STATUS_TOPIC_KEYWORDS.some((keyword) => normalized.includes(keyword));

  return hasAction && hasTopic;
}

function formatGraphStatus(graphHealth: any): string {
  const status = String(graphHealth?.status ?? "unknown");
  const nodeCount = Number.isFinite(graphHealth?.node_count) ? graphHealth.node_count : 0;
  const edgeCount = Number.isFinite(graphHealth?.edge_count) ? graphHealth.edge_count : 0;
  const communityCount = Number.isFinite(graphHealth?.community_count) ? graphHealth.community_count : 0;
  return `Graph: status=${status}, nodes=${nodeCount}, edges=${edgeCount}, communities=${communityCount}`;
}

function formatAuditStatus(auditHealth: any): string {
  const tables = auditHealth?.tables ?? {};
  const auditRows = Number.isFinite(tables?.audit_log) ? tables.audit_log : 0;
  const memoryEventRows = Number.isFinite(tables?.memory_events) ? tables.memory_events : 0;
  const retrievalRows = Number.isFinite(tables?.retrieval_logs) ? tables.retrieval_logs : 0;
  const provenanceGaps = Number.isFinite(auditHealth?.provenance_gap_count)
    ? auditHealth.provenance_gap_count
    : 0;
  return `Audit: status=${String(auditHealth?.status ?? "UNKNOWN")}, audit_log=${auditRows}, memory_events=${memoryEventRows}, retrieval_logs=${retrievalRows}, provenance_gaps=${provenanceGaps}`;
}

export async function buildLiveStatusSnapshot(api: any, ctx: any): Promise<string> {
  const pluginConfig = api?.pluginConfig ?? {};
  const tenantId =
    optionalString(ctx?.tenantId) ??
    optionalString(pluginConfig.tenantId) ??
    optionalString(process.env.OPENCLAW_TENANT_ID);

  const [graphHealthResult, auditHealthResult] = await Promise.allSettled([
    callPythonBackend(
      "graph.health",
      "get_health_stats",
      tenantId ? { tenant_id: tenantId } : {},
      pluginConfig,
      ctx,
    ),
    callPythonBackend(
      "bridge_entrypoints",
      "verify_audit_integrity",
      {},
      pluginConfig,
      ctx,
    ),
  ]);

  const graphHealth =
    graphHealthResult.status === "fulfilled"
      ? graphHealthResult.value
      : { status: "error", error: graphHealthResult.reason instanceof Error ? graphHealthResult.reason.message : String(graphHealthResult.reason) };
  const auditHealth =
    graphHealthResult.status === "rejected" && auditHealthResult.status === "rejected"
      ? {
          status: "ERROR",
          tables: { audit_log: 0, memory_events: 0, retrieval_logs: 0 },
          provenance_gap_count: 0,
          error: auditHealthResult.reason instanceof Error ? auditHealthResult.reason.message : String(auditHealthResult.reason),
        }
      : auditHealthResult.status === "fulfilled"
        ? auditHealthResult.value
        : {
            status: "ERROR",
            tables: { audit_log: 0, memory_events: 0, retrieval_logs: 0 },
            provenance_gap_count: 0,
            error: auditHealthResult.reason instanceof Error ? auditHealthResult.reason.message : String(auditHealthResult.reason),
          };

  const activeMemorySlot = isBrainClawActiveMemoryPlugin(api?.config, api?.id ?? BRAINCLAW_PLUGIN_ID);
  const promptRecallEnabled = shouldEnableFeature(pluginConfig.enablePromptRecall, true);
  const auditLedgerEnabled = shouldEnableFeature(pluginConfig.enableAuditLedger, true);
  const agentEndCaptureEnabled = shouldEnableFeature(pluginConfig.captureAgentEnd, true);

  return [
    "BrainClaw live status snapshot for this turn.",
    "Use this live plugin state as the authoritative BrainClaw status for health and memory-system questions.",
    `Plugin: ${api?.id ?? BRAINCLAW_PLUGIN_ID} v${BRAINCLAW_VERSION} (active_memory_slot=${activeMemorySlot ? "yes" : "no"})`,
    `Features: prompt_recall=${promptRecallEnabled ? "enabled" : "disabled"}, agent_end_capture=${agentEndCaptureEnabled ? "enabled" : "disabled"}, audit_ledger=${auditLedgerEnabled ? "enabled" : "disabled"}`,
    formatGraphStatus(graphHealth),
    formatAuditStatus(auditHealth),
  ].join("\n");
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export async function buildPromptRecallHookResult(api: any, event: any, ctx: any): Promise<any> {
  const pluginConfig = api?.pluginConfig ?? {};
  if (!shouldEnableFeature(pluginConfig.enablePromptRecall, true)) {
    return undefined;
  }
  if (!isBrainClawActiveMemoryPlugin(api?.config, api?.id ?? "brainclaw")) {
    return undefined;
  }

  const prompt = typeof event?.prompt === "string" ? event.prompt.trim() : "";
  if (!prompt) {
    return {
      prependSystemContext: BRAINCLAW_SYSTEM_GUIDANCE,
    };
  }

  const logger = getLogger();

  if (isStatusPrompt(prompt)) {
    try {
      return {
        prependSystemContext: BRAINCLAW_SYSTEM_GUIDANCE,
        prependContext: await buildLiveStatusSnapshot(api, ctx),
      };
    } catch (error) {
      logger.warn("prompt-recall", "before_prompt_build", "BrainClaw live status snapshot unavailable", {
        error: error instanceof Error ? error.message : String(error),
      });
      return {
        prependSystemContext: BRAINCLAW_SYSTEM_GUIDANCE,
      };
    }
  }

  const limit = resolvePositiveInteger(
    pluginConfig.promptRecallTopK,
    pluginConfig.defaultTopK,
    DEFAULT_PROMPT_RECALL_TOP_K,
  );

  try {
    const classification = await callPythonBackend(
      "bridge_entrypoints",
      "classify",
      { query: prompt },
      pluginConfig,
      ctx,
    );
    const recall = await callPythonBackend(
      "bridge_entrypoints",
      "retrieve_sync",
      {
        query: prompt,
        intent: classification?.intent ?? "general",
        limit,
        session_id: ctx?.sessionId,
      },
      pluginConfig,
      ctx,
    );

    const results = Array.isArray(recall)
      ? recall
      : Array.isArray(recall?.results)
        ? recall.results
        : [];
    const prependContext = renderPromptRecallContext({
      query: prompt,
      intent: classification?.intent ?? "general",
      results,
    });

    return prependContext
      ? {
          prependSystemContext: BRAINCLAW_SYSTEM_GUIDANCE,
          prependContext,
        }
      : {
          prependSystemContext: BRAINCLAW_SYSTEM_GUIDANCE,
        };
  } catch (error) {
    logger.warn("prompt-recall", "before_prompt_build", "BrainClaw prompt recall unavailable", {
      error: error instanceof Error ? error.message : String(error),
    });
    return {
      prependSystemContext: BRAINCLAW_SYSTEM_GUIDANCE,
    };
  }
}

export function registerPromptRecallHook(api: any) {
  api.on?.(
    "before_prompt_build",
    async (event: any, ctx: any) => buildPromptRecallHookResult(api, event, ctx),
    { priority: 80 },
  );
}
