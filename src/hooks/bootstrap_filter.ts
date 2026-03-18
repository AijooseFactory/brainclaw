import { getLogger } from "../logging.js";
import {
  isBrainClawActiveMemoryPlugin,
  isMemoryBootstrapFile,
  shouldEnableFeature,
} from "./shared.js";

export function filterBootstrapFilesForBrainClaw(files: any[]): any[] {
  return (Array.isArray(files) ? files : []).filter((file) => !isMemoryBootstrapFile(file));
}

export function registerBootstrapFilterHook(api: any) {
  api.registerHook?.(
    "agent:bootstrap",
    async (event: any) => {
      const cfg = event?.context?.cfg ?? api?.config;
      const pluginConfig = api?.pluginConfig ?? {};
      if (!shouldEnableFeature(pluginConfig.suppressMemoryBootstrap, true)) {
        return;
      }
      if (!isBrainClawActiveMemoryPlugin(cfg, api?.id ?? "brainclaw")) {
        return;
      }

      const currentFiles = event?.context?.bootstrapFiles;
      if (!Array.isArray(currentFiles) || currentFiles.length === 0) {
        return;
      }

      const filteredFiles = filterBootstrapFilesForBrainClaw(currentFiles);
      if (filteredFiles.length === currentFiles.length) {
        return;
      }

      event.context.bootstrapFiles = filteredFiles;
      getLogger().info(
        "bootstrap-filter",
        "agent_bootstrap",
        "Removed MEMORY.md from bootstrap context because BrainClaw is the active memory plugin",
        {
          removed: currentFiles.length - filteredFiles.length,
          agentId: event?.context?.agentId,
        },
      );
    },
    {
      name: "brainclaw.agent-bootstrap-filter",
      description:
        "Removes MEMORY.md bootstrap injection when BrainClaw is the active durable memory plugin.",
    },
  );
}
