# Implementation Plan: Authoritative OpenClaw Memory Backend

**Branch**: `codex/001-authoritative-memory-backend` | **Date**: 2026-03-18 | **Spec**: [spec.md](/Users/george/Mac/data/usr/projects/ai_joose_factory/packages/brainclaw/specs/001-authoritative-memory-backend/spec.md)
**Input**: Feature specification from `/specs/001-authoritative-memory-backend/spec.md`

## Summary

Make the local BrainClaw working tree the real OpenClaw memory backend for the
running `ajf-openclaw` deployment, with support for both single-agent and
multi-agent configurations, truthful feature status, safe migration away from
file-backed memory, production-style installation in OpenClaw’s plugin
directory, and instance-agnostic behavior that works across supported OpenClaw
deployments rather than only the current local stack. The implementation must
also make PostgreSQL the canonical durable memory ledger, keep Weaviate and
Neo4j rebuildable as derived indexes, and deliver decision/procedural memory,
promotion policy, provenance, supersession, and intent-routed retrieval as real
features rather than architecture-only claims.

## Technical Context

**Language/Version**: TypeScript (Node 24 runtime), Python 3.11+  
**Primary Dependencies**: TypeBox, TypeScript, asyncpg, weaviate-client, neo4j,
psycopg2-compatible access in runtime scripts  
**Storage**: PostgreSQL, Weaviate, Neo4j, OpenClaw state directory files for
config and migration inputs  
**Testing**: `node --test tests/**/*.test.js`, Python `pytest` where practical,
plus live runtime verification against `ajf-openclaw`  
**Target Platform**: Linux container runtime inside `ajf-openclaw` with macOS
host-mounted source tree  
**Project Type**: OpenClaw memory plugin with bundled Python backend  
**Performance Goals**: Memory retrieval and plugin health checks remain usable
in normal OpenClaw sessions without introducing obvious regression in operator
workflow  
**Constraints**: Preserve OpenClaw ControlUI data and config, avoid stopping or
impacting unrelated containers, avoid destructive changes to current state,
support both single-agent and multi-agent routing/isolation, avoid
`ajf-openclaw`-specific or agent-name-specific hardcoding  
**Scale/Scope**: One BrainClaw plugin package, one live `ajf-openclaw`
deployment, one canonical local working tree with existing uncommitted changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Memory Backend Authority**: Pass only if BrainClaw becomes the normal memory
  source when selected in the memory slot.
- **Canonical PostgreSQL Ledger**: Pass only if PostgreSQL becomes the
  authoritative ledger and derived stores are rebuildable.
- **Contract Parity Before Capability Claims**: Pass only if authoritative
  memory behavior is addressed before advanced feature claims are elevated.
- **Evidence-First Verification**: Pass only if each behavior change gets
  failing tests or explicit live probes.
- **Secure Multi-Agent Isolation**: Pass only if single-agent and multi-agent
  behavior preserve intended memory boundaries.
- **Operational Truth Over Marketing**: Pass only if repo claims, runtime
  behavior, and installed plugin state are reconciled.
- **Portable OpenClaw Compatibility**: Pass only if the same BrainClaw build
  adapts through configuration/discovery rather than instance-specific
  constants.

## Project Structure

### Documentation (this feature)

```text
specs/001-authoritative-memory-backend/
├── plan.md
├── spec.md
├── checklists/
│   └── requirements.md
├── research.md
├── data-model.md
├── quickstart.md
└── tasks.md
```

### Source Code (repository root)

```text
src/
├── bridge.ts
├── index.ts
├── logging.ts
├── sanitization.ts
├── validation.ts
├── services/
└── tools/

python/
└── openclaw_memory/
    ├── bridge_entrypoints.py
    ├── integration/
    ├── pipeline/
    ├── retrieval/
    ├── security/
    ├── storage/
    └── graph/

tests/
├── bridge.test.js
├── services.test.js
├── tools.test.js
└── e2e/
    └── smoke.test.js
```

**Structure Decision**: Keep the existing plugin/package layout. Implement
contract fixes at the TypeScript plugin boundary, backend behavior in the Python
package, and installation/runtime verification through the live `ajf-openclaw`
container and OpenClaw plugin directory.

## Implementation Phases

### Phase 0: Research and Baseline Capture

- Capture the current OpenClaw memory plugin expectations from the stock
  `memory-core` implementation.
- Capture the current BrainClaw runtime state in `ajf-openclaw`, including load
  path, plugin slot selection, and installed plugin roots.
- Capture the standard OpenClaw plugin discovery and runtime context surfaces
  BrainClaw can rely on across different instances.
- Document the target canonical-data architecture: PostgreSQL authority,
  rebuildable Weaviate/Neo4j indexes, memory classes, provenance, promotion,
  supersession, and decision memory.
- Document the production-style install target under
  `/home/node/.openclaw/extensions/brainclaw`.

### Phase 1: Canonical Data Model and Contract Fixes

- Add failing tests that prove BrainClaw does not yet satisfy the authoritative
  memory contract.
- Add failing tests that prove current code does not yet meet canonical-ledger,
  provenance, promotion, and supersession expectations.
- Add or adapt plugin behavior so BrainClaw exposes the expected memory tools
  and authoritative memory flow for OpenClaw sessions.
- Remove or downgrade claimed capabilities that are still placeholder-only until
  they are genuinely implemented.

### Phase 2: Portability and Environment Support

- Add failing tests that prove BrainClaw cannot assume `ajf-openclaw`-specific
  names, filesystem layouts, or agent identifiers.
- Refactor initialization, configuration, and identity routing so BrainClaw
  derives instance-specific details from supported OpenClaw inputs.
- Verify BrainClaw can initialize as a standard plugin install rather than only
  via a linked local source tree.

### Phase 3: Durable Memory Classes and Promotion Pipeline

- Implement or repair the canonical PostgreSQL-backed ingestion path for raw
  events, promoted memory items, provenance fields, lifecycle state, and memory
  classes.
- Implement selective promotion policy behavior that preserves raw history while
  governing durable promotion.
- Ensure decision, procedural, semantic, relational, episodic, and
  identity/governance memory classes are representable and queryable.

### Phase 4: Retrieval, Decisions, and Multi-Agent Semantics

- Verify and implement routing, identity, and retrieval behavior for
  single-agent operation.
- Verify and implement scoped memory behavior for multi-agent operation,
  including separation and permitted sharing semantics.
- Implement or repair intent-routed retrieval, decision recall, supersession
  chains, temporal reasoning, and evidence-bundle assembly.
- Verify graph and vector retrieval remain derived from canonical PostgreSQL
  history and can be rebuilt.

### Phase 5: Packaging and Installation

- Package BrainClaw as a real OpenClaw plugin install located in the OpenClaw
  plugin directory.
- Update OpenClaw plugin configuration safely so BrainClaw is recognized from
  the plugin folder without losing existing settings.

### Phase 6: Migration and Live Verification

- Preserve file-backed memory and current ControlUI settings.
- Verify migration or fallback paths without deleting current memory files.
- Run fresh build, tests, plugin inspection, and live `ajf-openclaw`
  verification before any completion claim.
- Include scripted verification that BrainClaw still behaves correctly when
  agent identifiers and install paths differ from the local default
  `ajf-openclaw` setup.
- Include validation that promoted memory provenance, decision memory,
  supersession, and rebuildability are real in the running system.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Parallel TypeScript and Python changes | The plugin boundary and backend gap are both real blockers | Fixing only one layer would leave BrainClaw non-authoritative |
| Dual install model during transition | Need canonical source repo plus real plugin-folder install | Directly editing only the installed copy would break maintainability and traceability |
