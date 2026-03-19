import { test } from "node:test";
import assert from "node:assert";
import { warnIfPlaintextSecret } from "../dist/validation.js";
import { initLogger } from "../dist/logging.js";

function captureLogs() {
  const entries = [];

  initLogger({
    debug() {},
    info() {},
    warn(message) {
      entries.push(JSON.parse(message));
    },
    error(message) {
      entries.push(JSON.parse(message));
    },
  });

  return entries;
}

test("Validation: env-backed resolved postgresUrl does not emit plaintext-secret warning", () => {
  const previous = process.env.POSTGRES_URL;
  process.env.POSTGRES_URL = "postgresql://brainclaw:brainclaw_secret@postgres:5432/brainclaw";

  const entries = captureLogs();

  try {
    warnIfPlaintextSecret("postgresUrl", process.env.POSTGRES_URL);
  } finally {
    if (previous === undefined) {
      delete process.env.POSTGRES_URL;
    } else {
      process.env.POSTGRES_URL = previous;
    }
  }

  assert.deepStrictEqual(
    entries.filter((entry) => entry.operation === "plaintextSecret"),
    [],
  );
});

test("Validation: literal neo4jPassword still emits plaintext-secret warning", () => {
  const previous = process.env.NEO4J_PASSWORD;
  process.env.NEO4J_PASSWORD = "different-secret";

  const entries = captureLogs();

  try {
    warnIfPlaintextSecret("neo4jPassword", "literal-secret");
  } finally {
    if (previous === undefined) {
      delete process.env.NEO4J_PASSWORD;
    } else {
      process.env.NEO4J_PASSWORD = previous;
    }
  }

  assert.strictEqual(
    entries.filter((entry) => entry.operation === "plaintextSecret").length,
    1,
  );
});
