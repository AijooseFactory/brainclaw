# BrainClaw Plugin

BrainClaw is the canonical durable memory plugin for OpenClaw.

- Canonical ledger: **PostgreSQL**
- Derived stores: **Weaviate** for retrieval and **Neo4j** for graph reasoning
- Lossless-Claw role: **upstream context and drill-down source only**

This repository now includes the BrainClaw + Lossless-Claw integration contract on `main`. The integration was implemented inside BrainClaw only. Lossless-Claw was not modified.

## What Shipped

The current integration on `main` adds:

- OpenClaw runtime gating before Lossless-Claw import is enabled
- Lossless-Claw detection, schema fingerprinting, and compatibility-state persistence
- Canonical import of LCM artifacts into BrainClaw `source_artifacts`
- Deterministic sync, replay, rebuild, and exact-once artifact dedupe
- Tool-first drill-down with SQLite fallback for supported fingerprints only
- CLI status and sync surfaces for bootstrap, incremental, repair, and rebuild flows
- PRD-aligned README, manifest, data-model, and tests

The integration landing commit is:

- [`50f8a3f`](https://github.com/AijooseFactory/brainclaw/commit/50f8a3f10110e7a91fddcf26ecb0ff34c30d829e) `feat: align lcm integration contract, runtime gating, and status surfaces`

The compare view from the prior repo state is:

- [`e57dfdb...50f8a3f`](https://github.com/AijooseFactory/brainclaw/compare/e57dfdb...50f8a3f)

## Where The Integration Lives

The main implementation entrypoints are:

- [`src/lcm_runtime.ts`](./src/lcm_runtime.ts) for OpenClaw runtime gating, compatibility checks, and Lossless-Claw tool discovery
- [`python/openclaw_memory/integration/lossless_adapter.py`](./python/openclaw_memory/integration/lossless_adapter.py) for the read-only Lossless-Claw adapter
- [`python/openclaw_memory/integration/lossless_sync.py`](./python/openclaw_memory/integration/lossless_sync.py) for bootstrap, incremental, repair, checkpoints, replay, and import flow
- [`python/openclaw_memory/bridge_entrypoints.py`](./python/openclaw_memory/bridge_entrypoints.py) for `lcm status`, `lcm sync`, and rebuild bridge entrypoints
- [`openclaw.plugin.json`](./openclaw.plugin.json) for the BrainClaw-owned Lossless-Claw config surface
- [`specs/001-authoritative-memory-backend/data-model.md`](./specs/001-authoritative-memory-backend/data-model.md) for the canonical data contract

## Compatibility Matrix

### Runtime floor currently enforced in code

- OpenClaw: `2026.3.14+`
- Lossless-Claw: `0.4.0`

### Historical PRD baseline

- OpenClaw `2026.3.13` / tag `v2026.3.13-1` remains documented because the PRD was originally locked against that baseline.

Practical interpretation:

- `2026.3.14+` is what the code currently accepts.
- `2026.3.13` remains part of the product history and compatibility discussion, but is not the active enforced floor in this repo state.

Unknown OpenClaw versions and unknown Lossless-Claw schema fingerprints do not silently enable import.

## Runtime Gate Contract

BrainClaw enables Lossless-Claw integration only when all required checks pass:

1. OpenClaw version is supported.
2. `plugins.slots.memory=brainclaw`.
3. `plugins.slots.contextEngine=lossless-claw`.
4. Lossless-Claw install is present in `plugins.installs`.
5. Lossless-Claw is registered and enabled in active runtime plugin entries.
6. Required Lossless-Claw tools are available at runtime, or a supported fallback path exists.

Supported compatibility states are:

- `not_installed`
- `installed_compatible`
- `installed_degraded`
- `installed_incompatible`
- `installed_unreachable`

BrainClaw persists integration state in canonical storage (`integration_states`) with:

- current state
- reason code
- last successful gate timestamp
- last degraded reason and timestamp
- last successful supported profile

## Canonical Data Flow

Authority flows in one direction:

1. Import Lossless-Claw artifacts into `source_artifacts`.
2. Validate, scope-check, and trust-check with fail-closed behavior.
3. Extract staged `memory_candidates`.
4. Run contradiction checks and promotion policy.
5. Write promoted `memory_items` to PostgreSQL.
6. Mark derived-store backfill for Weaviate and Neo4j.

Exact-once dedupe is enforced by:

- deterministic `artifact_hash`
- a composite unique identity across source plugin, scope key, artifact type, artifact id, source timestamp, and hash

Repair and replay are deterministic and do not duplicate already-promoted memory from already-imported artifacts.

## Promotion Policy

Promotion thresholds are explicit:

- auto-promote when `raw_extraction_confidence >= 0.85`
- or promote when `interpretive_confidence >= 0.70` and `topic_hint_match_score >= 0.60`
- otherwise block as `LOW_CONFIDENCE` unless stronger corroboration or privileged override applies

Interpretive candidates never bypass policy.

## Drill-Down Contract

BrainClaw retrieval is memory-first. Lossless-Claw drill-down is supplemental evidence only.

Drill-down order:

1. `lcm_expand_query` when available and allowed
2. `lcm_expand` when available and allowed
3. direct SQLite DAG traversal for supported fingerprints only
4. canonical-only response with degraded state surfaced

## ACL And Scope Contract

BrainClaw persists ACL and scope fields on source artifacts, candidates, and promoted memory:

- `workspace_id`
- `agent_id`
- `session_id`
- `project_id`
- `user_id`
- `visibility_scope`
- `owner_id`
- `statefulness`
- `access_control`

Default write policy is owner-only unless explicitly authorized.

## Operational Commands

```bash
brainclaw lcm status
brainclaw lcm sync --mode bootstrap
brainclaw lcm sync --mode incremental
brainclaw lcm sync --mode repair
brainclaw rebuild --target weaviate
brainclaw rebuild --target neo4j
brainclaw memory sync
```

`brainclaw lcm status` returns:

- compatibility state
- reason code
- supported profile
- checkpoint state
- replay state
- backfill summary
- rebuild checkpoint status

## Quick Verification

On a running OpenClaw install with BrainClaw as memory slot and Lossless-Claw installed:

```bash
brainclaw lcm status
brainclaw lcm sync --mode incremental
brainclaw rebuild --target neo4j
```

Healthy integration should show:

- `compatibility_state: installed_compatible`
- a supported Lossless-Claw schema fingerprint
- runtime tool availability for `lcm_expand_query` and/or `lcm_expand`
- checkpoint progress
- rebuild status for derived stores

## Configuration Surface

Lossless-Claw integration config keys owned by BrainClaw:

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

See [`openclaw.plugin.json`](./openclaw.plugin.json) for config defaults, enums, and descriptions.

## Rollout Safety

### Generic OpenClaw installs

Required production safety rules:

- Never roll production against floating local OpenClaw HEAD.
- Never recreate production with an empty `./data` mount.
- Never run destructive volume commands such as `docker compose down -v`.
- Never hand-edit `data/openclaw.json` or `plugins.installs`.
- Always take a pre-change snapshot of the OpenClaw state directory.
- Validate staging on the same version, config, and state shape before production promotion.

### State preservation expectations

Restart and rebuild must preserve:

- `plugins.slots.memory=brainclaw`
- `plugins.slots.contextEngine=lossless-claw`
- `plugins.installs` and plugin-enabled state
- Control UI configuration
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
