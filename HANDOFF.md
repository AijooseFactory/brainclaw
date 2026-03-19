# BrainClaw Handoff

> Last updated: 2026-03-19
> Repo branch: `main`
> Repo HEAD: `4400a2f269610cb9e150a58c26334166cceee573`
> Live OpenClaw mount: `./brainclaw-sync -> /home/node/.openclaw/extensions/brainclaw`

## Read This First

BrainClaw is a plugin repository, not part of the OpenClaw core `/app` source tree.

If you are verifying or changing BrainClaw, use one of these two paths:

- agent-visible repo: `/home/node/Mac/data/usr/projects/ai_joose_factory/packages/brainclaw`
- live mounted plugin: `/home/node/.openclaw/extensions/brainclaw`

Both paths were verified on 2026-03-19 and both resolve to the same commit:

- `4400a2f269610cb9e150a58c26334166cceee573`

Do not inspect `/app/src` or `/app/package.json` and assume those files describe BrainClaw. `/app` is OpenClaw core.

## Version Map

These three version numbers refer to different systems:

- OpenClaw runtime version: `2026.3.14`
- BrainClaw plugin/package version: `1.3.0`
- Lossless-Claw plugin version: `0.4.0`

If a report mixes those values together, the report is wrong.

## Git State

Current `main` history relevant to continuation work:

- `4400a2f` `docs: correct brainclaw handoff and verification guidance`
- `022138c` `fix: suppress env-backed secret warnings`
- `adf97cc` `Update HANDOFF.md`
- `9d263b3` `docs: broaden handoff to full brainclaw project`
- `b39c963` `docs: refresh handoff for current main state`
- `957d812` `chore: stop tracking local codex and specify artifacts`

`957d812` is no longer the repo head. Any handoff or report that still treats it as the current baseline is stale.

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
- tools:
  - `search`
  - `memory_search`
  - `memory_get`
  - `ingest`
  - `graph_health`
  - `contradiction_check`
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

These are actually present in the repo. Do not claim they are missing without checking the BrainClaw repo path above.

### Python backend

The Python backend lives under `python/openclaw_memory` and currently includes:

- storage clients:
  - PostgreSQL
  - Neo4j
  - Weaviate
- pipeline modules:
  - ingestion
  - chunking
  - extraction
  - llm_extraction
  - redaction
  - sync
- retrieval modules:
  - fusion
  - rrf_fusion
  - intent
  - policy
  - drill_down
- graph modules:
  - health
  - communities
  - summarize
- memory modules:
  - classes
  - lifecycle
  - write_policy
- observability modules:
  - logging
  - metrics
  - telemetry
  - lcm_metrics
- security modules:
  - access_control
  - team_lookup

### Integration layer

The integration directory does exist and currently contains:

- `python/openclaw_memory/integration/source_adapter.py`
- `python/openclaw_memory/integration/artifact_validation.py`
- `python/openclaw_memory/integration/lcm_migration.py`
- `python/openclaw_memory/integration/lossless_adapter.py`
- `python/openclaw_memory/integration/lossless_sync.py`
- `python/openclaw_memory/integration/memory_backup.py`
- `python/openclaw_memory/integration/openclaw_client.py`
- `python/openclaw_memory/integration/operational_memory_sync.py`
- `python/openclaw_memory/integration/operations.py`
- `python/openclaw_memory/integration/promotion_override.py`
- `python/openclaw_memory/integration/session_context.py`
- `python/openclaw_memory/integration/sync_error_handling.py`

## Runtime Verification

Freshly verified against the running `ajf-openclaw` container on 2026-03-19:

Command run:

- `docker exec ajf-openclaw node /app/openclaw.mjs brainclaw lcm status`

Verified runtime facts:

- BrainClaw plugin initialized as version `1.3.0`
- Lossless-Claw compatibility state: `installed_compatible`
- Lossless-Claw plugin version: `0.4.0`
- OpenClaw runtime version: `2026.3.14`
- schema fingerprint: `273f618956474734`
- supported profile: `lossless-claw-v0.4.0-core`
- runtime tools available:
  - `lcm_grep`
  - `lcm_describe`
  - `lcm_expand_query`
  - `lcm_expand`

Verified derived-store state from the same run:

- Weaviate rebuild status: `completed`
- Neo4j rebuild status: `completed`
- Neo4j last validated target state:
  - `entity_count: 766`
  - `relationship_count: 27`
  - `memory_item_count: 2372`

## Test Evidence

### Node tests from the BrainClaw repo

Command:

- `npm test`

Result on 2026-03-19:

- `37` tests passed
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

- `56` tests passed
- `8` failed

Those host-side failures were environment-related:

- missing async test support on the host Python environment
- missing `asyncpg` on the host Python environment

That host failure is not evidence that the live plugin is broken. The container runtime test is the relevant operational check.

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
