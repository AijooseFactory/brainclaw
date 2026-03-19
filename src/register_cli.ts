import { callPythonBackend } from "./bridge.js";
import { buildLosslessClawRuntimeSnapshot, resolveBrainclawPluginConfig } from "./lcm_runtime.js";

function printJson(value: unknown) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

export function registerBrainclawCli(api: any) {
  api.registerCli?.(({ program, config, logger }: any) => {
    const brainclaw = program.command("brainclaw").description("BrainClaw operational commands");
    const lcm = brainclaw.command("lcm").description("Lossless-Claw integration commands");

    lcm.command("status").action(async () => {
      const pluginConfig = resolveBrainclawPluginConfig(config);
      const runtime = buildLosslessClawRuntimeSnapshot({
        config,
        pluginConfig,
        runtimeVersion: api.runtime?.version,
      });
      const result = await callPythonBackend(
        "bridge_entrypoints",
        "lcm_status",
        { runtime, plugin_config: pluginConfig },
        pluginConfig,
      );
      printJson(result);
    });

    lcm
      .command("sync")
      .requiredOption("--mode <mode>", "bootstrap | incremental | repair")
      .action(async (opts: { mode: string }) => {
        const pluginConfig = resolveBrainclawPluginConfig(config);
        const runtime = buildLosslessClawRuntimeSnapshot({
          config,
          pluginConfig,
          runtimeVersion: api.runtime?.version,
        });
        const result = await callPythonBackend(
          "bridge_entrypoints",
          "lcm_sync",
          { runtime, plugin_config: pluginConfig, mode: opts.mode },
          pluginConfig,
        );
        printJson(result);
      });

    brainclaw
      .command("rebuild")
      .requiredOption("--target <target>", "weaviate | neo4j")
      .action(async (opts: { target: string }) => {
        const pluginConfig = resolveBrainclawPluginConfig(config);
        const result = await callPythonBackend(
          "bridge_entrypoints",
          "lcm_rebuild",
          { target: opts.target },
          pluginConfig,
        );
        printJson(result);
      });

    logger.info?.("[brainclaw] registered CLI commands: brainclaw lcm status|sync, brainclaw rebuild");
  }, { commands: ["brainclaw"] });
}
