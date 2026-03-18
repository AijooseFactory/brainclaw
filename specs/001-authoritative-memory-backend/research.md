# Research: Authoritative OpenClaw Memory Backend

## Inputs

- The BrainClaw/OpenClaw runtime findings captured on 2026-03-18
- The consolidated Hybrid GraphRAG requirements document provided by the user on
  2026-03-18
- The local BrainClaw working tree, current runtime logs, and the stock
  OpenClaw `memory-core` plugin contract

## Target Capability Summary

BrainClaw is expected to become the real OpenClaw memory system, not just an
additional plugin with custom tools. The target system must provide:

- PostgreSQL as the canonical source of truth for raw events, promoted memory,
  decision records, provenance, lifecycle state, visibility, and retrieval logs
- Weaviate and Neo4j as rebuildable derived indexes for semantic and
  relationship-aware retrieval
- Durable decision, procedural, semantic, relational, episodic, and
  identity/governance memory classes
- Selective promotion that keeps raw history lossless while controlling durable
  memory quality
- Provenance, confidence, supersession, and temporal lifecycle support
- Intent-routed retrieval that can answer fact, decision, relationship,
  procedural, preference, and change-over-time questions
- Honest capability reporting and portability across different OpenClaw
  instances

## Confirmed Current Baseline

- OpenClaw in `ajf-openclaw` is up and configured to use `brainclaw` in the
  memory slot.
- BrainClaw is currently loaded from a linked local source path, not from the
  standard OpenClaw plugin directory.
- `MEMORY.md` is still injected into bootstrap context in live logs, so file
  memory remains part of the active path.
- BrainClaw currently exposes custom tools such as
  `hybrid_graphrag_search` and `hybrid_graphrag_ingest`, but not the standard
  `memory_search` and `memory_get` contract used by the stock memory plugin.

## Highest-Risk Gaps

### 1. Authoritative Memory Contract Gap

BrainClaw does not yet satisfy the standard OpenClaw memory-plugin contract.
This blocks BrainClaw from being a drop-in authoritative memory backend.

### 2. Canonical Ledger Gap

The requirements call for PostgreSQL to be the authoritative memory ledger, but
current code and runtime evidence do not yet prove:

- durable promoted-memory modeling
- complete provenance coverage
- durable decision-memory behavior
- supersession chains
- full rebuildability of Weaviate/Neo4j from PostgreSQL history

### 3. Capability Truth Gap

Some advanced features are still placeholder or log-only behavior. Current code
contains placeholder contradiction and audit flows, so runtime capability claims
must be downgraded until those capabilities are either implemented or clearly
marked incomplete.

### 4. Portability Gap

Current code still contains instance-specific assumptions, including local path
fallbacks and `ajf`-specific defaults in some runtime paths. The target system
must adapt to any supported OpenClaw deployment via configuration and runtime
discovery.

### 5. Installation Gap

BrainClaw is not yet installed as a standard plugin under OpenClaw’s plugin
directory. The runtime currently depends on linked local-path loading.

## Implementation Implications

- The first release gate is contract parity with `memory_search` and
  `memory_get`.
- PostgreSQL-backed durable memory models must be treated as core scope, not
  optional later enhancements.
- Decision memory, supersession, provenance, and promotion policy must be
  represented in the canonical data model and covered by tests.
- Derived vector and graph indexes must be rebuildable from canonical history.
- Runtime status must distinguish clearly between implemented and incomplete
  capabilities.
- Packaging and install work must preserve current OpenClaw data, ControlUI
  settings, and unrelated containers.
