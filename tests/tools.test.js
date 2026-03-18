import { test } from "node:test";
import assert from "node:assert";
import { searchTool } from "../dist/tools/search.js";
import { ingestTool } from "../dist/tools/ingest.js";
import { graphHealthTool } from "../dist/tools/graph_health.js";
import { contradictionCheckTool } from "../dist/tools/contradiction_check.js";
import { setSpawn } from "../dist/bridge.js";

// Mocking ctx for execution
const mockCtx = {
  config: {
    postgresUrl: "localhost",
    pythonTimeoutMs: 10000
  }
};

/**
 * Helper to set up a mock Python response via setSpawn
 */
function mockBridgeResponse(result) {
  setSpawn(() => ({
    stdout: { on: (event, cb) => {
      if (event === "data") cb(Buffer.from(JSON.stringify(result)));
    }},
    stderr: { on: () => {} },
    on: (event, cb) => {
      if (event === "close") cb(0);
    },
    kill: () => {}
  }));
}

test("Search Tool: Parameter passing and execution (MOCKED)", async () => {
  const mockResult = [{ content: "GraphRAG is powerful", score: 0.9 }];
  mockBridgeResponse(mockResult);

  try {
    const result = await searchTool.execute("test_id", { query: "search test" }, mockCtx);
    // Search tool returns a JSON string in content[0].text
    const parsed = JSON.parse(result.content[0].text);
    assert.ok(Array.isArray(parsed), "Should return an array of results");
  } finally {
    // cleanup in a real scenario would reset spawn to default
  }
});

test("Ingest Tool: Parameter passing and execution (MOCKED)", async () => {
  const mockResult = { id: "evt_123", status: "SAVED" };
  mockBridgeResponse(mockResult);

  try {
    const params = {
      content: "New knowledge entry.",
      memory_class: "test",
      tenant_id: "test"
    };
    const result = await ingestTool.execute("test_id", params, mockCtx);
    assert.ok(result.content[0].text.includes("SAVED"), "Should mention status in output");
  } finally {
    // cleanup
  }
});

test("Graph Health Tool: Execution", async () => {
  const result = await graphHealthTool.execute("test_id", { tenant_id: "test" }, mockCtx);
  assert.ok(result.content[0].text.includes("HEALTHY"), "Should return healthy status");
});

test("Contradiction Check Tool: Execution (MOCKED)", async () => {
  mockBridgeResponse([{ content: "No contradictions" }]);

  try {
    const result = await contradictionCheckTool.execute("test_id", { entity_name: "test" }, mockCtx);
    assert.ok(result.content[0].text.includes("NO_CONTRADICTIONS_FOUND"), "Should return check status");
  } finally {
    // cleanup
  }
});
