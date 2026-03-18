import { test } from "node:test";
import assert from "node:assert";
import { callPythonBackend, setSpawn } from "../dist/bridge.js";

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

  const config = { pythonTimeoutMs: 10 };
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

  const config = { pythonTimeoutMs: 5000 };
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
    await callPythonBackend("retrieval", "classify", { query: "error test" });
    assert.fail("Should have thrown a Python error");
  } catch (e) {
    assert.ok(!e.message.includes("/Users/"), "Error should not leak local paths");
    assert.ok(!e.message.includes("Traceback"), "Error should be sanitized");
  } finally {
    // cleanup
  }
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
