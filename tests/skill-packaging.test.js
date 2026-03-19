import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

test("BrainClaw ships a generic memory-data-engineer skill", () => {
  const genericSkillPath = path.join(repoRoot, "skills", "memory-data-engineer", "SKILL.md");
  const legacySkillPath = path.join(repoRoot, "skills", "lore", "SKILL.md");

  assert.ok(fs.existsSync(genericSkillPath), "Expected generic memory-data-engineer skill to be shipped");
  assert.ok(!fs.existsSync(legacySkillPath), "Expected legacy lore skill path to be removed from the shipped plugin");

  const source = fs.readFileSync(genericSkillPath, "utf8");

  assert.match(source, /^name:\s*memory-data-engineer$/m);
  assert.match(source, /^description:\s*Generic memory data engineering skill for any OpenClaw agent\./m);
  assert.match(source, /^# Memory Data Engineer$/m);
});
