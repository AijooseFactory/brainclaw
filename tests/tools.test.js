import { test } from "node:test";
import assert from "node:assert";
import { searchTool } from "../dist/tools/search.js";
import { ingestTool } from "../dist/tools/ingest.js";
import { graphHealthTool } from "../dist/tools/graph_health.js";
import { contradictionCheckTool } from "../dist/tools/contradiction_check.js";
import { memorySearchTool } from "../dist/tools/memory_search.js";
import { memoryGetTool } from "../dist/tools/memory_get.js";
import { setSpawn } from "../dist/bridge.js";

// Mocking ctx for execution
const mockCtx = {
  config: {
    postgresUrl: "localhost",
    pythonTimeoutMs: 10000,
    brainclawSecret: "test-secret"
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

function mockBridgeResponses(results) {
  let index = 0;
  setSpawn(() => {
    const result = results[Math.min(index, results.length - 1)];
    index += 1;
    return {
      stdout: { on: (event, cb) => {
        if (event === "data") cb(Buffer.from(JSON.stringify(result)));
      }},
      stderr: { on: () => {} },
      on: (event, cb) => {
        if (event === "close") cb(0);
      },
      kill: () => {}
    };
  });
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
  mockBridgeResponse({ status: "HEALTHY" });
  const result = await graphHealthTool.execute("test_id", { tenant_id: "test" }, mockCtx);
  assert.ok(result.content[0].text.includes("HEALTHY"), "Should return healthy status");
});

test("Contradiction Check Tool: surfaces real contradiction evidence from the backend", async () => {
  mockBridgeResponse({
    status: "CONTRADICTIONS_FOUND",
    checked_entities: ["PostgreSQL"],
    checked_count: 2,
    evidence_count: 2,
    contradictions: [
      {
        memory_ids: ["mem-1", "mem-2"],
        reason: "Contradicts existing fact: 'PostgreSQL is running...'",
      },
    ],
  });

  try {
    const result = await contradictionCheckTool.execute("test_id", { entity_name: "PostgreSQL" }, mockCtx);
    const parsed = JSON.parse(result.content[0].text);

    assert.equal(parsed.status, "CONTRADICTIONS_FOUND");
    assert.equal(parsed.evidence_count, 2);
    assert.equal(parsed.contradictions.length, 1);
    assert.deepEqual(parsed.contradictions[0].memory_ids, ["mem-1", "mem-2"]);
  } finally {
    // cleanup
  }
});

test("Memory Search Tool: returns portable citations from BrainClaw retrieval results", async () => {
  mockBridgeResponses([
    { intent: "fact_lookup", confidence: 0.93 },
    {
      results: [
        {
          id: "mem-123",
          content: "Authentication decision with rationale",
          score: 0.91,
          metadata: { memory_class: "decision", source_session_id: "sess-1" }
        }
      ],
      total: 1
    }
  ]);

  const result = await memorySearchTool.execute("test_id", { query: "auth decision" }, mockCtx);
  const parsed = JSON.parse(result.content[0].text);

  assert.equal(parsed.results.length, 1, "Should surface retrieved memories");
  assert.equal(parsed.results[0].path, "brainclaw://memory/mem-123");
  assert.equal(parsed.results[0].snippet, "Authentication decision with rationale");
});

test("Memory Get Tool: resolves a BrainClaw citation through the backend", async () => {
  mockBridgeResponse({
    id: "mem-123",
    content: "Authentication decision with rationale",
    metadata: { memory_class: "decision" },
    provenance: { source_session_id: "sess-1" }
  });

  const result = await memoryGetTool.execute(
    "test_id",
    { path: "brainclaw://memory/mem-123" },
    mockCtx
  );
  const parsed = JSON.parse(result.content[0].text);

  assert.equal(parsed.path, "brainclaw://memory/mem-123");
  assert.equal(parsed.text, "Authentication decision with rationale");
  assert.equal(parsed.metadata.memory_class, "decision");
  assert.equal(parsed.provenance.source_session_id, "sess-1");
});
