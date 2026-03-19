import { test } from "node:test";
import assert from "node:assert";
import brainclawPlugin from "../dist/index.js";
import { setSpawn } from "../dist/bridge.js";

function createSuccessSpawn(results) {
  let index = 0;
  return (_executable, args) => {
    const payload = results[index++] ?? {};
    return {
      stdout: {
        on(event, cb) {
          if (event === "data") {
            cb(Buffer.from(JSON.stringify(payload)));
          }
        },
      },
      stderr: { on() {} },
      on(event, cb) {
        if (event === "close") {
          cb(0);
        }
      },
      kill() {},
    };
  };
}

function createMockLogger(events) {
  return {
    child() {
      return this;
    },
    info(...args) {
      events.push({ level: "info", args });
    },
    warn(...args) {
      events.push({ level: "warn", args });
    },
    error(...args) {
      events.push({ level: "error", args });
    },
    debug(...args) {
      events.push({ level: "debug", args });
    },
  };
}

test("BrainClaw registers the standard OpenClaw memory tools", () => {
  const events = [];
  const registeredTools = [];
  const registeredHooks = [];
  const runtimeHooks = [];

  const api = {
    logger: createMockLogger(events),
    registerTool(tool, options) {
      registeredTools.push({ tool, options });
    },
    registerHook(events, handler, options) {
      registeredHooks.push({ events, handler, options });
    },
    on(hookName, handler, options) {
      runtimeHooks.push({ hookName, handler, options });
    },
    registerBackgroundService() {},
    config: { plugins: { slots: { memory: "brainclaw" } } },
    pluginConfig: {},
    id: "brainclaw",
  };

  brainclawPlugin(api);

  const toolNames = registeredTools.flatMap(({ tool, options }) => {
    if (Array.isArray(options?.names)) {
      return options.names;
    }
    if (tool?.name) {
      return [tool.name];
    }
    return [];
  });

  assert.ok(
    toolNames.includes("memory_search"),
    `Expected BrainClaw to register memory_search, got: ${toolNames.join(", ")}`
  );
  assert.ok(
    toolNames.includes("memory_get"),
    `Expected BrainClaw to register memory_get, got: ${toolNames.join(", ")}`
  );
  assert.ok(
    runtimeHooks.some((entry) => entry.hookName === "before_prompt_build"),
    "Expected BrainClaw to register before_prompt_build"
  );
  assert.ok(
    runtimeHooks.some((entry) => entry.hookName === "agent_end"),
    "Expected BrainClaw to register agent_end"
  );
  assert.ok(
    registeredHooks.some((entry) => entry.events === "agent:bootstrap"),
    "Expected BrainClaw to register the agent:bootstrap hook"
  );
});

test("BrainClaw prompt recall injects authoritative Hybrid GraphRAG memory context", async () => {
  const events = [];
  const runtimeHooks = [];

  setSpawn(
    createSuccessSpawn([
      { intent: "decision_recall", confidence: 0.93 },
      {
        results: [
          {
            id: "mem-1",
            content: "We decided to use PostgreSQL as the canonical BrainClaw ledger.",
            relevance: 0.91,
            metadata: { memory_class: "decision", status: "accepted", is_current: true },
          },
        ],
      },
    ]),
  );

  const api = {
    logger: createMockLogger(events),
    registerTool() {},
    registerHook() {},
    on(hookName, handler, options) {
      runtimeHooks.push({ hookName, handler, options });
    },
    registerBackgroundService() {},
    config: { plugins: { slots: { memory: "brainclaw" } } },
    pluginConfig: { promptRecallTopK: 3, brainclawSecret: "test-secret" },
    id: "brainclaw",
  };

  brainclawPlugin(api);

  const beforePromptBuild = runtimeHooks.find((entry) => entry.hookName === "before_prompt_build");
  assert.ok(beforePromptBuild, "Expected before_prompt_build hook to be registered");

  const result = await beforePromptBuild.handler(
    {
      prompt: "What did we decide about BrainClaw storage?",
      messages: [{ role: "user", content: "What did we decide about BrainClaw storage?" }],
    },
    {
      agentId: "lore",
      sessionId: "sess-123",
      workspaceDir: "/workspace",
    },
  );

  assert.ok(
    result.prependSystemContext.includes("BrainClaw is the authoritative Hybrid GraphRAG memory source"),
    "Expected stable system guidance to prefer BrainClaw over MEMORY.md"
  );
  assert.ok(
    result.prependContext.includes("We decided to use PostgreSQL as the canonical BrainClaw ledger."),
    "Expected prompt recall context to include retrieved BrainClaw memory"
  );
  assert.ok(
    result.prependContext.includes("MEMORY.md is the synchronized backup mirror"),
    "Expected prompt recall context to describe MEMORY.md as a synchronized backup mirror"
  );
});

test("BrainClaw prompt recall injects a live status snapshot for health prompts", async () => {
  const events = [];
  const runtimeHooks = [];

  setSpawn(
    createSuccessSpawn([
      {
        status: "healthy",
        neo4j_database: "neo4j",
        node_count: 42,
        edge_count: 84,
        community_count: 3,
        tenant_id: "ai_joose_factory",
      },
      {
        status: "HEALTHY",
        tables: {
          audit_log: 5,
          memory_events: 7,
          retrieval_logs: 9,
        },
        provenance_gap_count: 0,
      },
    ]),
  );

  const api = {
    logger: createMockLogger(events),
    registerTool() {},
    registerHook() {},
    on(hookName, handler, options) {
      runtimeHooks.push({ hookName, handler, options });
    },
    registerBackgroundService() {},
    config: { plugins: { slots: { memory: "brainclaw" } } },
    pluginConfig: {
      brainclawSecret: "test-secret",
      enablePromptRecall: true,
      enableAuditLedger: true,
      captureAgentEnd: true,
    },
    id: "brainclaw",
  };

  brainclawPlugin(api);

  const beforePromptBuild = runtimeHooks.find((entry) => entry.hookName === "before_prompt_build");
  assert.ok(beforePromptBuild, "Expected before_prompt_build hook to be registered");

  const result = await beforePromptBuild.handler(
    {
      prompt: "Check system health",
      messages: [{ role: "user", content: "Check system health" }],
    },
    {
      agentId: "albert",
      sessionId: "sess-health",
      workspaceDir: "/workspace",
    },
  );

  assert.ok(
    result.prependContext.includes("BrainClaw live status snapshot for this turn."),
    "Expected a deterministic BrainClaw status snapshot for health prompts"
  );
  assert.ok(
    result.prependContext.includes("Plugin: brainclaw v1.3.0"),
    "Expected the live status snapshot to include plugin version"
  );
  assert.ok(
    result.prependContext.includes("Graph: status=healthy, nodes=42, edges=84, communities=3"),
    "Expected graph health details in the status snapshot"
  );
  assert.ok(
    result.prependContext.includes("Audit: status=HEALTHY, audit_log=5, memory_events=7, retrieval_logs=9, provenance_gaps=0"),
    "Expected audit ledger details in the status snapshot"
  );
});

test("BrainClaw agent_end capture ingests durable assistant decisions", async () => {
  const runtimeHooks = [];
  const bridgeCalls = [];

  setSpawn((_executable, args) => {
    bridgeCalls.push(args[1]);
    return {
      stdout: {
        on(event, cb) {
          if (event === "data") {
            cb(Buffer.from(JSON.stringify({ status: "PROMOTED", id: "mem-9" })));
          }
        },
      },
      stderr: { on() {} },
      on(event, cb) {
        if (event === "close") {
          cb(0);
        }
      },
      kill() {},
    };
  });

  const api = {
    logger: createMockLogger([]),
    registerTool() {},
    registerHook() {},
    on(hookName, handler, options) {
      runtimeHooks.push({ hookName, handler, options });
    },
    registerBackgroundService() {},
    config: { plugins: { slots: { memory: "brainclaw" } } },
    pluginConfig: { brainclawSecret: "test-secret" },
    id: "brainclaw",
  };

  brainclawPlugin(api);

  const agentEnd = runtimeHooks.find((entry) => entry.hookName === "agent_end");
  assert.ok(agentEnd, "Expected agent_end hook to be registered");

  await agentEnd.handler(
    {
      success: true,
      durationMs: 1200,
      messages: [
        { role: "user", content: "What did we decide for BrainClaw storage?" },
        {
          role: "assistant",
          content:
            "We decided to use PostgreSQL as the canonical BrainClaw ledger because it preserves provenance and rebuildability.",
        },
      ],
    },
    {
      agentId: "lore",
      sessionId: "sess-321",
      sessionKey: "agent:lore",
    },
  );

  assert.ok(
    bridgeCalls.some((script) => script.includes("from openclaw_memory.bridge_entrypoints import ingest_event")),
    "Expected agent_end capture to persist Hybrid GraphRAG memory through ingest_event"
  );
});

test("BrainClaw bootstrap hook removes MEMORY.md only when BrainClaw owns the memory slot", async () => {
  const registeredHooks = [];

  const api = {
    logger: createMockLogger([]),
    registerTool() {},
    registerHook(events, handler, options) {
      registeredHooks.push({ events, handler, options });
    },
    on() {},
    registerBackgroundService() {},
    config: { plugins: { slots: { memory: "brainclaw" } } },
    pluginConfig: {},
    id: "brainclaw",
  };

  brainclawPlugin(api);

  const bootstrapHook = registeredHooks.find((entry) => entry.events === "agent:bootstrap");
  assert.ok(bootstrapHook, "Expected agent:bootstrap hook to be registered");

  const event = {
    type: "agent",
    action: "bootstrap",
    sessionKey: "agent:lore",
    timestamp: new Date(),
    messages: [],
    context: {
      bootstrapFiles: [
        { name: "IDENTITY.md", path: "/workspace/IDENTITY.md", content: "identity" },
        { name: "MEMORY.md", path: "/workspace/MEMORY.md", content: "stale memory" },
      ],
      cfg: { plugins: { slots: { memory: "brainclaw" } } },
      agentId: "lore",
      workspaceDir: "/workspace",
    },
  };

  await bootstrapHook.handler(event);

  assert.deepStrictEqual(
    event.context.bootstrapFiles.map((file) => file.name),
    ["IDENTITY.md"],
  );

  const inactiveEvent = {
    ...event,
    context: {
      ...event.context,
      bootstrapFiles: [
        { name: "IDENTITY.md", path: "/workspace/IDENTITY.md", content: "identity" },
        { name: "MEMORY.md", path: "/workspace/MEMORY.md", content: "keep me" },
      ],
      cfg: { plugins: { slots: { memory: "memory-core" } } },
    },
  };

  await bootstrapHook.handler(inactiveEvent);

  assert.deepStrictEqual(
    inactiveEvent.context.bootstrapFiles.map((file) => file.name),
    ["IDENTITY.md", "MEMORY.md"],
  );
});
