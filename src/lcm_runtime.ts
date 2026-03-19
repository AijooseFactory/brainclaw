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

function resolveOpenClawVersion(config: any, runtimeVersion?: string): string {
  if (typeof runtimeVersion === "string" && runtimeVersion.trim()) {
    const normalizedRuntimeVersion = runtimeVersion.trim();
    if (normalizedRuntimeVersion.toLowerCase() !== "unknown") {
      return normalizedRuntimeVersion;
    }
  }

  const configuredVersion = config?.meta?.lastTouchedVersion;
  if (typeof configuredVersion === "string" && configuredVersion.trim()) {
    return configuredVersion.trim();
  }

  const packageJson = safeReadJson("/app/package.json");
  const packageVersion = packageJson?.version;
  if (typeof packageVersion === "string" && packageVersion.trim()) {
    return packageVersion.trim();
  }

  return "unknown";
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

function collectToolNamesFromRuntimeConfig(config: any): string[] {
  const candidates = [
    config?.plugins?.runtimeToolNames?.["lossless-claw"],
    config?.plugins?.toolNames?.["lossless-claw"],
    config?.plugins?.registry?.["lossless-claw"]?.toolNames,
    config?.plugins?.entries?.["lossless-claw"]?.toolNames,
  ];

  const toolNames = new Set<string>();
  for (const value of candidates) {
    if (!Array.isArray(value)) {
      continue;
    }
    for (const item of value) {
      if (typeof item === "string" && item.trim()) {
        toolNames.add(item.trim());
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
  const pluginEntry = params.config?.plugins?.entries?.["lossless-claw"];
  const pluginRegistered = Boolean(pluginEntry);
  const losslessInstall = installs["lossless-claw"] as PluginInstallRecord | undefined;
  const installPath = pluginConfig.losslessClawPluginPath || losslessInstall?.installPath;
  const runtimeToolNames = collectToolNamesFromRuntimeConfig(params.config);
  const discoveredToolNames =
    runtimeToolNames.length > 0
      ? runtimeToolNames
      : collectToolNamesFromInstallPath(installPath);

  return {
    openclaw_version: resolveOpenClawVersion(params.config, params.runtimeVersion),
    memory_slot: typeof slots.memory === "string" ? slots.memory : null,
    context_engine_slot: typeof slots.contextEngine === "string" ? slots.contextEngine : null,
    plugin_installed: Boolean(losslessInstall),
    plugin_registered: pluginRegistered,
    plugin_enabled:
      pluginConfig.losslessClawEnabled !== false &&
      pluginRegistered &&
      (pluginEntry?.enabled ?? true) !== false,
    plugin_version: losslessInstall?.version || null,
    plugin_install_path: installPath || null,
    tool_names: discoveredToolNames,
    tool_source: runtimeToolNames.length > 0 ? "runtime_registry" : "install_path_scan",
  };
}
