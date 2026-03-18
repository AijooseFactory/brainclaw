import { callPythonBackend } from "../bridge.js";
import { getLogger } from "../logging.js";
import {
  findLatestMessageText,
  isBrainClawActiveMemoryPlugin,
  shouldEnableFeature,
} from "./shared.js";

const DURABLE_MEMORY_PATTERNS = [
  /\bwe decided\b/i,
  /\bdecided to\b/i,
  /\bagreed to\b/i,
  /\bprocedure:\b/i,
  /\brunbook:\b/i,
  /\bplaybook:\b/i,
  /\bworkflow:\b/i,
  /\bsteps:\b/i,
  /\bworked successfully\b/i,
  /\bresolved\b/i,
  /\bfixed\b/i,
];

export function shouldCaptureAgentEndMemory(text: string): boolean {
  const normalized = text.trim();
  if (!normalized || normalized.length < 40) {
    return false;
  }

  return DURABLE_MEMORY_PATTERNS.some((pattern) => pattern.test(normalized));
}

export async function captureAgentEndMemory(api: any, event: any, ctx: any): Promise<void> {
  const pluginConfig = api?.pluginConfig ?? {};
  if (!shouldEnableFeature(pluginConfig.captureAgentEnd, true)) {
    return;
  }
  if (!event?.success) {
    return;
  }
  if (!isBrainClawActiveMemoryPlugin(api?.config, api?.id ?? "brainclaw")) {
    return;
  }

  const assistantText = findLatestMessageText(event?.messages ?? [], "assistant");
  if (!shouldCaptureAgentEndMemory(assistantText)) {
    return;
  }

  const userText = findLatestMessageText(event?.messages ?? [], "user");
  const metadata = {
    event_type: "agent_end",
    role: "assistant",
    session_id: ctx?.sessionId,
    session_key: ctx?.sessionKey,
    source: "brainclaw_agent_end",
    duration_ms: event?.durationMs,
    source_prompt: userText || undefined,
  };

  try {
    await callPythonBackend(
      "bridge_entrypoints",
      "ingest_event",
      {
        event: {
          content: assistantText,
          metadata,
        },
      },
      pluginConfig,
      ctx,
    );
  } catch (error) {
    getLogger().warn("agent-end-capture", "agent_end", "Failed to capture durable agent-end memory", {
      error: error instanceof Error ? error.message : String(error),
      agentId: ctx?.agentId,
      sessionId: ctx?.sessionId,
    });
  }
}

export function registerAgentEndCaptureHook(api: any) {
  api.on?.("agent_end", async (event: any, ctx: any) => captureAgentEndMemory(api, event, ctx));
}
