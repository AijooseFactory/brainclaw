import path from "node:path";
import { pathToFileURL } from "node:url";
import { loadConfig } from "../config/config.js";
import { resolveUserPath } from "../utils.js";
import type {
  AgentsBrainClawMemoryListParams,
  AgentsBrainClawMemoryListResult,
  AgentsBrainClawMemoryUpdateParams,
  AgentsBrainClawMemoryUpdateResult,
} from "./protocol/index.js";

type BrainClawBridgeModule = {
  callPythonBackend: (
    module: string,
    funct: string,
    params: Record<string, unknown>,
    config?: Record<string, unknown>,
    ctx?: Record<string, unknown>,
  ) => Promise<unknown>;
};

const ENV_REF_RE = /^\$\{([A-Z0-9_]+)\}$/;

function resolveEnvTemplate(value: string): string | undefined {
  const match = value.trim().match(ENV_REF_RE);
  if (!match) {
    return value;
  }
  return process.env[match[1]];
}

function resolveConfigTemplates(value: unknown): unknown {
  if (typeof value === "string") {
    return resolveEnvTemplate(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => resolveConfigTemplates(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, resolveConfigTemplates(item)]),
    );
  }
  return value;
}

function resolveBrainClawInstallPath(cfg: Record<string, unknown>): string {
  const installs = (cfg.plugins as { installs?: Record<string, Record<string, unknown>> } | undefined)
    ?.installs;
  const record = installs?.brainclaw;
  const rawInstallPath =
    (typeof record?.installPath === "string" && record.installPath.trim()) ||
    (typeof record?.sourcePath === "string" && record.sourcePath.trim());
  if (!rawInstallPath) {
    throw new Error("BrainClaw is not installed in the active OpenClaw runtime.");
  }
  return resolveUserPath(rawInstallPath);
}

function resolveBrainClawPluginConfig(cfg: Record<string, unknown>): Record<string, unknown> {
  const entries = (cfg.plugins as { entries?: Record<string, Record<string, unknown>> } | undefined)
    ?.entries;
  const entry = entries?.brainclaw;
  if (entry?.enabled === false) {
    throw new Error("BrainClaw is installed but disabled in the active OpenClaw runtime.");
  }
  const rawConfig = (entry?.config as Record<string, unknown> | undefined) ?? {};
  return resolveConfigTemplates(rawConfig) as Record<string, unknown>;
}

async function loadBrainClawBridge(): Promise<{
  bridge: BrainClawBridgeModule;
  pluginConfig: Record<string, unknown>;
}> {
  const cfg = loadConfig() as Record<string, unknown>;
  const installPath = resolveBrainClawInstallPath(cfg);
  const pluginConfig = resolveBrainClawPluginConfig(cfg);
  const bridgePath = path.join(installPath, "dist", "bridge.js");
  const bridge = (await import(pathToFileURL(bridgePath).href)) as BrainClawBridgeModule;
  if (typeof bridge.callPythonBackend !== "function") {
    throw new Error("BrainClaw bridge entrypoint is unavailable.");
  }
  return { bridge, pluginConfig };
}

function assertNoBridgeError(result: unknown): void {
  if (
    result &&
    typeof result === "object" &&
    "error" in result &&
    typeof (result as { error?: unknown }).error === "string"
  ) {
    throw new Error((result as { error: string }).error);
  }
}

export async function listAgentBrainClawMemories(
  params: AgentsBrainClawMemoryListParams,
): Promise<AgentsBrainClawMemoryListResult> {
  const { bridge, pluginConfig } = await loadBrainClawBridge();
  const result = await bridge.callPythonBackend(
    "bridge_entrypoints",
    "list_memories",
    {
      agent_id: params.agentId,
      query: params.query ?? "",
      area: params.area ?? "all",
      limit: params.limit ?? 25,
      page: params.page ?? 1,
      threshold: params.threshold ?? 0.6,
      include_superseded: params.includeSuperseded ?? false,
    },
    pluginConfig,
    { agentId: params.agentId, agentName: params.agentId },
  );
  assertNoBridgeError(result);
  return result as AgentsBrainClawMemoryListResult;
}

export async function updateAgentBrainClawMemory(
  params: AgentsBrainClawMemoryUpdateParams,
): Promise<AgentsBrainClawMemoryUpdateResult> {
  const { bridge, pluginConfig } = await loadBrainClawBridge();
  const result = await bridge.callPythonBackend(
    "bridge_entrypoints",
    "update_memory",
    {
      agent_id: params.agentId,
      memory_id: params.memoryId,
      content: params.content,
      reason: params.reason ?? "Edited from OpenClaw Control UI",
    },
    pluginConfig,
    { agentId: params.agentId, agentName: params.agentId },
  );
  assertNoBridgeError(result);
  return result as AgentsBrainClawMemoryUpdateResult;
}

export async function syncAgentBrainClawMemoryBackup(params: {
  agentId: string;
  content: string;
  filePath: string;
}): Promise<{
  ok: boolean;
  agentId: string;
  filePath: string;
  mirroredEntryCount: number;
  snapshotId?: string | null;
}> {
  const { bridge, pluginConfig } = await loadBrainClawBridge();
  const result = await bridge.callPythonBackend(
    "bridge_entrypoints",
    "sync_memory_md_backup",
    {
      agent_id: params.agentId,
      content: params.content,
      file_path: params.filePath,
      reason: "Synchronized from OpenClaw MEMORY.md editor",
    },
    pluginConfig,
    { agentId: params.agentId, agentName: params.agentId },
  );
  assertNoBridgeError(result);
  return result as {
    ok: boolean;
    agentId: string;
    filePath: string;
    mirroredEntryCount: number;
    snapshotId?: string | null;
  };
}
