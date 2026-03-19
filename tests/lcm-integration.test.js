import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

import brainclawPlugin from "../dist/index.js";
import { registerBrainclawCli } from "../dist/register_cli.js";

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

test("BrainClaw manifest exposes Lossless-Claw integration configuration", () => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(repoRoot, "openclaw.plugin.json"), "utf8"),
  );
  const properties = manifest.configSchema?.properties ?? {};

  for (const key of [
    "operationalMemorySyncEnabled",
    "operationalMemorySyncIntervalMs",
    "operationalMemoryPrimaryAgentId",
    "operationalMemoryRootPath",
    "losslessClawEnabled",
    "losslessClawPluginPath",
    "losslessClawDbPath",
    "losslessClawBootstrapOnStart",
    "losslessClawPollIntervalMs",
    "losslessClawDrillDownEnabled",
    "losslessClawArtifactQuotaBytes",
    "losslessClawAnchorByteCap",
    "losslessClawLargeFileMode",
    "losslessClawTrustMode",
  ]) {
    assert.ok(properties[key], `Expected plugin manifest config property ${key}`);
  }
});

test("BrainClaw manifest publishes runtime gate and CLI contract metadata", () => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(repoRoot, "openclaw.plugin.json"), "utf8"),
  );
  const contract = manifest.lcmContract ?? {};

  assert.deepStrictEqual(contract.compatibilityStates, [
    "not_installed",
    "installed_compatible",
    "installed_degraded",
    "installed_incompatible",
    "installed_unreachable",
  ]);
  assert.ok(
    Array.isArray(contract.runtimeGateChecks) && contract.runtimeGateChecks.length >= 6,
    "Expected runtime gate checks in manifest metadata",
  );
  assert.ok(
    Array.isArray(contract.operationalCommands) && contract.operationalCommands.includes("brainclaw lcm status"),
    "Expected CLI contract commands in manifest metadata",
  );
});

test("BrainClaw registers Lossless-Claw integration service and CLI surfaces", () => {
  const registeredServices = [];
  const registeredCli = [];

  const api = {
    logger: {
      child() {
        return this;
      },
      info() {},
      warn() {},
      error() {},
      debug() {},
    },
    registerTool() {},
    registerHook() {},
    on() {},
    registerBackgroundService(service) {
      registeredServices.push(service);
    },
    registerCli(registrar, options) {
      registeredCli.push({ registrar, options });
    },
    config: { plugins: { slots: { memory: "brainclaw", contextEngine: "lossless-claw" } } },
    pluginConfig: {},
    runtime: {
      config: {
        loadConfig() {
          return { plugins: { slots: { memory: "brainclaw", contextEngine: "lossless-claw" } } };
        },
      },
    },
    id: "brainclaw",
  };

  brainclawPlugin(api);

  assert.ok(
    registeredServices.some((service) => service?.id === "brainclaw-lossless-claw-integration"),
    "Expected BrainClaw to register the Lossless-Claw integration background service",
  );
  assert.ok(
    registeredCli.some(({ options }) => options?.commands?.includes("brainclaw")),
    "Expected BrainClaw to register the brainclaw CLI surface",
  );
});

test("BrainClaw CLI exposes a memory sync command", () => {
  let registrar;

  function createCommand(name) {
    return {
      name,
      children: [],
      description() {
        return this;
      },
      command(childName) {
        const child = createCommand(childName);
        this.children.push(child);
        return child;
      },
      requiredOption() {
        return this;
      },
      action(handler) {
        this.handler = handler;
        return this;
      },
    };
  }

  registerBrainclawCli({
    registerCli(fn) {
      registrar = fn;
    },
  });

  const program = createCommand("root");
  registrar({
    program,
    config: { plugins: { entries: { brainclaw: { config: {} } } } },
    logger: { info() {} },
  });

  const brainclaw = program.children.find((entry) => entry.name === "brainclaw");
  assert.ok(brainclaw, "Expected root brainclaw command");

  const memory = brainclaw.children.find((entry) => entry.name === "memory");
  assert.ok(memory, "Expected brainclaw memory command");

  const sync = memory.children.find((entry) => entry.name === "sync");
  assert.ok(sync, "Expected brainclaw memory sync command");
  assert.strictEqual(typeof sync.handler, "function");
});
