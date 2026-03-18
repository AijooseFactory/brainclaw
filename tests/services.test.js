import { test, mock } from "node:test";
import assert from "node:assert";
import { summarizerService } from "../dist/services/summarizer.js";
import { auditLoggerService } from "../dist/services/audit_logger.js";
import { contradictionDetectorService } from "../dist/services/contradiction_detector.js";
import { setSpawn } from "../dist/bridge.js";

test("Summarizer Service: Lifecycle operations", () => {
  const setIntervalMock = mock.method(global, "setInterval", () => "mock_interval");
  const clearIntervalMock = mock.method(global, "clearInterval", () => {});
  
  try {
    const handle = summarizerService.start({});
    assert.strictEqual(typeof handle.stop, "function", "Service should return a handle with a stop function");
    assert.strictEqual(setIntervalMock.mock.callCount(), 1, "Should register an interval");
    
    handle.stop();
    assert.strictEqual(clearIntervalMock.mock.callCount(), 1, "Should clear the interval when stopped");
  } finally {
    setIntervalMock.mock.restore();
    clearIntervalMock.mock.restore();
  }
});

test("Audit Logger Service: Lifecycle operations", () => {
  const setIntervalMock = mock.method(global, "setInterval", () => "mock_interval");
  const clearIntervalMock = mock.method(global, "clearInterval", () => {});
  
  try {
    const handle = auditLoggerService.start({});
    assert.strictEqual(typeof handle.stop, "function", "Service should return a handle with a stop function");
    assert.strictEqual(setIntervalMock.mock.callCount(), 1, "Should register an interval");
    
    handle.stop();
    assert.strictEqual(clearIntervalMock.mock.callCount(), 1, "Should clear the interval when stopped");
  } finally {
    setIntervalMock.mock.restore();
    clearIntervalMock.mock.restore();
  }
});

test("Contradiction Detector Service: interval invokes backend contradiction analysis", async () => {
  let scheduledCallback;
  let capturedBridgeScript = "";

  const setIntervalMock = mock.method(global, "setInterval", (callback) => {
    scheduledCallback = callback;
    return "mock_interval";
  });
  const clearIntervalMock = mock.method(global, "clearInterval", () => {});

  setSpawn((_executable, args) => {
    capturedBridgeScript = args[1];
    return {
      stdout: { on: (event, cb) => {
        if (event === "data") {
          cb(Buffer.from(JSON.stringify({
            status: "NO_CONTRADICTIONS_FOUND",
            contradictions: [],
            checked_count: 0,
          })));
        }
      }},
      stderr: { on: () => {} },
      on: (event, cb) => {
        if (event === "close") cb(0);
      },
      kill: () => {},
    };
  });

  try {
    const handle = contradictionDetectorService.start({
      config: { brainclawSecret: "test-secret", pythonBackendPath: "/tmp/python" },
    });
    assert.strictEqual(typeof handle.stop, "function");
    assert.strictEqual(typeof scheduledCallback, "function");

    await scheduledCallback();

    assert.match(capturedBridgeScript, /from openclaw_memory\.bridge_entrypoints import check_contradictions/);

    handle.stop();
    assert.strictEqual(clearIntervalMock.mock.callCount(), 1);
  } finally {
    setIntervalMock.mock.restore();
    clearIntervalMock.mock.restore();
  }
});

test("Audit Logger Service: interval invokes backend audit verification", async () => {
  let scheduledCallback;
  let capturedBridgeScript = "";

  const setIntervalMock = mock.method(global, "setInterval", (callback) => {
    scheduledCallback = callback;
    return "mock_interval";
  });
  const clearIntervalMock = mock.method(global, "clearInterval", () => {});

  setSpawn((_executable, args) => {
    capturedBridgeScript = args[1];
    return {
      stdout: { on: (event, cb) => {
        if (event === "data") {
          cb(Buffer.from(JSON.stringify({
            status: "HEALTHY",
            tables: { audit_log: 1, memory_events: 2, retrieval_logs: 3 },
            provenance_gap_count: 0,
          })));
        }
      }},
      stderr: { on: () => {} },
      on: (event, cb) => {
        if (event === "close") cb(0);
      },
      kill: () => {},
    };
  });

  try {
    const handle = auditLoggerService.start({
      config: { brainclawSecret: "test-secret", pythonBackendPath: "/tmp/python" },
    });
    assert.strictEqual(typeof handle.stop, "function");
    assert.strictEqual(typeof scheduledCallback, "function");

    await scheduledCallback();

    assert.match(capturedBridgeScript, /from openclaw_memory\.bridge_entrypoints import verify_audit_integrity/);

    handle.stop();
    assert.strictEqual(clearIntervalMock.mock.callCount(), 1);
  } finally {
    setIntervalMock.mock.restore();
    clearIntervalMock.mock.restore();
  }
});
