<!--
Sync Impact Report
Version change: 1.1.0 -> 1.2.0
Modified principles:
- Added canonical PostgreSQL ledger principle
Added sections:
- None
Removed sections:
- None
Templates requiring updates:
- ✅ reviewed: .specify/templates/plan-template.md (no change required)
- ✅ reviewed: .specify/templates/spec-template.md (no change required)
- ✅ updated: .specify/templates/tasks-template.md
Deferred follow-up TODOs:
- None
-->
# BrainClaw Constitution

## Core Principles

### I. Memory Backend Authority
BrainClaw MUST function as the authoritative memory backend for OpenClaw when
selected in the memory slot. `MEMORY.md` and other file-backed memory artifacts
MAY exist for migration, audit, or rollback, but they MUST NOT remain the
primary memory source for normal production retrieval once BrainClaw is claimed
as active. Any work that preserves file-based memory as the dominant source MUST
be described as transitional, not complete.

### II. Canonical PostgreSQL Ledger
PostgreSQL MUST remain the authoritative memory ledger for BrainClaw raw events,
promoted memory items, decision records, provenance, lifecycle state,
visibility, and retrieval history. Weaviate and Neo4j MAY provide derived
semantic and graph indexes, but they MUST remain rebuildable from PostgreSQL
history. No feature MAY require vector or graph state to be the sole surviving
source of truth.

### III. Contract Parity Before Capability Claims
BrainClaw MUST satisfy the user-visible responsibilities expected from an
OpenClaw memory plugin before advanced GraphRAG features are declared complete.
Search, retrieval, provenance, memory accessibility, migration behavior, and
operator workflows MUST work coherently end to end. Placeholder, mocked, or
log-only behaviors MUST NOT be represented as shipped capabilities.

### IV. Evidence-First Verification
Every behavior-changing change MUST begin with failing automated coverage where a
practical harness exists. When a full automated harness does not exist, the work
MUST define explicit runtime probes against the live `ajf-openclaw` deployment.
Claims of completion require evidence from the running plugin, not only source
inspection or static reasoning.

### V. Secure Multi-Agent Isolation
Agent identity, tenant boundaries, authorization rules, secret handling, and
auditability are non-negotiable. BrainClaw MUST fail closed when identity or
storage security guarantees cannot be enforced. Multi-agent memory access MUST
be explicit, policy-driven, and observable, with no silent bypasses that weaken
isolation in the name of convenience.

### VI. Operational Truth Over Marketing
The GitHub repository, local working tree, built runtime bundle, and live
container behavior MUST be reconcilable. If those states diverge, the mismatch
is a delivery risk that MUST be documented and resolved before any "production
ready", "top-tier", or "comprehensive" claim is accepted. Runtime logs,
documented health checks, and measurable acceptance criteria outrank narrative
descriptions.

### VII. Portable OpenClaw Compatibility
BrainClaw MUST remain portable across supported OpenClaw instances and MUST NOT
depend on `ajf-openclaw`-specific container names, host mount paths, agent
names, agent IDs, tenant labels, or local developer filesystem layouts. The
same BrainClaw build MUST adapt through OpenClaw configuration, runtime
discovery, and explicit policy inputs rather than instance-specific hardcoding.
The `ajf-openclaw` deployment MAY be used as the primary verification
environment, but it MUST NOT become the product contract.

## Delivery Boundaries

BrainClaw work MUST preserve clear boundaries between:

- The TypeScript OpenClaw plugin surface
- The Python memory backend and storage orchestration
- The canonical PostgreSQL ledger and rebuildable derived indexes
- Migration pathways from file-backed memory artifacts
- Runtime verification in the `ajf-openclaw` container
- Portable compatibility with standard OpenClaw plugin discovery and runtime
  configuration

Every substantial feature specification MUST explicitly cover:

- Authoritative memory behavior when BrainClaw is selected
- Migration and rollback expectations
- Security and isolation expectations
- Observability and operator verification steps
- Acceptance criteria for any advertised advanced capability
- Instance-agnostic configuration and discovery behavior
- Canonical raw storage, promotion policy, provenance, and supersession behavior

## Workflow & Release Gates

Substantial BrainClaw work MUST follow the Spec Kit flow:

1. Constitution
2. Specification
3. Clarification when ambiguity materially affects scope, safety, or operator
   experience
4. Plan
5. Tasks
6. Analysis and checklist validation
7. Implementation

Release readiness requires all of the following:

- Automated tests or justified runtime probes exist for changed behavior
- Live verification is performed against the running `ajf-openclaw` plugin path
- The implementation remains instance-agnostic and does not encode
  `ajf-openclaw`-specific names, IDs, or filesystem assumptions
- Migration behavior and fallback behavior are documented
- Rebuildability of derived vector and graph indexes from PostgreSQL is
  demonstrated or explicitly probed
- Security-sensitive behavior is reviewed for isolation and data exposure risks
- No placeholder-only capability remains listed as complete in release-facing
  descriptions

## Governance

This constitution supersedes README marketing language, status assertions, and
informal delivery claims for BrainClaw. Amendments require updating this file,
reviewing dependent Spec Kit templates, and recording the correct semantic
version bump. Compliance review is mandatory during planning and before any work
is reported complete. Constitution violations that affect correctness, security,
or operational truth block completion until resolved or explicitly waived by the
project owner.

**Version**: 1.2.0 | **Ratified**: 2026-03-18 | **Last Amended**: 2026-03-18
