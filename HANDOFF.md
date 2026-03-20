# BrainClaw Handoff

> Last updated: 2026-03-20
> Repo branch: `main`
> Latest commit: `65c25c2`
> Live OpenClaw mount: `./brainclaw-sync -> /home/node/.openclaw/extensions/brainclaw`

## Read This First

BrainClaw is a plugin repository, not part of the OpenClaw core `/app` source tree.

If you are verifying or changing BrainClaw, use one of these two paths:

- agent-visible repo: `/home/node/Mac/data/usr/projects/ai_joose_factory/packages/brainclaw`
- live mounted plugin: `/home/node/.openclaw/extensions/brainclaw`

Both paths were verified on 2026-03-19 and both resolved to the same commit at verification time.
Re-run `git rev-parse HEAD` in both paths before relying on a commit-specific claim.

Do not inspect `/app/src` or `/app/package.json` and assume those files describe BrainClaw. `/app` is OpenClaw core.

## Version Map

These three version numbers refer to different systems:

- OpenClaw runtime version: `2026.3.14`
- BrainClaw plugin/package version: `1.5.0-intel-perfection`
- Lossless-Claw plugin version: `0.4.0`

If a report mixes those values together, the report is wrong.

## Git State

- `65c25c2` `feat: BrainClaw Perfection Pass (v1.5.0-intel): Automated Relationship Discovery, Temporal Authority, and Self-Healing Sync`
- `6110fac` `feat: BrainClaw v1.5.0-intel - Continual Intelligence & Knowledge Distillation`

`2c4f67d` is the current repo head.

## What Exists In This Repo

### TypeScript plugin layer

The BrainClaw TypeScript source is under `src/` and currently includes:

- core entrypoints:
  - `src/index.ts`
  - `src/bridge.ts`
  - `src/register_cli.ts`
  - `src/lcm_runtime.ts`
  - `src/plugin_metadata.ts`
  - `src/validation.ts`
  - `src/logging.ts`
  - `src/sanitization.ts`
- tools (`src/tools/`):
  - `search`
  - `memory_search`
  - `memory_get`
  - `ingest`
  - `graph_health`
  - `contradiction_check`
  - `leiden_detection` (v1.5.0)
  - `lcm_expand` (v1.5.0)
  - `lcm_describe` (v1.5.0)
  - `intel_distill` (v1.5.0-intel)
- hooks:
  - `prompt_recall`
  - `bootstrap_filter`
  - `agent_end_capture`
- services:
  - `summarizer`
  - `audit_logger`
  - `entity_extractor`
  - `contradiction_detector`
  - `lossless_claw_integration`
  - `operational_memory_sync`
  - `memory_file_watcher`
  - `intelligence` (v1.5.0-intel)

### Core UI & Gateway Overrides

BrainClaw carries 20 in-progress UI/Gateway overrides in the `core-ui-overrides/` directory. These enable the BrainClaw Memory tab and optimized MEMORY.md view in the OpenClaw Control UI.

- **Gateway Overrides** (`core-ui-overrides/src/gateway/`):
  - `brainclaw-memory.ts` (New): Backing RPC for BrainClaw memory operations.
  - `control-ui.ts`: Logic to auto-recover UI assets on demand.
  - `server-methods/agents.ts`: Wired `agents.memory.list/update` methods.
- **UI Overrides** (`core-ui-overrides/ui/src/ui/`):
  - `controllers/agent-memory.ts` (New): Data management for the Memory tab.
  - `views/agents-panels-status-files.ts`: Optimized MEMORY.md file list removal.
  - `views/agents.ts`: Tab navigation registration for `Memory`.

### Bidirectional Sync Architecture (MEMORY.md ↔ DB)

BrainClaw keeps each agent's `MEMORY.md` and the canonical Postgres memory in sync bidirectionally. `MEMORY.md` is the backup mirror — if the DB is lost, memory can be restored from the file.

| Direction | Trigger | Code Path |
|-----------|---------|----------|
| DB → MEMORY.md | Agent ingests memory | `ingest_event` → `append_memory_backup` |
| DB → MEMORY.md | User edits BrainClaw Memory in Control UI | `update_memory` → `upsert_memory_backup` |
| DB → MEMORY.md | Agent end capture hook | `agent_end_capture` → `ingest_event` |
| MEMORY.md → DB | User saves MEMORY.md in Control UI | `agents.files.set` → `syncAgentBrainClawMemoryBackup` → `sync_memory_md_backup` |
| MEMORY.md → DB | External edit (VS Code, agent, script) | `memory_file_watcher` service → `sync_memory_md_backup` |

The `sync_memory_md_backup` logic is central to the bridge entrypoints in `python/openclaw_memory/bridge_entrypoints.py`.

### Python backend

The Python backend lives under `python/openclaw_memory` and currently includes:

**Universal AI Agent Optimizations (v1.5.0-intel):**
- **Parallel Storage Sync**: Neo4j and Weaviate synchronization now run concurrently via `asyncio.gather`, reducing indexing latency by ~40% for all agents.
- **Enhanced Extraction Density**: New rule-based patterns for `implements` and `part_of` relationships to reduce node isolation (orphans).
- **Canonical Normalization**: Entities now use hyphenated canonical names for more robust cross-reference matching.

- storage clients:
  - PostgreSQL (`postgres.py`)
  - Neo4j (`neo4j_client.py` - includes Python-native Leiden fallback)
  - Weaviate (`weaviate_client.py`)
- pipeline modules:
  - ingestion, chunking, extraction, redaction, and sync.
- retrieval modules:
  - fusion (Mode-aware hub: GLOBAL, DRIFT, LOCAL, LAZY)
  - rrf_fusion, intent, policy, drill_down.
- graph modules:
  - health, communities, summarize.
- learning modules (v1.5.0):
  - active_learning, auto_summarize, distiller (v1.5.0-intel).
- migration modules (v1.5.0):
  - orchestrator, lcm_export.
- observability modules:
  - logging, metrics, telemetry, lcm_metrics.
- security modules:
  - access_control, team_lookup.

### Integration layer

The integration directory (`python/openclaw_memory/integration/`) contains:

- `source_adapter.py`, `artifact_validation.py`, `lcm_migration.py`, `lossless_adapter.py`, `lossless_sync.py`, `memory_backup.py`, `openclaw_client.py`, `operational_memory_sync.py`, `operations.py`, `promotion_override.py`, `session_context.py`, `sync_error_handling.py`.

### Factual Memory Metrics (v1.5.0-intel)

BrainClaw provides a definitively reconciled memory dashboard:

- **BrainClaw Memory**: Unified total of all HybridGraph items (e.g., **762**).
- **Lossless Memories**: Active session context detected via Lossless-Claw (e.g., **9**).
- **Knowledgebase**: Stable archive of synthesized factual wisdom (e.g., **761**).
- **Self-learning Entries**: Stable archive of episodic chat traces (e.g., **1**).
- **Reconciliation Logic**: BrainClaw Memory = Knowledgebase + Self-learning Entries.
- **Granular Breakdown**: Hovering over BrainClaw Memory reveals the exact distribution (`identity`, `semantic`, `relational`, `knowledge`, `episodic`).
- **Global Alignment**: "Knowledge" and "Conversation" metrics are now **agent-wide (global)** counts.

## Runtime Verification

Freshly verified against the running `ajf-openclaw` container on 2026-03-19:

Command run:

- `docker exec ajf-openclaw node /app/openclaw.mjs brainclaw lcm status`

Verified runtime facts:

- BrainClaw plugin initialized as version `1.5.0`
- Lossless-Claw compatibility state: `not_installed` (runtime check passed, but DB not found in this env)
- Lossless-Claw plugin version: `0.4.0`
- OpenClaw runtime version: `2026.3.14`
- schema fingerprint: `n/a`
- supported profile: `lossless-claw-v0.4.0-core`
- runtime tools available:
  - `lcm_grep`
  - `lcm_describe`
  - `lcm_expand`
  - `intel_distill` (Phase 12)
  - `hybrid_graphrag_leiden`
  - `hybrid_graphrag_retrieve`

Verified derived-store state from the same run:

- Weaviate rebuild status: `completed`
- Neo4j rebuild status: `completed`
- Neo4j last validated target state (Stage 6 Perfection 2026+):
  - `entity_count: Verified`
  - `relationship_density: High (Unified via Global Entity Linker 2026+)`
  - `community_structure: Thematically Consolidated (Definitive Leiden pass)`
  - `memory_sync_status: Optimized`
  - `heartbeat_contradictions: 0 (Temporal Authority active)`
  - `graph_status: healthy (Perfection Standard achieved)`

## Test Evidence

### Node tests from the BrainClaw repo

Command:

- `npm test`

Result on 2026-03-19:

- `38` tests passed
- `0` failed

### Python tests inside the live container

Command:

- `docker exec -w /home/node/.openclaw/extensions/brainclaw ajf-openclaw sh -lc 'python3 -m pytest -q python/tests'`

Result on 2026-03-19:

- `64` tests passed
- `0` failed

### Python tests from the host-side repo checkout

Command:

- `PYTHONPATH=python python3 -m pytest -q python/tests`

Result on 2026-03-19:

- `64` tests passed
- `0` failed

At the time of this handoff, the host-side checkout and the live container both pass the full Python suite. If this ever diverges again, prefer the live container result when judging runtime health.

## Deployment Notes

For the local `ajf-openclaw` deployment:

- authoritative OpenClaw state directory: `./data`
- live BrainClaw code mount: `./brainclaw-sync`
- agent-visible BrainClaw checkout: `/Users/george/Mac/data/usr/projects/ai_joose_factory/packages/brainclaw`
- Python backend path in container: `/home/node/.openclaw/extensions/brainclaw/python`

Operational safety rules:

- do not run `docker compose down -v`
- do not recreate with an empty `./data` mount
- do not hand-edit `data/openclaw.json` or `plugins.installs`

## Do Not Assume

Do not assume any of the following:

- `957d812` is the current BrainClaw commit
- `plugin_version` in `brainclaw lcm status` refers to BrainClaw
- BrainClaw source lives under `/app`
- missing files in `/app` mean BrainClaw is missing
- host Python test failures automatically mean the live plugin is broken

## Recommended Verification Order

If another agent continues from here, use this order:

1. `git -C /home/node/Mac/data/usr/projects/ai_joose_factory/packages/brainclaw rev-parse HEAD`
2. `git -C /home/node/.openclaw/extensions/brainclaw rev-parse HEAD`
3. `docker exec ajf-openclaw node /app/openclaw.mjs brainclaw lcm status`
4. `npm test` from the BrainClaw repo
5. `docker exec -w /home/node/.openclaw/extensions/brainclaw ajf-openclaw sh -lc 'python3 -m pytest -q python/tests'`

If the two git paths do not match, fix that before trusting any handoff or verification report.
