# BrainClaw Plugin (OpenClaw Memory Slot)

BrainClaw is the canonical durable memory plugin for OpenClaw.

- Canonical ledger: **PostgreSQL**
- Derived stores: **Weaviate** (retrieval), **Neo4j** (graph)
- Lossless-Claw role: **upstream context source only** (never canonical truth)

This repository implements BrainClaw + Lossless-Claw integration **without changing Lossless-Claw code or schema**.

## Compatibility Matrix

### Runtime floor currently enforced in code
- OpenClaw: `2026.3.14+`
- Lossless-Claw: `0.4.0`

### Historical PRD baseline
- OpenClaw `2026.3.13` / tag `v2026.3.13-1` is retained as a documented baseline reference.

Unknown OpenClaw versions and unknown Lossless-Claw schema fingerprints do not silently enable import.

## Runtime Gate Contract

BrainClaw enables Lossless-Claw integration only when all required checks pass:

1. OpenClaw version is supported.
2. `plugins.slots.memory=brainclaw`.
3. `plugins.slots.contextEngine=lossless-claw`.
4. Lossless-Claw install is present in `plugins.installs`.
5. Lossless-Claw is registered/enabled in plugin runtime entries.
6. Required Lossless-Claw tools are available at runtime (or from supported fallback discovery).

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
- last degraded reason/timestamp
- last successful supported profile

## Canonical Data Flow

Authority flow:

1. Import Lossless-Claw artifacts into `source_artifacts`.
2. Validate + scope-check + trust-check (fail closed).
3. Extract staged `memory_candidates`.
4. Run contradiction and promotion policy.
5. Write promoted `memory_items` to PostgreSQL.
6. Mark derived-store backfill for Weaviate/Neo4j.

Exact-once dedupe is enforced by:
- deterministic `artifact_hash`
- unique composite key: source plugin + scope key + artifact type + artifact id + source timestamp + hash

Repair/replay is deterministic and does not duplicate already-promoted memory from already-imported artifacts.

## Promotion Policy

Promotion thresholds are explicit:

- auto-promote when `raw_extraction_confidence >= 0.85`
- or promote when `interpretive_confidence >= 0.70` **and** `topic_hint_match_score >= 0.60`
- otherwise block as `LOW_CONFIDENCE` unless stronger corroboration or privileged override applies

Interpretive candidates never bypass policy.

## Drill-Down Contract

BrainClaw retrieval is memory-first. Lossless-Claw drill-down is supplemental evidence only.

Drill-down order:
1. `lcm_expand_query` (if available and allowed)
2. `lcm_expand` (if available and allowed)
3. Direct SQLite DAG traversal (supported fingerprints only)
4. Canonical-only response with degraded state surfaced

## ACL / Scope Contract

BrainClaw persists ACL/scope fields on source artifacts, candidates, and promoted memory:

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

`brainclaw lcm status` returns compatibility state, reason code, checkpoint state, replay state, backfill summary, and rebuild checkpoint status.

## Configuration Surface

Lossless-Claw integration config keys (BrainClaw-owned):

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

See [`openclaw.plugin.json`](/Users/george/Mac/data/usr/projects/ai_joose_factory/.a0proj/ajf-openclaw/brainclaw-sync/openclaw.plugin.json) for schema defaults and enums.

## Rollout Safety (ajf-openclaw and generic OpenClaw installs)

Required production safety rules:

- Never roll production against floating local OpenClaw HEAD.
- Never recreate production with an empty `./data` mount.
- Never run destructive volume commands (`docker compose down -v`).
- Never hand-edit `data/openclaw.json` or `plugins.installs`.
- Always take a pre-change snapshot of the OpenClaw state directory.
- Validate staging on the same version/config/state shape before production promotion.

Restart/rebuild acceptance expectations:

- Preserve `plugins.slots.memory=brainclaw`.
- Preserve `plugins.slots.contextEngine=lossless-claw`.
- Preserve `plugins.installs` and plugin-enabled state.
- Preserve Control UI config, auth, agents, sessions, workspaces, and canonical BrainClaw state.

## Development

```bash
npm install
npm run build
npm test

pip install -r requirements.txt
PYTHONPATH=python pytest -q
```
