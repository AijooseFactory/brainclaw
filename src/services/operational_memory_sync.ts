import { callPythonBackend } from "../bridge.js";
import { getLogger } from "../logging.js";
import { buildLosslessClawRuntimeSnapshot, resolveBrainclawPluginConfig } from "../lcm_runtime.js";

export const operationalMemorySyncService = {
  id: "brainclaw-operational-memory-sync",
  description: "Keeps root and agent MEMORY.md operational state blocks aligned with live BrainClaw status.",
  async start(ctx: any) {
    const logger = getLogger();
    const config = ctx.config ?? {};
    const pluginConfig = resolveBrainclawPluginConfig(config);

    if (pluginConfig.operationalMemorySyncEnabled === false) {
      logger.info("operational_memory_sync", "start", "Operational memory sync disabled");
      return {
        stop() {
          logger.info("operational_memory_sync", "stop", "Operational memory sync disabled");
        },
      };
    }

    const runtime = buildLosslessClawRuntimeSnapshot({
      config,
      pluginConfig,
      runtimeVersion: process.env.OPENCLAW_VERSION,
    });

    const runSync = async () => {
      try {
        await callPythonBackend(
          "bridge_entrypoints",
          "sync_operational_memory_files",
          { runtime, plugin_config: pluginConfig },
          pluginConfig,
        );
      } catch (error) {
        logger.error("operational_memory_sync", "sync", error as Error);
      }
    };

    await runSync();

    const interval = setInterval(runSync, pluginConfig.operationalMemorySyncIntervalMs ?? 300000);
    logger.info("operational_memory_sync", "start", "Operational memory sync service active", {
      interval_ms: pluginConfig.operationalMemorySyncIntervalMs ?? 300000,
    });

    return {
      stop() {
        clearInterval(interval);
        logger.info("operational_memory_sync", "stop", "Operational memory sync service stopped");
      },
    };
  },
};

export function registerOperationalMemorySyncService(api: any) {
  api.registerBackgroundService?.(operationalMemorySyncService);
}
