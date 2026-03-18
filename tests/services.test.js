import { test, mock } from "node:test";
import assert from "node:assert";
import { summarizerService } from "../dist/services/summarizer.js";
import { auditLoggerService } from "../dist/services/audit_logger.js";

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
