# Feature Specification: Authoritative OpenClaw Memory Backend

**Feature Branch**: `codex/001-authoritative-memory-backend`  
**Created**: 2026-03-18  
**Status**: Draft  
**Input**: User description: "Make BrainClaw the authoritative OpenClaw memory backend so users do not have to rely on OpenClaw's MEMORY.md file memory system." Plus the consolidated Hybrid GraphRAG requirements document provided on 2026-03-18.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authoritative Conversational Memory (Priority: P1)

An OpenClaw operator enables BrainClaw as the active memory backend and agents
use BrainClaw as the normal source of conversational memory during live
sessions, in either single-agent or multi-agent OpenClaw environments and
across differing OpenClaw instance layouts, without depending on injected
`MEMORY.md` content for standard memory recall, while durable memories preserve
provenance, lifecycle state, and the memory classes needed for decision,
procedural, semantic, relational, episodic, and identity recall.

**Why this priority**: This is the core value of BrainClaw. If BrainClaw cannot
act as the primary memory system, the rest of the GraphRAG capabilities are
secondary.

**Independent Test**: Configure BrainClaw as the active memory backend, run a
live agent session, store and retrieve memory, and confirm the session succeeds
without needing `MEMORY.md` as the primary recall path.

**Acceptance Scenarios**:

1. **Given** BrainClaw is selected as the active memory backend, **When** an
   agent stores and later recalls relevant memory during a live session,
   **Then** the recalled memory comes from BrainClaw and is available through
   the normal agent workflow.
2. **Given** BrainClaw is active and `MEMORY.md` still exists for migration or
   audit purposes, **When** the agent performs standard memory recall,
   **Then** `MEMORY.md` is not required as the primary memory source.
3. **Given** OpenClaw is configured for either a single-agent or multi-agent
   environment, **When** BrainClaw is the active memory backend, **Then** the
   memory behavior remains correct for that environment’s routing and access
   model.
4. **Given** an OpenClaw instance uses different agent names, IDs, plugin
   paths, or workspace/container layouts than `ajf-openclaw`, **When**
   BrainClaw is installed through supported plugin mechanisms, **Then** the
   same BrainClaw build operates through configuration and runtime discovery
   without instance-specific code changes.
5. **Given** a decision or durable preference has been promoted into BrainClaw,
   **When** an agent later asks what is currently true, **Then** BrainClaw
   returns the active memory with provenance, rationale, and supersession
   context instead of only raw conversation fragments.

---

### User Story 2 - Verifiable Advanced Memory Capabilities (Priority: P2)

An operator or maintainer can verify which BrainClaw capabilities are real,
active, and observable in the running OpenClaw deployment, including retrieval,
graph health, isolation, audit behavior, and any advanced reasoning features
advertised by the plugin.

**Why this priority**: Advanced GraphRAG value only matters if the running
system can prove the capability exists and is not a placeholder or stale claim.

**Independent Test**: Use documented checks against the running deployment to
confirm each advertised BrainClaw capability either operates successfully or is
explicitly marked incomplete, including canonical storage, promotion policy,
decision memory, provenance, supersession, and derived-index rebuildability.

**Acceptance Scenarios**:

1. **Given** BrainClaw is installed and active, **When** an operator checks the
   running plugin state, **Then** the operator can see which core and advanced
   capabilities are enabled, healthy, and verified.
2. **Given** a capability is incomplete or placeholder-only, **When** the
   operator reviews the deployment status, **Then** the capability is clearly
   represented as incomplete rather than presented as production-ready.
3. **Given** derived graph or vector state is rebuilt from PostgreSQL history,
   **When** the operator validates the rebuild process, **Then** the derived
   indexes can be recreated without losing canonical history or promoted-memory
   provenance.

---

### User Story 3 - Safe Migration Away from File-Backed Memory (Priority: P3)

An operator can migrate relevant file-backed memory into BrainClaw and retain a
documented rollback path, so the organization can reduce dependency on
`MEMORY.md` without losing important historical memory.

**Why this priority**: Migration matters after primary authority is proven, but
it is necessary for operational adoption and trust.

**Independent Test**: Import a representative file-backed memory set into
BrainClaw, verify the imported records are retrievable, and confirm rollback
instructions are available if the migration must be paused or reversed.

**Acceptance Scenarios**:

1. **Given** historical memory exists in file-backed form, **When** an operator
   runs the approved migration workflow, **Then** the targeted records are
   available in BrainClaw with visible migration results.
2. **Given** a migration issue is detected, **When** the operator follows the
   rollback or fallback procedure, **Then** service continuity is preserved and
   the operator understands the next safe step.

### Edge Cases

- What happens when BrainClaw is selected as active memory but a required
  storage dependency is unhealthy or unreachable?
- How does the system behave when switching between single-agent and multi-agent
  OpenClaw configurations?
- How does the system behave when deployed into an OpenClaw instance with
  different agent names, tenant identifiers, plugin install paths, or host
  mount layouts than the local `ajf-openclaw` environment?
- How does the system behave when low-confidence or contradicted material is
  present in canonical history but blocked from durable promotion?
- How are active, superseded, expired, and archived states exposed during
  decision recall and temporal queries?
- How does the system behave when migrated file-backed memory contains
  duplicates, contradictions, or malformed records?
- What happens when a capability is present in source code but absent from the
  built runtime or disabled in the live container?
- How does the system respond when identity or isolation checks fail during a
  cross-agent memory request?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: BrainClaw MUST serve as the primary memory source for supported
  OpenClaw agent sessions whenever it is selected as the active memory backend.
- **FR-002**: The system MUST provide a documented way for operators to verify
  the active memory backend and the status of BrainClaw’s advertised
  capabilities in the running deployment.
- **FR-003**: The system MUST distinguish clearly between complete capabilities
  and incomplete or placeholder capabilities in operator-facing status and
  release-readiness reporting.
- **FR-004**: The system MUST preserve secure agent and tenant memory boundaries
  during storage and retrieval.
- **FR-005**: The system MUST support migration of relevant file-backed memory
  into BrainClaw with visible success and exception reporting.
- **FR-006**: The system MUST provide a documented fallback or rollback path if
  BrainClaw cannot safely act as the active memory backend.
- **FR-007**: The system MUST allow operators to verify health for the core
  memory path, including storage readiness and retrieval readiness.
- **FR-008**: The system MUST keep repository claims, built plugin behavior, and
  live runtime behavior aligned enough for operators to determine the true
  delivery state.
- **FR-009**: BrainClaw MUST operate correctly in both single-agent and
  multi-agent OpenClaw configurations and environments.
- **FR-010**: In multi-agent configurations, the system MUST preserve the
  expected separation and sharing rules for agent-scoped, team-scoped, and
  tenant-scoped memory.
- **FR-011**: BrainClaw MUST NOT depend on hardcoded `ajf-openclaw` container
  names, local filesystem paths, agent names, agent IDs, or tenant labels to
  operate correctly.
- **FR-012**: BrainClaw MUST obtain instance-specific routing, identity,
  storage, and plugin-environment details from supported OpenClaw
  configuration, runtime discovery, or explicit operator inputs rather than
  instance-specific code branches.
- **FR-013**: BrainClaw MUST be installable and operable as a standard OpenClaw
  plugin in supported plugin directories or configured plugin load paths
  without requiring source-tree-only linkage.
- **FR-014**: PostgreSQL MUST be the canonical source of truth for raw events,
  promoted memory items, decision records, provenance, lifecycle state,
  visibility state, and retrieval logs.
- **FR-015**: Weaviate and Neo4j MUST be treated as derived indexes whose state
  can be rebuilt from canonical PostgreSQL history.
- **FR-016**: BrainClaw MUST support first-class memory classes for episodic,
  semantic, procedural, relational, decision, and identity/governance memory.
- **FR-017**: The system MUST implement selective promotion rules that preserve
  raw history losslessly while blocking low-confidence, contradicted, trivial,
  or otherwise low-value content from automatic durable promotion.
- **FR-018**: Durable promoted memory items MUST retain provenance including
  source session/message references, extraction metadata, confidence, memory
  class, visibility, lifecycle state, and user-confirmation state.
- **FR-019**: Decision memory MUST store at minimum the decision summary,
  rationale, alternatives considered, current status, supporting evidence,
  topic/domain, timestamps, provenance, and supersession links.
- **FR-020**: Supersession MUST preserve historical chains without overwriting
  prior memory records, including replacement reason and effective timing.
- **FR-021**: Retrieval MUST be intent-routed and policy-based, choosing among
  lexical, semantic, graph, temporal, and decision-oriented retrieval paths as
  appropriate to the query.
- **FR-022**: Query results MUST assemble an evidence bundle with provenance
  sufficient to explain why the answer was returned and how much it should be
  trusted.
- **FR-023**: Memory records MUST support lifecycle states for created, active,
  superseded, expired, and archived behavior where applicable.
- **FR-024**: BrainClaw MUST support rebuild or reindex workflows for derived
  vector and graph stores without loss of canonical PostgreSQL history.
- **FR-025**: Release-readiness verification MUST cover promotion rules,
  contradiction blocking, provenance presence, decision correctness,
  supersession chains, retrieval quality, procedural recall, identity memory,
  end-to-end recall behavior, and rebuildability.

### Key Entities *(include if feature involves data)*

- **Memory Record**: A unit of conversational or operational memory that can be
  stored, retrieved, migrated, and attributed to an agent, team, or tenant.
- **Decision Record**: A durable memory item that captures a current or former
  decision, its rationale, alternatives, supporting evidence, and current
  lifecycle/supersession state.
- **Capability Status**: A representation of whether a BrainClaw feature is
  active, healthy, verified, incomplete, or unavailable in the running system.
- **Migration Result**: A summary of which memory records were imported,
  skipped, rejected, or require operator review during migration.
- **Isolation Policy**: The rules that determine which agent or tenant may
  access a given memory record.
- **Promotion Policy State**: The metadata that records confidence,
  confirmation, contradiction, repetition, and other signals used to decide
  whether raw history becomes durable memory.
- **Provenance Bundle**: The fields that tie a promoted memory or answer back
  to source sessions, messages, extraction logic, and confidence/trust signals.
- **Supersession Link**: A structured relation between prior and current memory
  records that preserves what changed, when, and why.

## Assumptions

- `MEMORY.md` may remain present during a transition period, but it is treated
  as migration or fallback material rather than the intended primary memory
  source.
- The target environment for acceptance is the running `ajf-openclaw`
  deployment that serves `http://localhost:3000/`, but implementation choices
  must remain portable to other supported OpenClaw instances.
- Lossless Context Management and existing file-backed memory artifacts remain
  valuable source material, but they are not sufficient as the long-term
  authoritative durable-memory layer.
- Operators prefer an explicit, evidence-based status over optimistic feature
  claims.
- Single-agent and multi-agent support share one canonical BrainClaw codebase
  and differ by configuration, routing, and policy behavior rather than by
  separate plugin builds.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the target deployment, 100% of verified primary memory recall
  flows for supported BrainClaw-enabled agent sessions succeed without requiring
  `MEMORY.md` as the normal primary recall source.
- **SC-002**: An operator can determine the active memory backend, capability
  status, and core health state of BrainClaw within 5 minutes using documented
  checks.
- **SC-003**: At least 99% of targeted file-backed memory records selected for a
  migration run are imported successfully or reported with an explicit reason
  for non-import.
- **SC-004**: No capability presented as complete in the running deployment
  remains placeholder-only during release-readiness review.
- **SC-005**: Verified acceptance checks pass for both a single-agent and a
  multi-agent OpenClaw configuration without data loss or isolation regression.
- **SC-006**: Automated or scripted verification demonstrates that BrainClaw
  does not rely on `ajf-openclaw`-specific container names, filesystem paths,
  or agent identifiers to initialize, route memory operations, and expose its
  plugin contract.
- **SC-007**: In the acceptance dataset, 100% of durable promoted memory items
  sampled during validation include the required provenance, confidence, and
  lifecycle fields.
- **SC-008**: Decision-recall validation returns the currently active decision
  with rationale and supersession context for the benchmark decision prompts
  chosen during implementation.
- **SC-009**: A documented rebuild or reindex validation proves that derived
  vector and graph stores can be recreated from PostgreSQL-backed canonical
  history without losing historical memory records.
