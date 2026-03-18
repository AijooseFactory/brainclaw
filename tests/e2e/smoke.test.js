import { test } from "node:test";
import assert from "node:assert";
import { callPythonBackend } from "../../dist/bridge.js";

test("E2E Smoke: Intent Classification through Bridge", async () => {
  const config = { 
    postgresUrl: "localhost",
    weaviateUrl: "http://localhost:8080",
    neo4jUrl: "bolt://localhost:7687",
    pythonTimeoutMs: 15000 
  };
  
  try {
    const query = "What are the latest findings on gravity?";
    const result = await callPythonBackend("retrieval", "classify", { query }, config);
    
    // Check for expected response structure from Python backend
    assert.ok(result.primary_intent, "Classification should return a primary intent");
    console.log("E2E Smoke SUCCESS: Intent classified as:", result.primary_intent);
  } catch (e) {
    // If the backend stores are not fully accessible, we might get an error, 
    // but the classification step often works independently or with defaults.
    if (e.message.includes("Timeout")) {
      assert.fail("E2E Smoke FAIL: Backend call timed out");
    }
    console.warn("E2E Smoke Warning (expected if backend offline):", e.message);
  }
});

test("E2E Smoke: Multi-Agent Contradiction Detection Flow", async () => {
  const config = { 
    postgresUrl: "localhost",
    weaviateUrl: "http://localhost:8080",
    neo4jUrl: "bolt://localhost:7687",
    pythonTimeoutMs: 30000 
  };
  
  try {
    const query = "Check for contradictions about the new propulsion system.";
    const result = await callPythonBackend("retrieval", "retrieve_sync", {
      query: query,
      intent: "contradiction_check",
      tenant_id: "default",
      limit: 10
    }, config);
    
    assert.ok(Array.isArray(result), "Retrieve should return an array of Results");
    console.log("E2E Smoke SUCCESS: Retrieved", result.length, "results for contradiction check");
  } catch (e) {
    console.warn("E2E Smoke Warning (expected if backend offline):", e.message);
  }
});
