/**
 * File-watcher service for MEMORY.md bidirectional sync.
 *
 * Monitors each configured agent's MEMORY.md file for external changes
 * (edits made outside the Control UI — e.g. VS Code, agent file writes,
 * scripts) and pushes the updated content into BrainClaw's canonical
 * Postgres memory via the `sync_memory_md_backup` bridge entry point.
 *
 * This closes the last gap in the bidirectional sync contract:
 *   DB → MEMORY.md  is already handled by ingest_event / update_memory
 *   MEMORY.md → DB  is handled by agents.files.set (Control UI)
 *                     AND by this watcher (external edits)
 *
 * Uses fs.watchFile (stat polling) rather than fs.watch for cross-platform
 * reliability — fs.watch on macOS can miss events for symlinked paths
 * and behaves inconsistently across file systems.
 */

import { watchFile, unwatchFile, readFileSync, existsSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { callPythonBackend } from "../bridge.js";
import { getLogger } from "../logging.js";
import { resolveBrainclawPluginConfig } from "../lcm_runtime.js";

const DEFAULT_POLL_INTERVAL_MS = 2000;
const MEMORY_FILE_NAME = "MEMORY.md";

interface AgentEntry {
  id: string;
  workspace?: string;
  agentDir?: string;
}

type WatcherState = {
  filePath: string;
  lastHash: string;
  syncing: boolean;
};

function sha256(content: string): string {
  return createHash("sha256").update(content, "utf8").digest("hex");
}

function resolveAgentMemoryPaths(config: any): Array<{ agentId: string; filePath: string }> {
  const stateDir: string =
    process.env.OPENCLAW_STATE_DIR || "/home/node/.openclaw";
  const entries: AgentEntry[] =
    config?.agents?.list ?? config?.agents?.entries ?? [];

  const result: Array<{ agentId: string; filePath: string }> = [];

  // Root / main agent memory
  const rootMemory =
    process.env.OPENCLAW_ROOT_MEMORY_PATH ||
    config?.plugins?.entries?.brainclaw?.config?.operationalMemoryRootPath;
  if (rootMemory && typeof rootMemory === "string") {
    result.push({ agentId: "main", filePath: rootMemory });
  }

  for (const entry of entries) {
    if (!entry?.id) continue;
    const dir =
      entry.agentDir ||
      entry.workspace ||
      path.join(stateDir, "agents", entry.id, "agent");
    result.push({
      agentId: entry.id,
      filePath: path.join(dir, MEMORY_FILE_NAME),
    });
  }

  return result;
}

function readFileSafe(filePath: string): string | null {
  try {
    if (!existsSync(filePath)) return null;
    const stat = statSync(filePath);
    if (!stat.isFile()) return null;
    return readFileSync(filePath, "utf8");
  } catch {
    return null;
  }
}

export function createMemoryFileWatcher(params: {
  pluginConfig: Record<string, any>;
  config: any;
  pollIntervalMs?: number;
}): { stop: () => void } {
  const logger = getLogger();
  const pollIntervalMs = params.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const targets = resolveAgentMemoryPaths(params.config);
  const watchers = new Map<string, WatcherState>();

  function syncFile(agentId: string, filePath: string, content: string) {
    const state = watchers.get(agentId);
    if (state) state.syncing = true;

    callPythonBackend(
      "bridge_entrypoints",
      "sync_memory_md_backup",
      {
        agent_id: agentId,
        content,
        file_path: filePath,
        reason: "Synchronized from external MEMORY.md edit (file watcher)",
      },
      params.pluginConfig,
      { agentId, agentName: agentId },
    )
      .then((result: any) => {
        logger.info(
          "memory_file_watcher",
          "sync",
          `Synced external MEMORY.md edit for agent "${agentId}"`,
          {
            agentId,
            filePath,
            mirroredEntryCount: result?.mirroredEntryCount ?? 0,
            updatedMemoryIds: result?.updatedMemoryIds ?? [],
          },
        );
      })
      .catch((error: unknown) => {
        const message =
          error instanceof Error ? error.message : String(error);
        logger.warn(
          "memory_file_watcher",
          "sync",
          `Failed to sync external MEMORY.md edit for agent "${agentId}": ${message}`,
          { agentId, filePath },
        );
      })
      .finally(() => {
        if (state) state.syncing = false;
      });
  }

  function startWatching(agentId: string, filePath: string) {
    const initialContent = readFileSafe(filePath);
    const initialHash = initialContent !== null ? sha256(initialContent) : "";

    const state: WatcherState = {
      filePath,
      lastHash: initialHash,
      syncing: false,
    };
    watchers.set(agentId, state);

    watchFile(filePath, { persistent: true, interval: pollIntervalMs }, (curr, prev) => {
      // File deleted or not yet created
      if (curr.mtimeMs === 0) return;

      // No actual modification
      if (curr.mtimeMs === prev.mtimeMs && curr.size === prev.size) return;

      // Already syncing — skip to avoid races
      if (state.syncing) return;

      const content = readFileSafe(filePath);
      if (content === null) return;

      const hash = sha256(content);
      if (hash === state.lastHash) return; // No actual content change

      state.lastHash = hash;
      syncFile(agentId, filePath, content);
    });
  }

  // Start watching all known agent MEMORY.md files
  for (const { agentId, filePath } of targets) {
    startWatching(agentId, filePath);
  }

  if (targets.length > 0) {
    logger.info(
      "memory_file_watcher",
      "start",
      `Watching ${targets.length} MEMORY.md file(s) for external edits`,
      {
        pollIntervalMs,
        targets: targets.map((t) => ({ agentId: t.agentId, filePath: t.filePath })),
      },
    );
  }

  return {
    stop() {
      for (const [, state] of watchers) {
        unwatchFile(state.filePath);
      }
      watchers.clear();
      logger.info("memory_file_watcher", "stop", "Memory file watcher stopped");
    },
  };
}

export const memoryFileWatcherService = {
  id: "brainclaw-memory-file-watcher",
  description:
    "Watches agent MEMORY.md files for external edits and syncs changes into BrainClaw canonical memory.",
  async start(ctx: any) {
    const logger = getLogger();
    const config = ctx.config ?? {};
    const pluginConfig = resolveBrainclawPluginConfig(config);

    if (pluginConfig.memoryFileWatcherEnabled === false) {
      logger.info(
        "memory_file_watcher",
        "start",
        "Memory file watcher disabled by configuration",
      );
      return { stop() {} };
    }

    const instance = createMemoryFileWatcher({
      pluginConfig,
      config,
      pollIntervalMs: pluginConfig.memoryFileWatcherPollIntervalMs,
    });

    return {
      stop() {
        instance.stop();
      },
    };
  },
};

export function registerMemoryFileWatcherService(api: any) {
  api.registerBackgroundService?.(memoryFileWatcherService);
}
