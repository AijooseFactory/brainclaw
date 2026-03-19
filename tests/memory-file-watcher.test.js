import { test, describe, afterEach } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

// The bridge requires BRAINCLAW_SECRET for HMAC token generation.
process.env.BRAINCLAW_SECRET = process.env.BRAINCLAW_SECRET || "test-secret-for-watcher-tests";

import { setSpawn } from "../dist/bridge.js";

/**
 * Tests for the BrainClaw MEMORY.md file watcher service.
 *
 * These tests verify the watcher service contract:
 *   - Correct service metadata and registration
 *   - Lifecycle management (start/stop, disable via config)
 *   - Integration: external MEMORY.md edits trigger sync_memory_md_backup
 *   - Content-hash deduplication prevents unnecessary syncs
 */

// Helper: create a temp directory with a MEMORY.md file
function makeTempAgent(content = "# Agent Memory\n\nInitial content.\n") {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "brainclaw-watcher-"));
  const filePath = path.join(dir, "MEMORY.md");
  fs.writeFileSync(filePath, content, "utf8");
  return { dir, filePath, cleanup: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

// Helper: stub the Python bridge spawn and resolve immediately
function stubBridge(response = { ok: true, mirroredEntryCount: 1 }) {
  const calls = [];
  setSpawn((_executable, args) => {
    const script = args[1];
    const params = JSON.parse(args[2]);
    calls.push({ script, params });
    return {
      stdout: {
        on: (event, cb) => {
          if (event === "data") cb(Buffer.from(JSON.stringify(response)));
        },
      },
      stderr: { on: () => {} },
      on: (event, cb) => {
        if (event === "close") setTimeout(() => cb(0), 0);
      },
      kill: () => {},
    };
  });
  return calls;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe("Memory File Watcher Service", () => {
  test("memoryFileWatcherService has correct service metadata", async () => {
    const { memoryFileWatcherService } = await import(
      "../dist/services/memory_file_watcher.js"
    );

    assert.strictEqual(memoryFileWatcherService.id, "brainclaw-memory-file-watcher");
    assert.strictEqual(typeof memoryFileWatcherService.description, "string");
    assert.ok(memoryFileWatcherService.description.length > 0);
    assert.strictEqual(typeof memoryFileWatcherService.start, "function");
  });

  test("memoryFileWatcherService start returns a handle with stop()", async () => {
    const { memoryFileWatcherService } = await import(
      "../dist/services/memory_file_watcher.js"
    );

    const handle = await memoryFileWatcherService.start({
      config: {
        brainclawSecret: "test-secret",
        pythonBackendPath: "/tmp/python",
      },
    });

    assert.strictEqual(typeof handle.stop, "function");
    handle.stop();
  });

  test("memoryFileWatcherService disabled via config returns noop stop", async () => {
    const { memoryFileWatcherService } = await import(
      "../dist/services/memory_file_watcher.js"
    );

    const handle = await memoryFileWatcherService.start({
      config: {
        brainclawSecret: "test-secret",
        plugins: {
          entries: {
            brainclaw: {
              config: { memoryFileWatcherEnabled: false },
            },
          },
        },
      },
    });

    assert.strictEqual(typeof handle.stop, "function");
    handle.stop();
  });

  test("registerMemoryFileWatcherService calls registerBackgroundService", async () => {
    const { registerMemoryFileWatcherService } = await import(
      "../dist/services/memory_file_watcher.js"
    );

    let registeredService = null;
    const mockApi = {
      registerBackgroundService: (service) => {
        registeredService = service;
      },
    };

    registerMemoryFileWatcherService(mockApi);
    assert.ok(registeredService !== null, "Should have registered a service");
    assert.strictEqual(registeredService.id, "brainclaw-memory-file-watcher");
  });
});

describe("createMemoryFileWatcher", () => {
  let tempAgent;
  let watcher;

  afterEach(() => {
    if (watcher) {
      watcher.stop();
      watcher = null;
    }
    if (tempAgent) {
      tempAgent.cleanup();
      tempAgent = null;
    }
  });

  test("detects external MEMORY.md edit and calls sync_memory_md_backup", async () => {
    tempAgent = makeTempAgent();
    const bridgeCalls = stubBridge();

    const { createMemoryFileWatcher } = await import(
      "../dist/services/memory_file_watcher.js"
    );

    watcher = createMemoryFileWatcher({
      pluginConfig: {
        brainclawSecret: "test-secret",
        pythonBackendPath: "/tmp/python",
      },
      config: {
        agents: {
          list: [{ id: "test-agent", workspace: tempAgent.dir }],
        },
      },
      pollIntervalMs: 100, // fast polling for testing
    });

    // Wait for first poll cycle to baseline
    await sleep(150);

    // Simulate an external edit
    fs.writeFileSync(tempAgent.filePath, "# Agent Memory\n\nModified by user.\n", "utf8");

    // Wait for poll to detect the change (poll interval + processing)
    const deadline = Date.now() + 3000;
    while (bridgeCalls.length === 0 && Date.now() < deadline) {
      await sleep(100);
    }

    assert.ok(bridgeCalls.length > 0, "Should have called sync_memory_md_backup");
    const call = bridgeCalls[0];
    assert.ok(
      call.script.includes("sync_memory_md_backup"),
      "Bridge script should import sync_memory_md_backup",
    );
    assert.strictEqual(call.params.agent_id, "test-agent");
    assert.ok(call.params.content.includes("Modified by user"));
  });

  test("no-op when content hash has not changed", async () => {
    tempAgent = makeTempAgent("# Static content\n");
    const bridgeCalls = stubBridge();

    const { createMemoryFileWatcher } = await import(
      "../dist/services/memory_file_watcher.js"
    );

    watcher = createMemoryFileWatcher({
      pluginConfig: {
        brainclawSecret: "test-secret",
        pythonBackendPath: "/tmp/python",
      },
      config: {
        agents: {
          list: [{ id: "test-agent", workspace: tempAgent.dir }],
        },
      },
      pollIntervalMs: 100,
    });

    await sleep(150);

    // Touch the file (update mtime) without changing content
    const fd = fs.openSync(tempAgent.filePath, "a");
    fs.closeSync(fd);
    // Also explicitly re-write same content
    fs.writeFileSync(tempAgent.filePath, "# Static content\n", "utf8");

    await sleep(500);

    assert.strictEqual(bridgeCalls.length, 0, "Should NOT call sync when content is unchanged");
  });

  test("stop() cleans up all watchers without errors", async () => {
    tempAgent = makeTempAgent();

    const { createMemoryFileWatcher } = await import(
      "../dist/services/memory_file_watcher.js"
    );

    watcher = createMemoryFileWatcher({
      pluginConfig: {
        brainclawSecret: "test-secret",
        pythonBackendPath: "/tmp/python",
      },
      config: {
        agents: {
          list: [{ id: "test-agent", workspace: tempAgent.dir }],
        },
      },
      pollIntervalMs: 100,
    });

    watcher.stop();
    watcher.stop(); // Double-stop should be safe
    watcher = null; // Prevent afterEach from double-stopping again
  });

  test("gracefully handles nonexistent MEMORY.md path", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "brainclaw-watcher-empty-"));

    const { createMemoryFileWatcher } = await import(
      "../dist/services/memory_file_watcher.js"
    );

    // No MEMORY.md exists — watchFile will poll for creation
    watcher = createMemoryFileWatcher({
      pluginConfig: {
        brainclawSecret: "test-secret",
        pythonBackendPath: "/tmp/python",
      },
      config: {
        agents: {
          list: [{ id: "ghost-agent", workspace: dir }],
        },
      },
      pollIntervalMs: 100,
    });

    watcher.stop();
    watcher = null;
    fs.rmSync(dir, { recursive: true, force: true });
  });
});
