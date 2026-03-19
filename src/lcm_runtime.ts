import fs from "node:fs";
import path from "node:path";

type PluginInstallRecord = {
  installPath?: string;
  version?: string;
};

function safeReadJson(filePath: string): Record<string, unknown> | null {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return null;
  }
}

function collectToolNamesFromInstallPath(installPath?: string): string[] {
  if (!installPath) {
    return [];
  }

  const manifest = safeReadJson(path.join(installPath, "openclaw.plugin.json"));
  const toolNames = new Set<string>();
  const candidates = ["lcm_grep", "lcm_describe", "lcm_expand_query", "lcm_expand"];

  const manifestText = manifest ? JSON.stringify(manifest) : "";
  for (const candidate of candidates) {
    if (manifestText.includes(candidate)) {
      toolNames.add(candidate);
    }
  }

  const sourceDirs = [path.join(installPath, "src", "tools"), path.join(installPath, "dist", "tools")];
  const knownFiles = new Map<string, string>([
    ["lcm-grep-tool.ts", "lcm_grep"],
    ["lcm-describe-tool.ts", "lcm_describe"],
    ["lcm-expand-query-tool.ts", "lcm_expand_query"],
    ["lcm-expand-tool.ts", "lcm_expand"],
    ["lcm-grep-tool.js", "lcm_grep"],
    ["lcm-describe-tool.js", "lcm_describe"],
    ["lcm-expand-query-tool.js", "lcm_expand_query"],
    ["lcm-expand-tool.js", "lcm_expand"],
  ]);

  for (const sourceDir of sourceDirs) {
    if (!fs.existsSync(sourceDir)) {
      continue;
    }
    for (const fileName of fs.readdirSync(sourceDir)) {
      const toolName = knownFiles.get(fileName);
      if (toolName) {
        toolNames.add(toolName);
      }
    }
  }

  return [...toolNames];
}

export function resolveBrainclawPluginConfig(config: any): Record<string, any> {
  return (config?.plugins?.entries?.brainclaw?.config as Record<string, any>) ?? {};
}

export function buildLosslessClawRuntimeSnapshot(params: {
  config: any;
  pluginConfig?: Record<string, any>;
  runtimeVersion?: string;
}) {
  const pluginConfig = params.pluginConfig ?? resolveBrainclawPluginConfig(params.config);
  const installs = params.config?.plugins?.installs ?? {};
  const slots = params.config?.plugins?.slots ?? {};
  const losslessInstall = installs["lossless-claw"] as PluginInstallRecord | undefined;
  const installPath = pluginConfig.losslessClawPluginPath || losslessInstall?.installPath;

  return {
    openclaw_version: params.runtimeVersion || "unknown",
    memory_slot: typeof slots.memory === "string" ? slots.memory : null,
    context_engine_slot: typeof slots.contextEngine === "string" ? slots.contextEngine : null,
    plugin_installed: Boolean(losslessInstall),
    plugin_enabled:
      pluginConfig.losslessClawEnabled !== false &&
      (params.config?.plugins?.entries?.["lossless-claw"]?.enabled ?? true) !== false,
    plugin_version: losslessInstall?.version || null,
    plugin_install_path: installPath || null,
    tool_names: collectToolNamesFromInstallPath(installPath),
  };
}
