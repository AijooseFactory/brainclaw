# BrainClaw Plugin - Hybrid GraphRAG for OpenClaw

BrainClaw is the durable memory plugin for OpenClaw. It combines canonical memory storage, hybrid retrieval, graph reasoning, contradiction checks, provenance tracking, and operational memory sync so OpenClaw agents can recall and reuse knowledge across sessions without relying on `MEMORY.md` as the primary memory system.

## Overview

BrainClaw is designed around one authority model:

- PostgreSQL is the canonical durable memory ledger
- Weaviate is a derived semantic retrieval index
- Neo4j is a derived graph reasoning index

Everything else feeds or derives from that canonical layer.

## Core Capabilities

- Durable memory search and lookup
- Canonical ingest and promotion workflow
- Hybrid GraphRAG retrieval across lexical, semantic, and graph signals
- Prompt-time recall so BrainClaw becomes the active memory source
- Agent-end capture of decisions and procedures
- Graph health inspection and contradiction review
- Background entity extraction, summarization, audit logging, and contradiction detection
- Operational memory sync for root and agent `MEMORY.md` state blocks
- CLI surfaces for memory sync, rebuilds, and Lossless-Claw integration operations

## Architecture

BrainClaw is split into two layers:

- TypeScript OpenClaw plugin layer for tools, hooks, services, runtime gating, and CLI registration
- Python backend for storage, retrieval, graph operations, ingestion, promotion policy, and integration workflows

The main entrypoints are:

- [`src/index.ts`](./src/index.ts)
- [`src/bridge.ts`](./src/bridge.ts)
- [`python/openclaw_memory/bridge_entrypoints.py`](./python/openclaw_memory/bridge_entrypoints.py)
- [`openclaw.plugin.json`](./openclaw.plugin.json)

## Major Feature: Lossless-Claw Integration

Lossless-Claw integration is one major BrainClaw feature, not the project identity.

When Lossless-Claw is installed alongside BrainClaw, BrainClaw can:

- detect the active Lossless-Claw install
- verify OpenClaw runtime compatibility and slot configuration
- fingerprint the Lossless-Claw SQLite schema
- import LCM artifacts as `source_artifacts`
- extract `memory_candidates` from those artifacts
- apply contradiction checks and promotion policy before durable writes
- use Lossless-Claw as supplemental drill-down evidence when needed

Critical rule:

- Lossless-Claw is upstream context only
- BrainClaw remains the canonical durable memory authority

Primary implementation files for this feature:

- [`src/lcm_runtime.ts`](./src/lcm_runtime.ts)
- [`python/openclaw_memory/integration/lossless_adapter.py`](./python/openclaw_memory/integration/lossless_adapter.py)
- [`python/openclaw_memory/integration/lossless_sync.py`](./python/openclaw_memory/integration/lossless_sync.py)
- [`specs/001-authoritative-memory-backend/data-model.md`](./specs/001-authoritative-memory-backend/data-model.md)

## Recent Integration Work

The Lossless-Claw integration alignment landed on `main` in:

- [`50f8a3f`](https://github.com/AijooseFactory/brainclaw/commit/50f8a3f10110e7a91fddcf26ecb0ff34c30d829e) `feat: align lcm integration contract, runtime gating, and status surfaces`

The follow-up README correction is:

- [`46fd071`](https://github.com/AijooseFactory/brainclaw/commit/46fd0713f246766af298e5baf635bd6a289a622a) `docs: clarify lossless-claw integration in README`

## Runtime Compatibility

Current enforced runtime floor for the Lossless-Claw integration in this repo state:

- OpenClaw `2026.3.14+`
- Lossless-Claw `0.4.0`

BrainClaw only enables the integration when all runtime gate checks pass:

1. OpenClaw version is supported
2. `plugins.slots.memory=brainclaw`
3. `plugins.slots.contextEngine=lossless-claw`
4. Lossless-Claw is present in `plugins.installs`
5. Lossless-Claw is registered and enabled in the active runtime
6. Required Lossless-Claw tools are available, or a supported fallback path exists

Supported compatibility states:

- `not_installed`
- `installed_compatible`
- `installed_degraded`
- `installed_incompatible`
- `installed_unreachable`

## Operational Commands

```bash
brainclaw memory sync
brainclaw lcm status
brainclaw lcm sync --mode bootstrap
brainclaw lcm sync --mode incremental
brainclaw lcm sync --mode repair
brainclaw rebuild --target weaviate
brainclaw rebuild --target neo4j
```

## Quick Verification

On a running OpenClaw install:

```bash
brainclaw memory sync
brainclaw lcm status
brainclaw lcm sync --mode incremental
brainclaw rebuild --target neo4j
```

Healthy BrainClaw + Lossless-Claw integration should show:

- `compatibility_state: installed_compatible`
- a supported Lossless-Claw schema fingerprint
- runtime drill-down tool availability
- checkpoint state for imported artifacts
- rebuild status for derived stores

## Configuration

BrainClaw configuration lives in [`openclaw.plugin.json`](./openclaw.plugin.json).

Important config areas include:

- storage and backend connectivity
- prompt recall and bootstrap suppression
- operational memory sync
- Lossless-Claw detection, sync, quota, drill-down, and trust posture

Lossless-Claw-specific config keys include:

- `losslessClawEnabled`
- `losslessClawPluginPath`
- `losslessClawDbPath`
- `losslessClawBootstrapOnStart`
- `losslessClawPollIntervalMs`
- `losslessClawDrillDownEnabled`
- `losslessClawArtifactQuotaBytes`
- `losslessClawAnchorByteCap`
- `losslessClawLargeFileMode`
- `losslessClawTrustMode`

## Rollout Safety

For OpenClaw deployments, preserve runtime state during rollout:

- do not recreate production with an empty `./data` mount
- do not run destructive volume commands such as `docker compose down -v`
- do not hand-edit `data/openclaw.json` or `plugins.installs`
- take a pre-change snapshot before restarts or rebuilds that affect runtime state
- validate staging on the same version, config, and state shape before production promotion

Restart and rebuild flows must preserve:

- plugin slot selections
- plugin install records
- Control UI state
- auth state
- agents
- sessions
- workspaces
- canonical BrainClaw state

## Development

```bash
npm install
npm run build
npm test

pip install -r requirements.txt
PYTHONPATH=python pytest -q
```
