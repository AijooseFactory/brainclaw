import path from "node:path";

const MEMORY_BOOTSTRAP_FILENAMES = new Set(["MEMORY.md", "memory.md"]);

export function isBrainClawActiveMemoryPlugin(config: any, pluginId = "brainclaw"): boolean {
  return config?.plugins?.slots?.memory === pluginId;
}

export function shouldEnableFeature(value: unknown, defaultValue = true): boolean {
  return typeof value === "boolean" ? value : defaultValue;
}

export function resolvePositiveInteger(
  primary: unknown,
  fallback: unknown,
  defaultValue: number,
): number {
  const candidates = [primary, fallback, defaultValue];
  for (const candidate of candidates) {
    if (Number.isInteger(candidate) && Number(candidate) > 0) {
      return Number(candidate);
    }
  }
  return defaultValue;
}

export function isMemoryBootstrapFile(file: any): boolean {
  if (typeof file?.name === "string" && MEMORY_BOOTSTRAP_FILENAMES.has(file.name)) {
    return true;
  }

  if (typeof file?.path === "string" && file.path.trim()) {
    return MEMORY_BOOTSTRAP_FILENAMES.has(path.basename(file.path.trim()));
  }

  return false;
}

export function extractMessageText(message: any): string {
  const rawContent = message?.message?.content ?? message?.content;
  if (typeof rawContent === "string") {
    return rawContent.trim();
  }

  if (!Array.isArray(rawContent)) {
    return "";
  }

  const parts = rawContent
    .map((block) => {
      if (typeof block === "string") {
        return block.trim();
      }
      if (!block || typeof block !== "object") {
        return "";
      }
      if (typeof block.text === "string") {
        return block.text.trim();
      }
      if (block.type === "text" && typeof block.text === "string") {
        return block.text.trim();
      }
      if (block.type === "input_text" && typeof block.text === "string") {
        return block.text.trim();
      }
      return "";
    })
    .filter(Boolean);

  return parts.join("\n").trim();
}

export function findLatestMessageText(messages: unknown[], role: string): string {
  const entries = Array.isArray(messages) ? messages : [];
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry: any = entries[index];
    if ((entry?.message?.role ?? entry?.role) !== role) {
      continue;
    }
    const text = extractMessageText(entry);
    if (text) {
      return text;
    }
  }
  return "";
}
