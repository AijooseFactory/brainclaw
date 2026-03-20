import { html, nothing } from "lit";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import { clampText, formatRelativeTimestamp } from "../format.ts";
import { icons } from "../icons.ts";
import { toSanitizedMarkdownHtml } from "../markdown.ts";
import {
  formatCronPayload,
  formatCronSchedule,
  formatCronState,
  formatNextRun,
} from "../presenter.ts";
import type {
  AgentFileEntry,
  AgentsBrainClawMemoryRecord,
  AgentsFilesListResult,
  ChannelAccountSnapshot,
  ChannelsStatusSnapshot,
  CronJob,
  CronStatus,
} from "../types.ts";
import { formatBytes, type AgentContext } from "./agents-utils.ts";
import { resolveChannelExtras as resolveChannelExtrasFromConfig } from "./channel-config-extras.ts";

function renderAgentContextCard(context: AgentContext, subtitle: string) {
  return html`
    <section class="card">
      <div class="card-title">Agent Context</div>
      <div class="card-sub">${subtitle}</div>
      <div class="agents-overview-grid" style="margin-top: 16px;">
        <div class="agent-kv">
          <div class="label">Workspace</div>
          <div class="mono">${context.workspace}</div>
        </div>
        <div class="agent-kv">
          <div class="label">Primary Model</div>
          <div class="mono">${context.model}</div>
        </div>
        <div class="agent-kv">
          <div class="label">Identity Name</div>
          <div>${context.identityName}</div>
        </div>
        <div class="agent-kv">
          <div class="label">Identity Avatar</div>
          <div>${context.identityAvatar}</div>
        </div>
        <div class="agent-kv">
          <div class="label">Skills Filter</div>
          <div>${context.skillsLabel}</div>
        </div>
        <div class="agent-kv">
          <div class="label">Default</div>
          <div>${context.isDefault ? "yes" : "no"}</div>
        </div>
      </div>
    </section>
  `;
}

type ChannelSummaryEntry = {
  id: string;
  label: string;
  accounts: ChannelAccountSnapshot[];
};

const DEFAULT_AGENT_MEMORY_FILENAME = "MEMORY.md";
const DEFAULT_AGENT_MEMORY_ALT_FILENAME = "memory.md";

function resolveChannelLabel(snapshot: ChannelsStatusSnapshot, id: string) {
  const meta = snapshot.channelMeta?.find((entry) => entry.id === id);
  if (meta?.label) {
    return meta.label;
  }
  return snapshot.channelLabels?.[id] ?? id;
}

function resolveChannelEntries(snapshot: ChannelsStatusSnapshot | null): ChannelSummaryEntry[] {
  if (!snapshot) {
    return [];
  }
  const ids = new Set<string>();
  for (const id of snapshot.channelOrder ?? []) {
    ids.add(id);
  }
  for (const entry of snapshot.channelMeta ?? []) {
    ids.add(entry.id);
  }
  for (const id of Object.keys(snapshot.channelAccounts ?? {})) {
    ids.add(id);
  }
  const ordered: string[] = [];
  const seed = snapshot.channelOrder?.length ? snapshot.channelOrder : Array.from(ids);
  for (const id of seed) {
    if (!ids.has(id)) {
      continue;
    }
    ordered.push(id);
    ids.delete(id);
  }
  for (const id of ids) {
    ordered.push(id);
  }
  return ordered.map((id) => ({
    id,
    label: resolveChannelLabel(snapshot, id),
    accounts: snapshot.channelAccounts?.[id] ?? [],
  }));
}

const CHANNEL_EXTRA_FIELDS = ["groupPolicy", "streamMode", "dmPolicy"] as const;

function summarizeChannelAccounts(accounts: ChannelAccountSnapshot[]) {
  let connected = 0;
  let configured = 0;
  let enabled = 0;
  for (const account of accounts) {
    const probeOk =
      account.probe && typeof account.probe === "object" && "ok" in account.probe
        ? Boolean((account.probe as { ok?: unknown }).ok)
        : false;
    const isConnected = account.connected === true || account.running === true || probeOk;
    if (isConnected) {
      connected += 1;
    }
    if (account.configured) {
      configured += 1;
    }
    if (account.enabled) {
      enabled += 1;
    }
  }
  return {
    total: accounts.length,
    connected,
    configured,
    enabled,
  };
}

export function renderAgentChannels(params: {
  context: AgentContext;
  configForm: Record<string, unknown> | null;
  snapshot: ChannelsStatusSnapshot | null;
  loading: boolean;
  error: string | null;
  lastSuccess: number | null;
  onRefresh: () => void;
}) {
  const entries = resolveChannelEntries(params.snapshot);
  const lastSuccessLabel = params.lastSuccess
    ? formatRelativeTimestamp(params.lastSuccess)
    : "never";
  return html`
    <section class="grid grid-cols-2">
      ${renderAgentContextCard(params.context, "Workspace, identity, and model configuration.")}
      <section class="card">
        <div class="row" style="justify-content: space-between;">
          <div>
            <div class="card-title">Channels</div>
            <div class="card-sub">Gateway-wide channel status snapshot.</div>
          </div>
          <button class="btn btn--sm" ?disabled=${params.loading} @click=${params.onRefresh}>
            ${params.loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <div class="muted" style="margin-top: 8px;">
          Last refresh: ${lastSuccessLabel}
        </div>
        ${
          params.error
            ? html`<div class="callout danger" style="margin-top: 12px;">${params.error}</div>`
            : nothing
        }
        ${
          !params.snapshot
            ? html`
                <div class="callout info" style="margin-top: 12px">Load channels to see live status.</div>
              `
            : nothing
        }
        ${
          entries.length === 0
            ? html`
                <div class="muted" style="margin-top: 16px">No channels found.</div>
              `
            : html`
                <div class="list" style="margin-top: 16px;">
                  ${entries.map((entry) => {
                    const summary = summarizeChannelAccounts(entry.accounts);
                    const status = summary.total
                      ? `${summary.connected}/${summary.total} connected`
                      : "no accounts";
                    const configLabel = summary.configured
                      ? `${summary.configured} configured`
                      : "not configured";
                    const enabled = summary.total ? `${summary.enabled} enabled` : "disabled";
                    const extras = resolveChannelExtrasFromConfig({
                      configForm: params.configForm,
                      channelId: entry.id,
                      fields: CHANNEL_EXTRA_FIELDS,
                    });
                    return html`
                      <div class="list-item">
                        <div class="list-main">
                          <div class="list-title">${entry.label}</div>
                          <div class="list-sub mono">${entry.id}</div>
                        </div>
                        <div class="list-meta">
                          <div>${status}</div>
                          <div>${configLabel}</div>
                          <div>${enabled}</div>
                          ${
                            summary.configured === 0
                              ? html`
                                  <div>
                                    <a
                                      href="https://docs.openclaw.ai/channels"
                                      target="_blank"
                                      rel="noopener"
                                      style="color: var(--accent); font-size: 12px"
                                      >Setup guide</a
                                    >
                                  </div>
                                `
                              : nothing
                          }
                          ${
                            extras.length > 0
                              ? extras.map(
                                  (extra) => html`<div>${extra.label}: ${extra.value}</div>`,
                                )
                              : nothing
                          }
                        </div>
                      </div>
                    `;
                  })}
                </div>
              `
        }
      </section>
    </section>
  `;
}

export function renderAgentCron(params: {
  context: AgentContext;
  agentId: string;
  jobs: CronJob[];
  status: CronStatus | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onRunNow: (jobId: string) => void;
}) {
  const jobs = params.jobs.filter((job) => job.agentId === params.agentId);
  return html`
    <section class="grid grid-cols-2">
      ${renderAgentContextCard(params.context, "Workspace and scheduling targets.")}
      <section class="card">
        <div class="row" style="justify-content: space-between;">
          <div>
            <div class="card-title">Scheduler</div>
            <div class="card-sub">Gateway cron status.</div>
          </div>
          <button class="btn btn--sm" ?disabled=${params.loading} @click=${params.onRefresh}>
            ${params.loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <div class="stat-grid" style="margin-top: 16px;">
          <div class="stat">
            <div class="stat-label">Enabled</div>
            <div class="stat-value">
              ${params.status ? (params.status.enabled ? "Yes" : "No") : "n/a"}
            </div>
          </div>
          <div class="stat">
            <div class="stat-label">Jobs</div>
            <div class="stat-value">${params.status?.jobs ?? "n/a"}</div>
          </div>
          <div class="stat">
            <div class="stat-label">Next wake</div>
            <div class="stat-value">${formatNextRun(params.status?.nextWakeAtMs ?? null)}</div>
          </div>
        </div>
        ${
          params.error
            ? html`<div class="callout danger" style="margin-top: 12px;">${params.error}</div>`
            : nothing
        }
      </section>
    </section>
    <section class="card">
      <div class="card-title">Agent Cron Jobs</div>
      <div class="card-sub">Scheduled jobs targeting this agent.</div>
      ${
        jobs.length === 0
          ? html`
              <div class="muted" style="margin-top: 16px">No jobs assigned.</div>
            `
          : html`
              <div class="list" style="margin-top: 16px;">
                ${jobs.map(
                  (job) => html`
                    <div class="list-item">
                      <div class="list-main">
                        <div class="list-title">${job.name}</div>
                        ${
                          job.description
                            ? html`<div class="list-sub">${job.description}</div>`
                            : nothing
                        }
                        <div class="chip-row" style="margin-top: 6px;">
                          <span class="chip">${formatCronSchedule(job)}</span>
                          <span class="chip ${job.enabled ? "chip-ok" : "chip-warn"}">
                            ${job.enabled ? "enabled" : "disabled"}
                          </span>
                          <span class="chip">${job.sessionTarget}</span>
                        </div>
                      </div>
                      <div class="list-meta">
                        <div class="mono">${formatCronState(job)}</div>
                        <div class="muted">${formatCronPayload(job)}</div>
                        <button
                          class="btn btn--sm"
                          style="margin-top: 6px;"
                          ?disabled=${!job.enabled}
                          @click=${() => params.onRunNow(job.id)}
                        >Run Now</button>
                      </div>
                    </div>
                  `,
                )}
              </div>
            `
      }
    </section>
  `;
}

export function renderAgentFiles(params: {
  agentId: string;
  agentFilesList: AgentsFilesListResult | null;
  agentFilesLoading: boolean;
  agentFilesError: string | null;
  agentFileActive: string | null;
  agentFileContents: Record<string, string>;
  agentFileDrafts: Record<string, string>;
  agentFileSaving: boolean;
  onLoadFiles: (agentId: string) => void;
  onSelectFile: (name: string) => void;
  onFileDraftChange: (name: string, content: string) => void;
  onFileReset: (name: string) => void;
  onFileSave: (name: string) => void;
}) {
  return renderAgentFilePanel({
    ...params,
    title: "Core Files",
    subtitle: "Bootstrap persona, identity, and tool guidance.",
    loadMessage: "Load the agent workspace files to edit core instructions.",
    emptyEditorMessage: "Select a file to edit.",
    selectFiles: (list) => list.files,
  });
}

export function renderAgentMemory(params: {
  agentMemory: {
    view: "file" | "brainclaw";
    listLoading: boolean;
    listError: string | null;
    list: {
      agentId: string;
      total: number;
      filtered: number;
      knowledge: number;
      conversation: number;
      page: number;
      pageSize: number;
      pageCount: number;
      items: AgentsBrainClawMemoryRecord[];
    } | null;
    selectedId: string | null;
    draft: string;
    saving: boolean;
    query: string;
    memoryClass: string;
    limit: number;
    includeSuperseded: boolean;
  };
  agentId: string;
  agentFilesList: AgentsFilesListResult | null;
  agentFilesLoading: boolean;
  agentFilesError: string | null;
  agentFileActive: string | null;
  agentFileContents: Record<string, string>;
  agentFileDrafts: Record<string, string>;
  agentFileSaving: boolean;
  onLoadFiles: (agentId: string) => void;
  onSelectFile: (name: string) => void;
  onFileDraftChange: (name: string, content: string) => void;
  onFileReset: (name: string) => void;
  onFileSave: (name: string) => void;
  onSelectMemoryView: (view: "file" | "brainclaw") => void;
  onBrainClawMemoryRefresh: (page?: number) => void;
  onBrainClawMemorySelect: (memoryId: string) => void;
  onBrainClawMemoryDraftChange: (content: string) => void;
  onBrainClawMemoryReset: () => void;
  onBrainClawMemorySave: () => void;
  onBrainClawMemoryQueryChange: (next: string) => void;
  onBrainClawMemoryClassChange: (next: string) => void;
  onBrainClawMemoryLimitChange: (next: number) => void;
  onBrainClawMemoryIncludeSupersededChange: (next: boolean) => void;
}) {
  return html`
    <section class="card">
      <div>
        <div class="card-title">Agent Memory</div>
        <div class="card-sub">
          Manage the agent’s root memory file and canonical BrainClaw Hybrid GraphRAG memory entries.
        </div>
      </div>
      <div
        style="display: grid; grid-template-columns: minmax(180px, 220px) minmax(0, 1fr); gap: 16px; margin-top: 16px;"
      >
        <section class="card" style="padding: 0; align-self: start;">
          ${renderMemoryWorkspaceNav({
            activeView: params.agentMemory.view,
            onSelectMemoryView: params.onSelectMemoryView,
          })}
        </section>
        <div>
          ${
            params.agentMemory.view === "brainclaw"
              ? renderBrainClawMemoryManager({
                  agentId: params.agentId,
                  agentMemory: params.agentMemory,
                  onBrainClawMemoryRefresh: params.onBrainClawMemoryRefresh,
                  onBrainClawMemorySelect: params.onBrainClawMemorySelect,
                  onBrainClawMemoryDraftChange: params.onBrainClawMemoryDraftChange,
                  onBrainClawMemoryReset: params.onBrainClawMemoryReset,
                  onBrainClawMemorySave: params.onBrainClawMemorySave,
                  onBrainClawMemoryQueryChange: params.onBrainClawMemoryQueryChange,
                  onBrainClawMemoryClassChange: params.onBrainClawMemoryClassChange,
                  onBrainClawMemoryLimitChange: params.onBrainClawMemoryLimitChange,
                  onBrainClawMemoryIncludeSupersededChange:
                    params.onBrainClawMemoryIncludeSupersededChange,
                })
              : renderAgentFilePanel({
                  ...params,
                  title: "MEMORY.md",
                  subtitle:
                    "Edit the agent’s root memory file shared with the Files view and synchronized as the BrainClaw backup mirror.",
                  loadMessage: "Load the agent workspace to view and edit its MEMORY.md file.",
                  emptyEditorMessage: "No agent memory file available.",
                  selectFiles: resolveAgentMemoryFiles,
                  hideFileListWhenSingleFile: true,
                })
          }
        </div>
      </div>
    </section>
  `;
}

function renderAgentFilePanel(params: {
  agentId: string;
  agentFilesList: AgentsFilesListResult | null;
  agentFilesLoading: boolean;
  agentFilesError: string | null;
  agentFileActive: string | null;
  agentFileContents: Record<string, string>;
  agentFileDrafts: Record<string, string>;
  agentFileSaving: boolean;
  onLoadFiles: (agentId: string) => void;
  onSelectFile: (name: string) => void;
  onFileDraftChange: (name: string, content: string) => void;
  onFileReset: (name: string) => void;
  onFileSave: (name: string) => void;
  title: string;
  subtitle: string;
  loadMessage: string;
  emptyEditorMessage: string;
  selectFiles: (list: AgentsFilesListResult) => AgentFileEntry[];
  hideFileListWhenSingleFile?: boolean;
}) {
  const list = params.agentFilesList?.agentId === params.agentId ? params.agentFilesList : null;
  const files = list ? params.selectFiles(list) : [];
  const active = params.agentFileActive ?? null;
  const activeEntry = active ? (files.find((file) => file.name === active) ?? null) : null;
  const baseContent = active ? (params.agentFileContents[active] ?? "") : "";
  const draft = active ? (params.agentFileDrafts[active] ?? baseContent) : "";
  const isDirty = active ? draft !== baseContent : false;
  const showFileList = !(params.hideFileListWhenSingleFile && files.length <= 1);

  return html`
    <section class="card">
      <div class="row" style="justify-content: space-between;">
        <div>
          <div class="card-title">${params.title}</div>
          <div class="card-sub">${params.subtitle}</div>
        </div>
        <button
          class="btn btn--sm"
          ?disabled=${params.agentFilesLoading}
          @click=${() => params.onLoadFiles(params.agentId)}
        >
          ${params.agentFilesLoading ? "Loading…" : "Refresh"}
        </button>
      </div>
      ${
        list
          ? html`<div class="muted mono" style="margin-top: 8px;">Workspace: ${list.workspace}</div>`
          : nothing
      }
      ${
        params.agentFilesError
          ? html`<div class="callout danger" style="margin-top: 12px;">${params.agentFilesError}</div>`
          : nothing
      }
      ${
        !list
          ? html`
              <div class="callout info" style="margin-top: 12px">
                ${params.loadMessage}
              </div>
            `
          : html`
              <div class=${showFileList ? "agent-files-grid" : ""} style="margin-top: 16px;">
                ${
                  showFileList
                    ? html`
                        <div class="agent-files-list">
                          ${
                            files.length === 0
                              ? html`
                                  <div class="muted">No files found.</div>
                                `
                              : files.map((file) =>
                                  renderAgentFileRow(file, active, () =>
                                    params.onSelectFile(file.name),
                                  ),
                                )
                          }
                        </div>
                      `
                    : nothing
                }
                <div class=${showFileList ? "agent-files-editor" : ""}>
                  ${
                    !activeEntry
                      ? html`
                          <div class="muted">${params.emptyEditorMessage}</div>
                        `
                      : html`
                          <div class="agent-file-header">
                            <div>
                              <div class="agent-file-title mono">${activeEntry.name}</div>
                              <div class="agent-file-sub mono">${activeEntry.path}</div>
                            </div>
                            <div class="agent-file-actions">
                              <button
                                class="btn btn--sm"
                                title="Preview rendered markdown"
                                @click=${(e: Event) => {
                                  const btn = e.currentTarget as HTMLElement;
                                  const dialog = btn
                                    .closest(".agent-files-editor")
                                    ?.querySelector("dialog");
                                  if (dialog) {
                                    dialog.showModal();
                                  }
                                }}
                              >
                                ${icons.eye} Preview
                              </button>
                              <button
                                class="btn btn--sm"
                                ?disabled=${!isDirty}
                                @click=${() => params.onFileReset(activeEntry.name)}
                              >
                                Reset
                              </button>
                              <button
                                class="btn btn--sm primary"
                                ?disabled=${params.agentFileSaving || !isDirty}
                                @click=${() => params.onFileSave(activeEntry.name)}
                              >
                                ${params.agentFileSaving ? "Saving…" : "Save"}
                              </button>
                            </div>
                          </div>
                          ${
                            activeEntry.missing
                              ? html`
                                  <div class="callout info" style="margin-top: 10px">
                                    This file is missing. Saving will create it in the agent workspace.
                                  </div>
                                `
                              : nothing
                          }
                          <label class="field agent-file-field" style="margin-top: 12px;">
                            <span>Content</span>
                            <textarea
                              class="agent-file-textarea"
                              .value=${draft}
                              @input=${(e: Event) =>
                                params.onFileDraftChange(
                                  activeEntry.name,
                                  (e.target as HTMLTextAreaElement).value,
                                )}
                            ></textarea>
                          </label>
                          <dialog
                            class="md-preview-dialog"
                            @click=${(e: Event) => {
                              const dialog = e.currentTarget as HTMLDialogElement;
                              if (e.target === dialog) {
                                dialog.close();
                              }
                            }}
                          >
                            <div class="md-preview-dialog__panel">
                              <div class="md-preview-dialog__header">
                                <div class="md-preview-dialog__title mono">${activeEntry.name}</div>
                                <button
                                  class="btn btn--sm"
                                  @click=${(e: Event) => {
                                    (e.currentTarget as HTMLElement).closest("dialog")?.close();
                                  }}
                                >${icons.x} Close</button>
                              </div>
                              <div class="md-preview-dialog__body sidebar-markdown">
                                ${unsafeHTML(toSanitizedMarkdownHtml(draft))}
                              </div>
                            </div>
                          </dialog>
                        `
                  }
                </div>
              </div>
            `
      }
    </section>
  `;
}

function resolveAgentMemoryFiles(list: AgentsFilesListResult): AgentFileEntry[] {
  const primary = list.files.find((file) => file.name === DEFAULT_AGENT_MEMORY_FILENAME);
  if (primary) {
    return [primary];
  }
  const fallback = list.files.find((file) => file.name === DEFAULT_AGENT_MEMORY_ALT_FILENAME);
  if (fallback) {
    return [fallback];
  }
  return [
    {
      name: DEFAULT_AGENT_MEMORY_FILENAME,
      path: joinWorkspacePath(list.workspace, DEFAULT_AGENT_MEMORY_FILENAME),
      missing: true,
      size: 0,
    },
  ];
}

function joinWorkspacePath(workspace: string, name: string) {
  return workspace.endsWith("/") ? `${workspace}${name}` : `${workspace}/${name}`;
}

function renderMemoryWorkspaceNav(params: {
  activeView: "file" | "brainclaw";
  onSelectMemoryView: (view: "file" | "brainclaw") => void;
}) {
  return html`
    <button
      type="button"
      class="agent-file-row ${params.activeView === "file" ? "active" : ""}"
      @click=${() => params.onSelectMemoryView("file")}
    >
      <div>
        <div class="agent-file-name mono">MEMORY.md</div>
        <div class="agent-file-meta">Shared file editor</div>
      </div>
    </button>
    <button
      type="button"
      class="agent-file-row ${params.activeView === "brainclaw" ? "active" : ""}"
      @click=${() => params.onSelectMemoryView("brainclaw")}
    >
      <div>
        <div class="agent-file-name">BrainClaw Memory</div>
        <div class="agent-file-meta">Canonical Hybrid GraphRAG memory</div>
      </div>
    </button>
  `;
}

function parseIsoTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function resolveMemoryConfidence(record: AgentsBrainClawMemoryRecord): number | null {
  const metadataConfidence = record.metadata?.["confidence"];
  if (typeof metadataConfidence === "number" && Number.isFinite(metadataConfidence)) {
    return metadataConfidence;
  }
  const provenanceConfidence = record.provenance?.["extraction_confidence"];
  if (typeof provenanceConfidence === "number" && Number.isFinite(provenanceConfidence)) {
    return provenanceConfidence;
  }
  return null;
}

function renderBrainClawMemoryManager(params: {
  agentId: string;
  agentMemory: {
    listLoading: boolean;
    listError: string | null;
    list: {
      agentId: string;
      total: number;
      filtered: number;
      knowledge: number;
      conversation: number;
      page: number;
      pageSize: number;
      pageCount: number;
      items: AgentsBrainClawMemoryRecord[];
    } | null;
    selectedId: string | null;
    draft: string;
    saving: boolean;
    query: string;
    memoryClass: string;
    limit: number;
    includeSuperseded: boolean;
  };
  onBrainClawMemoryRefresh: (page?: number) => void;
  onBrainClawMemorySelect: (memoryId: string) => void;
  onBrainClawMemoryDraftChange: (content: string) => void;
  onBrainClawMemoryReset: () => void;
  onBrainClawMemorySave: () => void;
  onBrainClawMemoryQueryChange: (next: string) => void;
  onBrainClawMemoryClassChange: (next: string) => void;
  onBrainClawMemoryLimitChange: (next: number) => void;
  onBrainClawMemoryIncludeSupersededChange: (next: boolean) => void;
}) {
  const list = params.agentMemory.list?.agentId === params.agentId ? params.agentMemory.list : null;
  const selected =
    list?.items.find((item) => item.id === params.agentMemory.selectedId) ?? list?.items[0] ?? null;
  const selectedBaseContent = selected?.content ?? "";
  const isDirty = selected ? params.agentMemory.draft !== selectedBaseContent : false;
  const pageCount = Math.max(list?.pageCount ?? 0, 1);
  const page = Math.min(list?.page ?? 1, pageCount);

  return html`
    <section class="card">
      <div class="row" style="justify-content: space-between; align-items: start;">
        <div>
          <div class="card-title">BrainClaw Memory</div>
          <div class="card-sub">
            Canonical Hybrid GraphRAG memory for this agent. Edits supersede the current PostgreSQL
            memory item, rewrite the synchronized <code>MEMORY.md</code> backup mirror, and mark derived
            stores for resync.
          </div>
        </div>
        <button
          class="btn btn--sm"
          ?disabled=${params.agentMemory.listLoading}
          @click=${() => params.onBrainClawMemoryRefresh()}
        >
          ${params.agentMemory.listLoading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <div class="muted" style="margin-top: 8px;">
        Canonical store: PostgreSQL. Backup mirror: MEMORY.md. Derived stores: Weaviate + Neo4j.
      </div>
      ${
        params.agentMemory.listError
          ? html`<div class="callout danger" style="margin-top: 12px;">${params.agentMemory.listError}</div>`
          : nothing
      }
      <section class="card" style="margin-top: 16px; background: var(--panel-2, transparent);">
        <div
          style="display: grid; grid-template-columns: minmax(220px, 2fr) repeat(3, minmax(120px, 1fr)); gap: 12px; align-items: end;"
        >
          <label class="field">
            <span>Search</span>
            <input
              class="input"
              type="text"
              placeholder="Search BrainClaw memory content..."
              .value=${params.agentMemory.query}
              @input=${(e: Event) =>
                params.onBrainClawMemoryQueryChange((e.target as HTMLInputElement).value)}
            />
          </label>
          <label class="field">
            <span>Area</span>
            <select
              class="input"
              .value=${params.agentMemory.memoryClass}
              @change=${(e: Event) =>
                params.onBrainClawMemoryClassChange((e.target as HTMLSelectElement).value)}
            >
              ${[
                ["all", "All Areas"],
                ["knowledge", "Knowledge"],
                ["conversation", "Conversation"],
                ["identity", "Identity"],
                ["semantic", "Semantic"],
                ["relational", "Relational"],
                ["decision", "Decision"],
                ["procedural", "Procedural"],
                ["episodic", "Episodic"],
                ["summary", "Summary"],
              ].map(
                ([value, label]) => html`<option value=${value} ?selected=${params.agentMemory.memoryClass === value}>${label}</option>`,
              )}
            </select>
          </label>
          <label class="field">
            <span>Limit</span>
            <select
              class="input"
              .value=${String(params.agentMemory.limit)}
              @change=${(e: Event) =>
                params.onBrainClawMemoryLimitChange(
                  Number((e.target as HTMLSelectElement).value) || 25,
                )}
            >
              ${[10, 25, 50, 100].map(
                (value) =>
                  html`<option value=${String(value)} ?selected=${params.agentMemory.limit === value}
                    >${value}</option
                  >`,
              )}
            </select>
          </label>
          <div class="field">
            <span>Threshold</span>
            <div class="input" style="display: flex; align-items: center;">0.60</div>
          </div>
        </div>
        <div class="row" style="justify-content: space-between; margin-top: 12px; gap: 12px;">
          <label class="row" style="gap: 8px; align-items: center;">
            <input
              type="checkbox"
              .checked=${params.agentMemory.includeSuperseded}
              @change=${(e: Event) =>
                params.onBrainClawMemoryIncludeSupersededChange(
                  (e.target as HTMLInputElement).checked,
                )}
            />
            <span>Include superseded versions</span>
          </label>
          <div class="row" style="gap: 8px;">
            <button class="btn btn--sm" @click=${() => params.onBrainClawMemoryRefresh(1)}>
              Search
            </button>
            <button
              class="btn btn--sm"
              @click=${() => {
                params.onBrainClawMemoryQueryChange("");
                params.onBrainClawMemoryClassChange("all");
                params.onBrainClawMemoryLimitChange(25);
                params.onBrainClawMemoryIncludeSupersededChange(false);
                params.onBrainClawMemoryRefresh(1);
              }}
            >
              Clear
            </button>
          </div>
        </div>
      </section>
      <div class="stat-grid" style="margin-top: 16px;">
        <div class="stat" title="Total unique memory items archived for this agent in the canonical PostgreSQL store.">
          <div class="stat-label">Total</div>
          <div class="stat-value">${list?.total ?? "—"}</div>
        </div>
        <div class="stat" title="Number of memories matching your current search query, area selection, and confidence threshold.">
          <div class="stat-label">Filtered</div>
          <div class="stat-value">${list?.filtered ?? "—"}</div>
        </div>
        <div class="stat" title="High-fidelity synthesized wisdom, facts, and relational items (Long-term memory).">
          <div class="stat-label">Knowledge</div>
          <div class="stat-value">${list?.knowledge ?? "—"}</div>
        </div>
        <div class="stat" title="Episodic chat history and session summaries (Short-term memory).">
          <div class="stat-label">Conversation</div>
          <div class="stat-value">${list?.conversation ?? "—"}</div>
        </div>
      </div>
      ${
        !list
          ? html`
              <div class="callout info" style="margin-top: 16px;">
                Load BrainClaw memory to browse and edit canonical memory items for this agent.
              </div>
            `
          : html`
              <div
                style="display: grid; grid-template-columns: minmax(300px, 1fr) minmax(340px, 1.2fr); gap: 16px; margin-top: 16px;"
              >
                <section class="card" style="margin: 0;">
                  <div class="row" style="justify-content: space-between;">
                    <div>
                      <div class="card-title">Entries</div>
                      <div class="card-sub">Canonical BrainClaw memory items for this agent.</div>
                    </div>
                    <div class="row" style="gap: 8px; align-items: center;">
                      <button
                        class="btn btn--sm"
                        ?disabled=${page <= 1 || params.agentMemory.listLoading}
                        @click=${() => params.onBrainClawMemoryRefresh(page - 1)}
                      >
                        ${icons.chevronLeft}
                      </button>
                      <div class="muted">Page ${page} of ${pageCount}</div>
                      <button
                        class="btn btn--sm"
                        ?disabled=${page >= pageCount || params.agentMemory.listLoading}
                        @click=${() => params.onBrainClawMemoryRefresh(page + 1)}
                      >
                        ${icons.chevronRight}
                      </button>
                    </div>
                  </div>
                  ${
                    list.items.length === 0
                      ? html`<div class="muted" style="margin-top: 16px;">No BrainClaw memory entries matched the current filter.</div>`
                      : html`
                          <div class="list" style="margin-top: 16px;">
                            ${list.items.map((item) =>
                              renderBrainClawMemoryRow({
                                item,
                                activeId: selected?.id ?? null,
                                onSelect: () => params.onBrainClawMemorySelect(item.id),
                              }),
                            )}
                          </div>
                        `
                  }
                </section>
                <section class="card" style="margin: 0;">
                  ${
                    !selected
                      ? html`<div class="muted">Select a BrainClaw memory item to inspect and edit it.</div>`
                      : html`
                          <div class="agent-file-header">
                            <div>
                              <div class="agent-file-title mono">${selected.id}</div>
                              <div class="agent-file-sub">
                                ${String(selected.metadata?.["memory_class"] ?? "semantic")} ·
                                ${String(selected.metadata?.["memory_type"] ?? "fact")} ·
                                ${String(selected.metadata?.["status"] ?? "active")}
                              </div>
                            </div>
                            <div class="agent-file-actions">
                              <button
                                class="btn btn--sm"
                                ?disabled=${!isDirty}
                                @click=${() => params.onBrainClawMemoryReset()}
                              >
                                Reset
                              </button>
                              <button
                                class="btn btn--sm primary"
                                ?disabled=${params.agentMemory.saving || !isDirty}
                                @click=${() => params.onBrainClawMemorySave()}
                              >
                                ${params.agentMemory.saving ? "Saving…" : "Save"}
                              </button>
                            </div>
                          </div>
                          <div class="agents-overview-grid" style="margin-top: 16px;">
                            <div class="agent-kv">
                              <div class="label">Confidence</div>
                              <div>${resolveMemoryConfidence(selected)?.toFixed(2) ?? "n/a"}</div>
                            </div>
                            <div class="agent-kv">
                              <div class="label">Visibility</div>
                              <div>${String(selected.metadata?.["visibility_scope"] ?? "agent")}</div>
                            </div>
                            <div class="agent-kv">
                              <div class="label">Created</div>
                              <div>${formatRelativeTimestamp(parseIsoTimestamp(selected.created_at))}</div>
                            </div>
                            <div class="agent-kv">
                              <div class="label">Updated</div>
                              <div>${formatRelativeTimestamp(parseIsoTimestamp(selected.updated_at))}</div>
                            </div>
                          </div>
                          <label class="field agent-file-field" style="margin-top: 16px;">
                            <span>Canonical Content</span>
                            <textarea
                              class="agent-file-textarea"
                              .value=${params.agentMemory.draft}
                              @input=${(e: Event) =>
                                params.onBrainClawMemoryDraftChange(
                                  (e.target as HTMLTextAreaElement).value,
                                )}
                            ></textarea>
                          </label>
                          <div class="callout info" style="margin-top: 16px;">
                            Saving creates a superseding PostgreSQL-backed memory version. Weaviate and
                            Neo4j are derived stores and will be refreshed from canonical state.
                          </div>
                        `
                  }
                </section>
              </div>
            `
      }
    </section>
  `;
}

function renderBrainClawMemoryRow(params: {
  item: AgentsBrainClawMemoryRecord;
  activeId: string | null;
  onSelect: () => void;
}) {
  const metadata = params.item.metadata ?? {};
  const createdLabel = formatRelativeTimestamp(parseIsoTimestamp(params.item.updated_at ?? params.item.created_at));
  return html`
    <button
      type="button"
      class="agent-file-row ${params.activeId === params.item.id ? "active" : ""}"
      style="display: block; text-align: left;"
      @click=${params.onSelect}
    >
      <div style="display: flex; justify-content: space-between; gap: 12px; align-items: start;">
        <div style="min-width: 0;">
          <div class="agent-file-name">
            ${String(metadata["memory_class"] ?? "semantic")} · ${String(metadata["memory_type"] ?? "fact")}
          </div>
          <div class="agent-file-meta">${clampText(params.item.content, 140)}</div>
        </div>
        <div style="text-align: right; flex: 0 0 auto;">
          <div class="agent-file-meta">${createdLabel}</div>
          <div class="agent-file-meta">${String(metadata["visibility_scope"] ?? "agent")}</div>
        </div>
      </div>
    </button>
  `;
}

function renderAgentFileRow(file: AgentFileEntry, active: string | null, onSelect: () => void) {
  const status = file.missing
    ? "Missing"
    : `${formatBytes(file.size)} · ${formatRelativeTimestamp(file.updatedAtMs ?? null)}`;
  return html`
    <button
      type="button"
      class="agent-file-row ${active === file.name ? "active" : ""}"
      @click=${onSelect}
    >
      <div>
        <div class="agent-file-name mono">${file.name}</div>
        <div class="agent-file-meta">${status}</div>
      </div>
      ${
        file.missing
          ? html`
              <span class="agent-pill warn">missing</span>
            `
          : nothing
      }
    </button>
  `;
}
