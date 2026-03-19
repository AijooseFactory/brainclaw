import { test } from "node:test";
import assert from "node:assert";
import { callPythonBackend, setSpawn } from "../dist/bridge.js";
import { buildLosslessClawRuntimeSnapshot } from "../dist/lcm_runtime.js";

const baseBridgeConfig = {
  brainclawSecret: "test-secret",
};

test("Bridge Security: Unauthorized routing rejection", async () => {
  try {
    await callPythonBackend("invalid_module", "invalid_func", {});
    assert.fail("Should have thrown a security error");
  } catch (e) {
    assert.ok(e.message.includes("Security Block"), "Error should mention security block");
  }
});

test("Bridge Lifecycle: Timeout enforcement", async () => {
  // Use setSpawn to mock the process
  setSpawn(() => ({
    stdout: { on: () => {} },
    stderr: { on: () => {} },
    on: () => {},
    kill: (signal) => {
      assert.strictEqual(signal, 'SIGTERM');
    }
  }));

  const config = { ...baseBridgeConfig, pythonTimeoutMs: 10 };
  try {
    await callPythonBackend("retrieval", "classify", { query: "test" }, config);
    assert.fail("Should have timed out");
  } catch (e) {
    assert.ok(e.message.includes("Timeout"), "Error should mention timeout");
  } finally {
    // Restore default (would need to import the real spawn to fully restore, 
    // but for unit tests we can just leave it or use a better cleanup)
  }
});

test("Bridge Success: Integration with retrieval (MOCKED)", async () => {
  const mockResult = { primary_intent: "search" };
  
  setSpawn(() => ({
    stdout: { on: (event, cb) => {
      if (event === "data") cb(Buffer.from(JSON.stringify(mockResult)));
    }},
    stderr: { on: () => {} },
    on: (event, cb) => {
      if (event === "close") cb(0);
    },
    kill: () => {}
  }));

  const config = { ...baseBridgeConfig, pythonTimeoutMs: 5000 };
  try {
    const result = await callPythonBackend("retrieval", "classify", { query: "search test" }, config);
    assert.strictEqual(result.primary_intent, "search");
  } finally {
    // cleanup
  }
});

test("Bridge Sanitization: Error message stripping", async () => {
  setSpawn(() => ({
    stdout: { on: (event, cb) => {
      if (event === "data") cb(Buffer.from(JSON.stringify({ error: "Traceback (most recent call last):\n  File \"/Users/george/test.py\", line 1" })));
    }},
    stderr: { on: () => {} },
    on: (event, cb) => {
      if (event === "close") cb(0);
    },
    kill: () => {}
  }));

  try {
    await callPythonBackend("retrieval", "classify", { query: "error test" }, baseBridgeConfig);
    assert.fail("Should have thrown a Python error");
  } catch (e) {
    assert.ok(!e.message.includes("/Users/"), "Error should not leak local paths");
    assert.ok(!e.message.includes("Traceback"), "Error should be sanitized");
  } finally {
    // cleanup
  }
});

test("Bridge Error Handling: parses JSON error payloads from non-zero Python exits", async () => {
  setSpawn(() => ({
    stdout: {
      on(event, cb) {
        if (event === "data") {
          cb(Buffer.from(JSON.stringify({ error: "relation integration_states does not exist" })));
        }
      },
    },
    stderr: { on: () => {} },
    on(event, cb) {
      if (event === "close") cb(1);
    },
    kill() {},
  }));

  try {
    await callPythonBackend("bridge_entrypoints", "lcm_status", {}, baseBridgeConfig);
    assert.fail("Should have surfaced JSON error payload from Python");
  } catch (e) {
    assert.ok(
      e.message.includes("integration_states"),
      "Expected parsed Python error message from stdout JSON payload",
    );
  }
});

test("Bridge Parsing: accepts trailing JSON after backend log noise", async () => {
  setSpawn(() => ({
    stdout: {
      on(event, cb) {
        if (event === "data") {
          cb(
            Buffer.from(
              [
                'HTTP Request: GET http://weaviate:8080/v1/meta "HTTP/1.1 200 OK"',
                '{"results":[{"id":"mem-1","content":"PostgreSQL is canonical."}],"total":1}',
              ].join("\n"),
            ),
          );
        }
      },
    },
    stderr: { on: () => {} },
    on(event, cb) {
      if (event === "close") cb(0);
    },
    kill() {},
  }));

  const result = await callPythonBackend(
    "bridge_entrypoints",
    "retrieve_sync",
    { query: "canonical ledger" },
    baseBridgeConfig,
  );

  assert.strictEqual(result.total, 1);
  assert.strictEqual(result.results[0].id, "mem-1");
});

test("Bridge Config: Custom pythonPath and pythonBackendPath", async () => {
  let capturedExecutable = "";
  let capturedArgs = [];
  
  setSpawn((executable, args) => {
    capturedExecutable = executable;
    capturedArgs = args;
    return {
      stdout: { on: (event, cb) => {
        if (event === "data") cb(Buffer.from(JSON.stringify({ primary_intent: "test" })));
      }},
      stderr: { on: () => {} },
      on: (event, cb) => {
        if (event === "close") cb(0);
      },
      kill: () => {}
    };
  });

  const config = { 
    ...baseBridgeConfig,
    pythonPath: "/custom/bin/python",
    pythonBackendPath: "/custom/lib/openclaw",
    pythonTimeoutMs: 5000
  };
  
  try {
    await callPythonBackend("retrieval", "classify", { query: "test" }, config);
    assert.strictEqual(capturedExecutable, "/custom/bin/python", "Should use custom python executable");
    assert.ok(capturedArgs[1].includes("/custom/lib/openclaw"), "Should use custom python backend path in sys.path.append");
  } finally {
    // cleanup
  }
});

test("Bridge Identity: does not fabricate team or tenant defaults when runtime context is missing", async () => {
  let capturedEnv;

  setSpawn((_executable, _args, options) => {
    capturedEnv = options.env;
    return {
      stdout: { on: (event, cb) => {
        if (event === "data") cb(Buffer.from(JSON.stringify({ primary_intent: "search" })));
      }},
      stderr: { on: () => {} },
      on: (event, cb) => {
        if (event === "close") cb(0);
      },
      kill: () => {}
    };
  });

  const config = {
    ...baseBridgeConfig,
    pythonPath: "/custom/bin/python",
    pythonBackendPath: "/custom/lib/openclaw",
    pythonTimeoutMs: 5000
  };

  await callPythonBackend("bridge_entrypoints", "classify", { query: "portable context" }, config, {});

  const identityToken = capturedEnv.BRAINCLAW_IDENTITY_TOKEN;
  assert.ok(identityToken, "Expected an identity token to be passed to the Python backend");

  const decoded = JSON.parse(Buffer.from(identityToken, "base64").toString("utf8"));

  assert.ok(!("teamId" in decoded), "teamId should be omitted when OpenClaw does not provide one");
  assert.ok(!("tenantId" in decoded), "tenantId should be omitted when OpenClaw does not provide one");
  assert.strictEqual(capturedEnv.TEAM_ID, undefined, "TEAM_ID should not be fabricated by the bridge");
});

test("Bridge Security: allows Lossless-Claw integration bridge entrypoints", async () => {
  const calls = [];

  setSpawn((_executable, args) => {
    calls.push(args[1]);
    return {
      stdout: {
        on(event, cb) {
          if (event === "data") cb(Buffer.from(JSON.stringify({ status: "ok" })));
        },
      },
      stderr: { on: () => {} },
      on(event, cb) {
        if (event === "close") cb(0);
      },
      kill() {},
    };
  });

  await callPythonBackend("bridge_entrypoints", "lcm_status", {}, baseBridgeConfig);
  await callPythonBackend("bridge_entrypoints", "lcm_sync", { mode: "bootstrap" }, baseBridgeConfig);
  await callPythonBackend("bridge_entrypoints", "lcm_rebuild", { target: "neo4j" }, baseBridgeConfig);

  assert.strictEqual(calls.length, 3);
});

test("Bridge Security: allows operational memory sync bridge entrypoint", async () => {
  const calls = [];

  setSpawn((_executable, args) => {
    calls.push(args[1]);
    return {
      stdout: {
        on(event, cb) {
          if (event === "data") cb(Buffer.from(JSON.stringify({ status: "ok", target_count: 5 })));
        },
      },
      stderr: { on: () => {} },
      on(event, cb) {
        if (event === "close") cb(0);
      },
      kill() {},
    };
  });

  const result = await callPythonBackend(
    "bridge_entrypoints",
    "sync_operational_memory_files",
    {},
    baseBridgeConfig,
  );

  assert.strictEqual(result.status, "ok");
  assert.strictEqual(calls.length, 1);
});

test("LCM Runtime: falls back when runtime version is unavailable or unknown", () => {
  const runtime = buildLosslessClawRuntimeSnapshot({
    config: {
      meta: { lastTouchedVersion: "2026.3.14" },
      plugins: {
        slots: { memory: "brainclaw", contextEngine: "lossless-claw" },
        installs: {
          "lossless-claw": {
            installPath: "/tmp/lossless-claw-sync",
            version: "0.4.0",
          },
        },
      },
    },
    pluginConfig: {},
    runtimeVersion: "unknown",
  });

  assert.strictEqual(runtime.openclaw_version, "2026.3.14");
});

test("LCM Runtime: marks install as unregistered when plugin entry is missing", () => {
  const runtime = buildLosslessClawRuntimeSnapshot({
    config: {
      plugins: {
        slots: { memory: "brainclaw", contextEngine: "lossless-claw" },
        installs: {
          "lossless-claw": {
            installPath: "/tmp/lossless-claw-sync",
            version: "0.4.0",
          },
        },
        entries: {},
      },
    },
    pluginConfig: {},
    runtimeVersion: "2026.3.14",
  });

  assert.strictEqual(runtime.plugin_installed, true);
  assert.strictEqual(runtime.plugin_registered, false);
  assert.strictEqual(runtime.plugin_enabled, false);
});
