import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

import brainclawPlugin from "../dist/index.js";

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

test("BrainClaw manifest exposes Lossless-Claw integration configuration", () => {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(repoRoot, "openclaw.plugin.json"), "utf8"),
  );
  const properties = manifest.configSchema?.properties ?? {};

  for (const key of [
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
