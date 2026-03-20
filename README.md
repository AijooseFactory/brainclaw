# BrainClaw

BrainClaw is a Hybrid GraphRAG memory plugin for OpenClaw. It combines canonical memory storage, hybrid retrieval, graph reasoning, contradiction checks, provenance tracking, and operational memory sync so OpenClaw agents can recall and reuse knowledge across sessions without relying on `MEMORY.md` files as the primary memory system.

## Overview

BrainClaw is designed around one authority model (see [BENCHMARK.md](./BENCHMARK.md) for verified performance metrics):

- PostgreSQL is the canonical durable memory ledger for BrainClaw's Hybrid GraphRAG memory system
- Weaviate is a derived semantic retrieval index
- Neo4j is a derived graph reasoning index

Everything else feeds or derives from that canonical layer.

## Core Capabilities

- Durable memory search and lookup
- Canonical ingest and promotion workflow
- Hybrid GraphRAG retrieval with research-backed Mode-Aware Hub (Local, Global, DRIFT, Lazy)
- Prompt-time recall so BrainClaw becomes the active memory source
- Agent-end capture of decisions and procedures
- Universal Leiden Community Detection (GDS with Python-native fallback)
- Graph health inspection and contradiction review
- Background entity extraction, summarization, audit logging, and contradiction detection
- Operational memory sync for root and agent `MEMORY.md` state blocks
- Automatic Lossless-Claw detection, compatibility gating, and artifact integration
- CLI surfaces for memory sync, rebuilds, and Lossless-Claw installation/ops

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
- BrainClaw remains the canonical Hybrid GraphRAG memory authority

Primary implementation files for this feature:

- [`src/lcm_runtime.ts`](./src/lcm_runtime.ts)
- [`python/openclaw_memory/integration/lossless_adapter.py`](./python/openclaw_memory/integration/lossless_adapter.py)
- [`python/openclaw_memory/integration/lossless_sync.py`](./python/openclaw_memory/integration/lossless_sync.py)
- [`specs/001-authoritative-memory-backend/data-model.md`](./specs/001-authoritative-memory-backend/data-model.md)

## Recent Releases
 
- **v1.5.0-intel-perfection (Current)**: `236aba8` `feat: BrainClaw Perfection 2026+ Audit - Relationship Enhancement, Thematic Consolidation, and Knowledgebase UI`
- **v1.5.0-intel**: `e81051a` `feat: Phase 12 Factual HybridGraph UI (BrainClaw Memory, Lossless Memories, Knowledgebase, Self-learning Entries)`
- **v1.5.0**: `5db43b1` `feat: BrainClaw v1.5.0 - Universal Leiden Fallback & Mode-Aware Retrieval`
 
v1.5.0-intel-perfection achieves **Total Graph Unification** and product-grade reliability:
- **World-Class Connectivity**: Automated **Global Entity Linking** has unified memories into a dense, high-fidelity knowledge network (eliminating fragmentation).
- **Definitive Thematic Consolidation**: Optimized **Knowledgebase Clustering** via definitive Leiden resolution for superior global RAG reasoning.
- **Professionalized UI**: All UI terminologies professionalized to **Knowledgebase** (superseding legacy 'Agent's Knowledge' labels).
- **Architectural Zero-Friction**: Resolved all circular imports, DB connection errors, and situational fragmentation for the 2026+ intelligence standard.

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
brainclaw hybrid_graphrag_leiden
brainclaw lcm_expand
brainclaw lcm_describe
```

## Quick Verification

On a running OpenClaw install:

```bash
brainclaw memory sync
brainclaw lcm status
brainclaw lcm sync --mode incremental
brainclaw rebuild --target neo4j
```

## Verification & Benchmarks

For the definitive quantitative metrics and operational proof of the **v1.5.0-intel-perfection** release, please see the [BENCHMARK.md](./BENCHMARK.md).

- **Graph Density**: 1,234,116 relationships across 766 nodes.
- **Thematic Consolidation**: 173 communities (Leiden 0.1 Resolution).
- **Sync Performance**: < 450ms average latency.
- **Identity Integrity**: 100% "Knowledgebase" terminological synchronization.

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
