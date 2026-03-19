# BrainClaw Handoff

> Last updated: 2026-03-19  
> Branch: `main`  
> Head: `957d812`  
> Live OpenClaw mount: `./brainclaw-sync -> /home/node/.openclaw/extensions/brainclaw`

## Current Truth

This repository is no longer on a feature branch. The active integration work was merged to `main`, and the current repo head is:

- `957d812` `chore: stop tracking local codex and specify artifacts`

Important recent commits on `main`:

- `50f8a3f` `feat: align lcm integration contract, runtime gating, and status surfaces`
- `7af6ca1` `Update README.md`
- `7f892ce` `chore: ignore local codex prompt artifacts`
- `957d812` `chore: stop tracking local codex and specify artifacts`

Do not use older notes that refer to `codex/lossless-claw-integration`. That branch is obsolete for current continuation work.

## What Is Implemented

BrainClaw on `main` includes:

- OpenClaw runtime gating for Lossless-Claw integration
- compatibility-state persistence and schema fingerprint handling
- canonical LCM import into `source_artifacts`
- staged candidate extraction and promotion pipeline
- CLI surfaces for `brainclaw lcm status`, `sync`, `rebuild`, and `brainclaw memory sync`
- operational memory sync features
- PRD-aligned plugin manifest and canonical data-model documentation

Primary implementation files:

- `src/lcm_runtime.ts`
- `src/register_cli.ts`
- `python/openclaw_memory/bridge_entrypoints.py`
- `python/openclaw_memory/integration/lossless_adapter.py`
- `python/openclaw_memory/integration/lossless_sync.py`
- `python/openclaw_memory/integration/source_adapter.py`
- `python/openclaw_memory/integration/artifact_validation.py`
- `python/openclaw_memory/integration/operational_memory_sync.py`
- `python/openclaw_memory/retrieval/drill_down.py`
- `python/openclaw_memory/retrieval/intent.py`
- `python/openclaw_memory/observability/lcm_metrics.py`

## Live Runtime Verification

Freshly verified against the running `ajf-openclaw` container on 2026-03-19:

Command run:

- `docker exec ajf-openclaw node /app/openclaw.mjs brainclaw lcm status`

Verified runtime facts:

- `compatibility_state: installed_compatible`
- `openclaw_version: 2026.3.14`
- `plugin_version: 0.4.0`
- `schema_fingerprint: 273f618956474734`
- `supported_profile: lossless-claw-v0.4.0-core`
- runtime tools available:
  - `lcm_grep`
  - `lcm_describe`
  - `lcm_expand_query`
  - `lcm_expand`

Verified operational state from the same run:

- checkpoint status: `completed`
- replay status: `completed`
- Weaviate rebuild status: `completed`
- Neo4j rebuild status: `completed`
- Neo4j status included nonzero relationships: `relationship_count: 27`

## Fresh Test Evidence

Freshly run on 2026-03-19:

### Node

Command:

- `npm test`

Result:

- `35` tests passed
- `0` failed

### Python

Command:

- `PYTHONPATH=python pytest -q python/tests/test_lossless_claw_contract.py python/tests/test_lossless_claw_sync.py python/tests/test_lossless_claw_bridge.py python/tests/test_operational_memory_sync.py python/tests/test_memory_contract.py`

Result:

- `43` tests passed
- `0` failed
- `1` warning about unknown pytest config option `asyncio_mode`

## Repo Hygiene State

This repo now ignores and no longer tracks:

- `.codex/prompts`
- `.specify`

That cleanup was committed so those local artifacts should not be reintroduced into Git history unless explicitly intended.

## README State

The README on `main` currently reflects user-authored framing:

- title: `# BrainClaw`
- lead sentence begins: `BrainClaw is a Hybrid GraphRAG for OpenClaw memory plugin for OpenClaw.`

Do not silently rewrite that wording without user approval. The user explicitly changed it.

## Deployment Notes

For the local `ajf-openclaw` deployment:

- the authoritative OpenClaw state directory is `./data`
- the live BrainClaw code mount is `./brainclaw-sync`
- Python backend path inside container is `/home/node/.openclaw/extensions/brainclaw/python`

Operational safety rules still apply:

- do not run `docker compose down -v`
- do not recreate with an empty `./data` mount
- do not hand-edit `data/openclaw.json` or `plugins.installs`

## Known Caveats

- Live logs still warn when sensitive config values such as `postgresUrl` or `neo4jPassword` are configured as plaintext instead of `${ENV_VAR}` references.
- `npm test` is a mocked/unit-level confirmation. It does not replace live container verification.
- The Python verification above covered the current contract and integration suites, not every Python test file in the repo.

## Recommended Next Checks

If another agent continues from here, use this order:

1. `git status --short --branch`
2. `git log --oneline --decorate -n 5`
3. `docker exec ajf-openclaw node /app/openclaw.mjs brainclaw lcm status`
4. If touching integration code, rerun:
   - `npm test`
   - `PYTHONPATH=python pytest -q python/tests/test_lossless_claw_contract.py python/tests/test_lossless_claw_sync.py python/tests/test_lossless_claw_bridge.py python/tests/test_operational_memory_sync.py python/tests/test_memory_contract.py`

## Do Not Assume

Do not assume any of the following older handoff claims are still valid:

- feature branch workflows
- pending merge to `main`
- stale README text
- tracked `.codex/prompts` or `.specify`
- zero-edge Neo4j state

Use `main` and current runtime verification as the handoff baseline.
