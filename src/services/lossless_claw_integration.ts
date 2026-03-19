import { callPythonBackend } from "../bridge.js";
import { getLogger } from "../logging.js";
import { buildLosslessClawRuntimeSnapshot, resolveBrainclawPluginConfig } from "../lcm_runtime.js";

export const losslessClawIntegrationService = {
  id: "brainclaw-lossless-claw-integration",
  description: "Detects, gates, and incrementally syncs Lossless-Claw artifacts into BrainClaw.",
  async start(ctx: any) {
    const logger = getLogger();
    const config = ctx.config ?? {};
    const pluginConfig = resolveBrainclawPluginConfig(config);

    if (pluginConfig.losslessClawEnabled === false) {
      logger.info("lossless_claw_integration", "start", "Lossless-Claw integration disabled");
      return {
        stop() {
          logger.info("lossless_claw_integration", "stop", "Lossless-Claw integration disabled");
        },
      };
    }

    const runtime = buildLosslessClawRuntimeSnapshot({
      config,
      pluginConfig,
      runtimeVersion: process.env.OPENCLAW_VERSION,
    });

    logger.info("lossless_claw_integration", "start", "Lossless-Claw integration service active", {
      poll_interval_ms: pluginConfig.losslessClawPollIntervalMs ?? 60000,
    });

    try {
      const status = await callPythonBackend(
        "bridge_entrypoints",
        "lcm_status",
        { runtime, plugin_config: pluginConfig },
        pluginConfig,
      );
      logger.info("lossless_claw_integration", "gate", "Lossless-Claw runtime gate evaluated", {
        compatibility_state: status.compatibility_state,
        reason_code: status.reason_code ?? null,
      });
      if (
        pluginConfig.losslessClawBootstrapOnStart !== false &&
        status.compatibility_state === "installed_compatible"
      ) {
        await callPythonBackend(
          "bridge_entrypoints",
          "lcm_sync",
          { runtime, plugin_config: pluginConfig, mode: "bootstrap" },
          pluginConfig,
        );
      }
    } catch (error) {
      logger.error("lossless_claw_integration", "gate", error as Error);
    }

    const interval = setInterval(async () => {
      try {
        await callPythonBackend(
          "bridge_entrypoints",
          "lcm_sync",
          { runtime, plugin_config: pluginConfig, mode: "incremental" },
          pluginConfig,
        );
      } catch (error) {
        logger.error("lossless_claw_integration", "incremental_sync", error as Error);
      }
    }, pluginConfig.losslessClawPollIntervalMs ?? 60000);

    return {
      stop() {
        clearInterval(interval);
        logger.info("lossless_claw_integration", "stop", "Lossless-Claw integration service stopped");
      },
    };
  },
};

export function registerLosslessClawIntegrationService(api: any) {
  api.registerBackgroundService?.(losslessClawIntegrationService);
}
