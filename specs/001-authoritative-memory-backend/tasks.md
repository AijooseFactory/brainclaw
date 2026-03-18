# Tasks: Authoritative OpenClaw Memory Backend

**Input**: Design documents from `/specs/001-authoritative-memory-backend/`
**Prerequisites**: plan.md, spec.md

**Tests**: Tests are REQUIRED for behavior-changing work. Runtime verification
tasks below supplement automated coverage for the live OpenClaw deployment and
the non-destructive plugin install flow.

**Organization**: Tasks are grouped by user story so each story can be
implemented and verified independently.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture current drift, create reusable test harnesses, and prepare
runtime verification without changing production behavior.

- [ ] T001 Document current contract drift, runtime drift, and plugin install
      expectations in
      `specs/001-authoritative-memory-backend/research.md`
- [ ] T002 Document the target data model for canonical PostgreSQL storage,
      promotion policy, provenance, decision memory, and supersession in
      `specs/001-authoritative-memory-backend/data-model.md`
- [ ] T003 Create reusable OpenClaw plugin API test fixtures in
      `tests/helpers/plugin_api.js`
- [ ] T004 Create reusable bridge/spawn test fixtures in
      `tests/helpers/bridge.js`
- [ ] T005 Document safe install, rollback, rebuild, and verification steps in
      `specs/001-authoritative-memory-backend/quickstart.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the portable runtime contract and operator-facing truth
model that all user stories depend on.

**⚠️ CRITICAL**: No user story work should be considered complete until these
tasks are green.

- [ ] T005 [P] Add failing portability tests for configuration/env/path
      resolution in `tests/bridge.test.js`
- [ ] T006 [P] Add failing plugin contract tests for memory-plugin registration
      in `tests/plugin-contract.test.js`
- [ ] T007 [P] Add failing capability-status tests for truthful runtime feature
      reporting in `tests/capability-status.test.js`
- [ ] T008 [P] Add failing canonical-ledger, provenance, promotion, and
      supersession tests in `python/tests/test_memory_contract.py`
- [ ] T009 Define shared runtime context and capability-status helpers in
      `src/runtime_context.ts` and `src/capability_status.ts`
- [ ] T010 Define canonical memory contract models in
      `python/openclaw_memory/memory/classes.py`,
      `python/openclaw_memory/memory/lifecycle.py`, and
      `python/openclaw_memory/memory/write_policy.py`
- [ ] T011 Refactor `src/index.ts`, `src/bridge.ts`, and `src/validation.ts` to
      use portable runtime context instead of instance-specific defaults
- [ ] T012 Add non-destructive install and verification helpers in
      `scripts/install-openclaw-plugin.sh` and `scripts/verify-openclaw-plugin.sh`

**Checkpoint**: BrainClaw has a portable contract surface, truthful capability
status model, canonical memory contract scaffolding, and repeatable
install/verification entry points.

---

## Phase 3: User Story 1 - Authoritative Conversational Memory (Priority: P1)

**Goal**: BrainClaw behaves like a real OpenClaw memory backend, exposes the
expected memory tools, and works in both single-agent and multi-agent runtime
modes without relying on `MEMORY.md` as the primary recall path.

**Independent Test**: Run the memory contract tests plus live OpenClaw checks
to verify `memory_search` and `memory_get` work through BrainClaw in both
single-agent and multi-agent configurations.

### Tests for User Story 1

- [ ] T013 [P] [US1] Add failing registration tests for `memory_search` and
      `memory_get` in `tests/plugin-contract.test.js`
- [ ] T014 [P] [US1] Add failing behavior tests for memory search/get adapter,
      promoted-memory provenance, and decision recall in `tests/tools.test.js`
- [ ] T015 [P] [US1] Add failing backend retrieval/identity tests in
      `python/tests/test_bridge_entrypoints.py`

### Implementation for User Story 1

- [ ] T016 [US1] Add BrainClaw-backed `memory_search` and `memory_get` tool
      adapters in `src/tools/memory_search.ts` and `src/tools/memory_get.ts`
- [ ] T017 [US1] Refactor plugin registration in `src/index.ts` so BrainClaw
      registers the standard OpenClaw memory contract and only exposes advanced
      tools/services that are actually supported
- [ ] T018 [US1] Extend bridge entry points for authoritative memory retrieval,
      record lookup, decision recall, and provenance return in
      `python/openclaw_memory/bridge_entrypoints.py`
- [ ] T019 [US1] Implement single-agent and multi-agent context routing in
      `src/runtime_context.ts`,
      `python/openclaw_memory/integration/session_context.py`, and
      `python/openclaw_memory/security/access_control.py`
- [ ] T020 [US1] Implement canonical PostgreSQL-backed durable memory writes,
      lifecycle, and provenance capture in
      `python/openclaw_memory/storage/postgres.py`,
      `python/openclaw_memory/pipeline/ingestion.py`,
      `python/openclaw_memory/memory/lifecycle.py`, and
      `python/openclaw_memory/memory/write_policy.py`
- [ ] T021 [US1] Update memory-related operator documentation in
      `README.md` and
      `specs/001-authoritative-memory-backend/quickstart.md`

**Checkpoint**: BrainClaw satisfies the primary OpenClaw memory contract and is
independently testable without advanced features.

---

## Phase 4: User Story 2 - Verifiable Advanced Capabilities (Priority: P2)

**Goal**: Operators can tell which BrainClaw capabilities are real, healthy,
portable, and safe to rely on, and incomplete capabilities are not presented as
complete.

**Independent Test**: Run capability-status tests, portability tests, and live
status verification to confirm that advertised features match the running
plugin.

### Tests for User Story 2

- [ ] T022 [P] [US2] Add failing capability truthfulness tests in
      `tests/capability-status.test.js`
- [ ] T023 [P] [US2] Add failing placeholder-service tests in
      `tests/services.test.js`
- [ ] T024 [P] [US2] Add failing portability tests for alternate agent IDs,
      tenant IDs, and install paths in `tests/bridge.test.js`
- [ ] T025 [P] [US2] Add failing tests for promotion rules, contradiction
      blocking, supersession chains, and rebuildability in
      `python/tests/test_promotion_and_rebuild.py`

### Implementation for User Story 2

- [ ] T026 [US2] Implement capability status computation and operator reporting
      in `src/capability_status.ts`, `src/index.ts`, and `src/logging.ts`
- [ ] T027 [US2] Replace placeholder contradiction and audit behaviors with
      verifiable implementations or explicitly downgrade them in
      `src/tools/contradiction_check.ts`,
      `src/services/contradiction_detector.ts`, and
      `src/services/audit_logger.ts`
- [ ] T028 [US2] Remove `ajf-openclaw`-specific, path-specific, and
      agent-name-specific assumptions from `src/bridge.ts`,
      `src/validation.ts`, `python/openclaw_memory/bridge_entrypoints.py`, and
      `python/openclaw_memory/config.py`
- [ ] T029 [US2] Implement decision memory, supersession links, temporal
      retrieval, and intent-routed evidence assembly in
      `python/openclaw_memory/retrieval/policy.py`,
      `python/openclaw_memory/retrieval/fusion.py`,
      `python/openclaw_memory/graph/communities.py`, and
      `python/openclaw_memory/graph/summarize.py`
- [ ] T030 [US2] Add rebuild workflows for Weaviate and Neo4j derived indexes
      in `python/openclaw_memory/pipeline/sync.py` and
      `python/openclaw_memory/storage/migrations/run_migrations.py`
- [ ] T031 [US2] Update operator-facing capability and portability docs in
      `README.md` and
      `specs/001-authoritative-memory-backend/quickstart.md`

**Checkpoint**: BrainClaw’s advanced capabilities are either implemented and
observable or clearly marked incomplete, and the plugin no longer depends on
instance-specific assumptions.

---

## Phase 5: User Story 3 - Safe Migration Away from File-Backed Memory (Priority: P3)

**Goal**: Operators can migrate relevant file-backed memory into BrainClaw,
keep rollback options, and install the packaged plugin in a standard OpenClaw
plugin directory without losing existing data or settings.

**Independent Test**: Run migration tests plus a non-destructive install into a
standard plugin directory, then verify OpenClaw can still use BrainClaw with
file-backed fallback preserved.

### Tests for User Story 3

- [ ] T032 [P] [US3] Add failing migration workflow tests in
      `python/tests/test_migration_orchestrator.py`
- [ ] T033 [P] [US3] Add failing install/rollback verification tests in
      `tests/install-flow.test.js`

### Implementation for User Story 3

- [ ] T034 [US3] Harden migration orchestration and reporting in
      `python/openclaw_memory/migration/orchestrator.py` and
      `python/openclaw_memory/storage/migrations/migrate_memory_md.py`
- [ ] T035 [US3] Implement safe packaged-plugin install and rollback behavior
      in `scripts/install-openclaw-plugin.sh`,
      `scripts/verify-openclaw-plugin.sh`, and
      `openclaw.plugin.json`
- [ ] T036 [US3] Document migration, fallback, rollback, and rebuild procedures
      in
      `specs/001-authoritative-memory-backend/quickstart.md` and `README.md`

**Checkpoint**: BrainClaw can be installed as a standard plugin, migration is
documented and verifiable, and rollback is preserved.

---

## Phase 6: Polish & Cross-Cutting Verification

**Purpose**: Finish the release gate with evidence from tests, packaging, and
the live OpenClaw deployment.

- [ ] T031 [P] Run `npm test` from
- [ ] T037 [P] Run `npm test` from
      `/Users/george/Mac/data/usr/projects/ai_joose_factory/packages/brainclaw`
- [ ] T038 [P] Run targeted Python tests in
      `python/tests/test_bridge_entrypoints.py` and
      `python/tests/test_memory_contract.py`,
      `python/tests/test_promotion_and_rebuild.py`, and
      `python/tests/test_migration_orchestrator.py`
- [ ] T039 Run `scripts/verify-openclaw-plugin.sh` against the local OpenClaw
      deployment without touching unrelated containers
- [ ] T040 Verify BrainClaw is installed in the standard OpenClaw plugin
      directory and selected safely in the target instance configuration
- [ ] T041 Verify single-agent and multi-agent acceptance flows against the
      live OpenClaw instance and record evidence in
      `specs/001-authoritative-memory-backend/quickstart.md`
- [ ] T042 Verify decision recall, provenance presence, supersession chains, and
      derived-index rebuildability against the live deployment and record
      evidence in `specs/001-authoritative-memory-backend/quickstart.md`

---

## Dependencies & Execution Order

- Setup must complete before foundational work.
- Foundational work blocks all user stories.
- User Story 1 is the MVP and must complete before User Stories 2 and 3 are
  treated as done.
- User Story 2 depends on the portable context and contract work from
  foundational tasks plus the authoritative memory path from User Story 1.
- User Story 3 depends on the packaged plugin and truthful capability state
  established by User Stories 1 and 2.
- Cross-cutting verification happens last and must include both automated
  evidence and live runtime checks.

## Parallel Opportunities

- `T002` and `T003` can run in parallel.
- `T005`, `T006`, and `T007` can run in parallel.
- Within User Story 1, `T011`, `T012`, and `T013` can run in parallel.
- Within User Story 2, `T019`, `T020`, and `T021` can run in parallel.
- Within User Story 3, `T026` and `T027` can run in parallel.

## Implementation Strategy

1. Establish the portable contract and test harness.
2. Make BrainClaw authoritative for the core OpenClaw memory workflow.
3. Reconcile advanced capabilities with truth and portability.
4. Package and install BrainClaw as a standard OpenClaw plugin with safe
   migration and rollback.
5. Verify everything in the live deployment before claiming completion.
