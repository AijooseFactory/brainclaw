import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const filesToCheck = [
  "src/services/entity_extractor.ts",
  "src/services/summarizer.ts",
  "src/services/contradiction_detector.ts",
  "python/openclaw_memory/bridge_entrypoints.py",
  "python/openclaw_memory/config.py",
  "python/openclaw_memory/storage/neo4j_client.py",
  "python/openclaw_memory/migration/lcm_export.py",
];

const bannedLiterals = [
  "ajf-openclaw",
  "ai_joose_factory",
  "ajf-openclaw-graphdb",
  "ajf-neo4j-host-proxy",
  "agent-001-uuid",
  "agent-002-uuid",
  "agent-003-uuid",
  "agent-004-uuid",
  "agent-005-uuid",
  "agent-unknown",
  "team-default",
  "tenant-default",
  "default-team",
];

test("Portability: runtime code avoids instance-specific defaults and ajf-specific literals", () => {
  const violations = [];

  for (const relativePath of filesToCheck) {
    const absolutePath = path.join(repoRoot, relativePath);
    const source = fs.readFileSync(absolutePath, "utf8");

    for (const literal of bannedLiterals) {
      if (source.includes(literal)) {
        violations.push(`${relativePath}: ${literal}`);
      }
    }
  }

  assert.deepStrictEqual(
    violations,
    [],
    `Found instance-specific or fabricated defaults:\n${violations.join("\n")}`,
  );
});
