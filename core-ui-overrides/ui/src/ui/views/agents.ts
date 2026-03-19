import { html, nothing } from "lit";
import type {
  AgentIdentityResult,
  AgentsBrainClawMemoryListResult,
  AgentsFilesListResult,
  AgentsListResult,
  ChannelsStatusSnapshot,
  CronJob,
  CronStatus,
  SkillStatusReport,
  ToolsCatalogResult,
} from "../types.ts";
import { renderAgentOverview } from "./agents-panels-overview.ts";
import {
  renderAgentFiles,
  renderAgentMemory,
  renderAgentChannels,
  renderAgentCron,
} from "./agents-panels-status-files.ts";
import { renderAgentTools, renderAgentSkills } from "./agents-panels-tools-skills.ts";
import { agentBadgeText, buildAgentContext, normalizeAgentLabel } from "./agents-utils.ts";

export type AgentsPanel =
  | "overview"
  | "memory"
  | "files"
  | "tools"
  | "skills"
  | "channels"
  | "cron";

export type ConfigState = {
  form: Record<string, unknown> | null;
  loading: boolean;
  saving: boolean;
  dirty: boolean;
};

export type ChannelsState = {
  snapshot: ChannelsStatusSnapshot | null;
  loading: boolean;
  error: string | null;
  lastSuccess: number | null;
};

export type CronState = {
  status: CronStatus | null;
  jobs: CronJob[];
  loading: boolean;
  error: string | null;
};

export type AgentFilesState = {
  list: AgentsFilesListResult | null;
  loading: boolean;
  error: string | null;
  active: string | null;
  contents: Record<string, string>;
  drafts: Record<string, string>;
  saving: boolean;
};

export type AgentMemoryState = {
  view: "file" | "brainclaw";
  listLoading: boolean;
  listError: string | null;
  list: AgentsBrainClawMemoryListResult | null;
  selectedId: string | null;
  draft: string;
  saving: boolean;
  query: string;
  memoryClass: string;
  limit: number;
  includeSuperseded: boolean;
};

export type AgentSkillsState = {
  report: SkillStatusReport | null;
  loading: boolean;
  error: string | null;
  agentId: string | null;
  filter: string;
};

export type ToolsCatalogState = {
  loading: boolean;
  error: string | null;
  result: ToolsCatalogResult | null;
};

export type AgentsProps = {
  basePath: string;
  loading: boolean;
  error: string | null;
  agentsList: AgentsListResult | null;
  selectedAgentId: string | null;
  activePanel: AgentsPanel;
  config: ConfigState;
  channels: ChannelsState;
  cron: CronState;
  agentFiles: AgentFilesState;
  agentMemory: AgentMemoryState;
  agentIdentityLoading: boolean;
  agentIdentityError: string | null;
  agentIdentityById: Record<string, AgentIdentityResult>;
  agentSkills: AgentSkillsState;
  toolsCatalog: ToolsCatalogState;
  onRefresh: () => void;
  onSelectAgent: (agentId: string) => void;
  onSelectPanel: (panel: AgentsPanel) => void;
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
  onToolsProfileChange: (agentId: string, profile: string | null, clearAllow: boolean) => void;
  onToolsOverridesChange: (agentId: string, alsoAllow: string[], deny: string[]) => void;
  onConfigReload: () => void;
  onConfigSave: () => void;
  onModelChange: (agentId: string, modelId: string | null) => void;
  onModelFallbacksChange: (agentId: string, fallbacks: string[]) => void;
  onChannelsRefresh: () => void;
  onCronRefresh: () => void;
  onCronRunNow: (jobId: string) => void;
  onSkillsFilterChange: (next: string) => void;
  onSkillsRefresh: () => void;
  onAgentSkillToggle: (agentId: string, skillName: string, enabled: boolean) => void;
  onAgentSkillsClear: (agentId: string) => void;
  onAgentSkillsDisableAll: (agentId: string) => void;
  onSetDefault: (agentId: string) => void;
};

export function renderAgents(props: AgentsProps) {
  const agents = props.agentsList?.agents ?? [];
  const defaultId = props.agentsList?.defaultId ?? null;
  const selectedId = props.selectedAgentId ?? defaultId ?? agents[0]?.id ?? null;
  const brainClawInstalled = isBrainClawInstalled(props.config.form);
  const activePanel =
    props.activePanel === "memory" && !brainClawInstalled ? "overview" : props.activePanel;
  const selectedAgent = selectedId
    ? (agents.find((agent) => agent.id === selectedId) ?? null)
    : null;
  const selectedSkillCount =
    selectedId && props.agentSkills.agentId === selectedId
      ? (props.agentSkills.report?.skills?.length ?? null)
      : null;

  const channelEntryCount = props.channels.snapshot
    ? Object.keys(props.channels.snapshot.channelAccounts ?? {}).length
    : null;
  const cronJobCount = selectedId
    ? props.cron.jobs.filter((j) => j.agentId === selectedId).length
    : null;
  const tabCounts: Record<string, number | null> = {
    files: props.agentFiles.list?.files?.length ?? null,
    skills: selectedSkillCount,
    channels: channelEntryCount,
    cron: cronJobCount || null,
  };

  return html`
    <div class="agents-layout">
      <section class="agents-toolbar">
        <div class="agents-toolbar-row">
          <span class="agents-toolbar-label">Agent</span>
          <div class="agents-control-row">
            <div class="agents-control-select">
              <select
                class="agents-select"
                .value=${selectedId ?? ""}
                ?disabled=${props.loading || agents.length === 0}
                @change=${(e: Event) => props.onSelectAgent((e.target as HTMLSelectElement).value)}
              >
                ${
                  agents.length === 0
                    ? html`
                        <option value="">No agents</option>
                      `
                    : agents.map(
                        (agent) => html`
                        <option value=${agent.id} ?selected=${agent.id === selectedId}>
                          ${normalizeAgentLabel(agent)}${agentBadgeText(agent.id, defaultId) ? ` (${agentBadgeText(agent.id, defaultId)})` : ""}
                        </option>
                      `,
                      )
                }
              </select>
            </div>
            <div class="agents-control-actions">
              ${
                selectedAgent
                  ? html`
                      <div class="agent-actions-wrap">
                        <button
                          class="agent-actions-toggle"
                          type="button"
                          @click=${() => {
                            actionsMenuOpen = !actionsMenuOpen;
                          }}
                        >⋯</button>
                        ${
                          actionsMenuOpen
                            ? html`
                                <div class="agent-actions-menu">
                                  <button type="button" @click=${() => {
                                    void navigator.clipboard.writeText(selectedAgent.id);
                                    actionsMenuOpen = false;
                                  }}>Copy agent ID</button>
                                  <button
                                    type="button"
                                    ?disabled=${Boolean(defaultId && selectedAgent.id === defaultId)}
                                    @click=${() => {
                                      props.onSetDefault(selectedAgent.id);
                                      actionsMenuOpen = false;
                                    }}
                                  >
                                    ${defaultId && selectedAgent.id === defaultId ? "Already default" : "Set as default"}
                                  </button>
                                </div>
                              `
                            : nothing
                        }
                      </div>
                    `
                  : nothing
              }
              <button class="btn btn--sm agents-refresh-btn" ?disabled=${props.loading} @click=${props.onRefresh}>
                ${props.loading ? "Loading…" : "Refresh"}
              </button>
            </div>
          </div>
        </div>
        ${
          props.error
            ? html`<div class="callout danger" style="margin-top: 8px;">${props.error}</div>`
            : nothing
        }
      </section>
      <section class="agents-main">
        ${
          !selectedAgent
            ? html`
                <div class="card">
                  <div class="card-title">Select an agent</div>
                  <div class="card-sub">Pick an agent to inspect its workspace and tools.</div>
                </div>
              `
            : html`
                ${renderAgentTabs(activePanel, (panel) => props.onSelectPanel(panel), tabCounts, {
                  showMemory: brainClawInstalled,
                })}
                ${
                  activePanel === "overview"
                    ? renderAgentOverview({
                        agent: selectedAgent,
                        basePath: props.basePath,
                        defaultId,
                        configForm: props.config.form,
                        agentFilesList: props.agentFiles.list,
                        agentIdentity: props.agentIdentityById[selectedAgent.id] ?? null,
                        agentIdentityError: props.agentIdentityError,
                        agentIdentityLoading: props.agentIdentityLoading,
                        configLoading: props.config.loading,
                        configSaving: props.config.saving,
                        configDirty: props.config.dirty,
                        onConfigReload: props.onConfigReload,
                        onConfigSave: props.onConfigSave,
                        onModelChange: props.onModelChange,
                        onModelFallbacksChange: props.onModelFallbacksChange,
                        onSelectPanel: props.onSelectPanel,
                      })
                    : nothing
                }
                ${
                  activePanel === "memory"
                    ? renderAgentMemory({
                        agentMemory: props.agentMemory,
                        agentId: selectedAgent.id,
                        agentFilesList: props.agentFiles.list,
                        agentFilesLoading: props.agentFiles.loading,
                        agentFilesError: props.agentFiles.error,
                        agentFileActive: props.agentFiles.active,
                        agentFileContents: props.agentFiles.contents,
                        agentFileDrafts: props.agentFiles.drafts,
                        agentFileSaving: props.agentFiles.saving,
                        onLoadFiles: props.onLoadFiles,
                        onSelectFile: props.onSelectFile,
                        onFileDraftChange: props.onFileDraftChange,
                        onFileReset: props.onFileReset,
                        onFileSave: props.onFileSave,
                        onSelectMemoryView: props.onSelectMemoryView,
                        onBrainClawMemoryRefresh: props.onBrainClawMemoryRefresh,
                        onBrainClawMemorySelect: props.onBrainClawMemorySelect,
                        onBrainClawMemoryDraftChange: props.onBrainClawMemoryDraftChange,
                        onBrainClawMemoryReset: props.onBrainClawMemoryReset,
                        onBrainClawMemorySave: props.onBrainClawMemorySave,
                        onBrainClawMemoryQueryChange: props.onBrainClawMemoryQueryChange,
                        onBrainClawMemoryClassChange: props.onBrainClawMemoryClassChange,
                        onBrainClawMemoryLimitChange: props.onBrainClawMemoryLimitChange,
                        onBrainClawMemoryIncludeSupersededChange:
                          props.onBrainClawMemoryIncludeSupersededChange,
                      })
                    : nothing
                }
                ${
                  activePanel === "files"
                    ? renderAgentFiles({
                        agentId: selectedAgent.id,
                        agentFilesList: props.agentFiles.list,
                        agentFilesLoading: props.agentFiles.loading,
                        agentFilesError: props.agentFiles.error,
                        agentFileActive: props.agentFiles.active,
                        agentFileContents: props.agentFiles.contents,
                        agentFileDrafts: props.agentFiles.drafts,
                        agentFileSaving: props.agentFiles.saving,
                        onLoadFiles: props.onLoadFiles,
                        onSelectFile: props.onSelectFile,
                        onFileDraftChange: props.onFileDraftChange,
                        onFileReset: props.onFileReset,
                        onFileSave: props.onFileSave,
                      })
                    : nothing
                }
                ${
                  activePanel === "tools"
                    ? renderAgentTools({
                        agentId: selectedAgent.id,
                        configForm: props.config.form,
                        configLoading: props.config.loading,
                        configSaving: props.config.saving,
                        configDirty: props.config.dirty,
                        toolsCatalogLoading: props.toolsCatalog.loading,
                        toolsCatalogError: props.toolsCatalog.error,
                        toolsCatalogResult: props.toolsCatalog.result,
                        onProfileChange: props.onToolsProfileChange,
                        onOverridesChange: props.onToolsOverridesChange,
                        onConfigReload: props.onConfigReload,
                        onConfigSave: props.onConfigSave,
                      })
                    : nothing
                }
                ${
                  activePanel === "skills"
                    ? renderAgentSkills({
                        agentId: selectedAgent.id,
                        report: props.agentSkills.report,
                        loading: props.agentSkills.loading,
                        error: props.agentSkills.error,
                        activeAgentId: props.agentSkills.agentId,
                        configForm: props.config.form,
                        configLoading: props.config.loading,
                        configSaving: props.config.saving,
                        configDirty: props.config.dirty,
                        filter: props.agentSkills.filter,
                        onFilterChange: props.onSkillsFilterChange,
                        onRefresh: props.onSkillsRefresh,
                        onToggle: props.onAgentSkillToggle,
                        onClear: props.onAgentSkillsClear,
                        onDisableAll: props.onAgentSkillsDisableAll,
                        onConfigReload: props.onConfigReload,
                        onConfigSave: props.onConfigSave,
                      })
                    : nothing
                }
                ${
                  activePanel === "channels"
                    ? renderAgentChannels({
                        context: buildAgentContext(
                          selectedAgent,
                          props.config.form,
                          props.agentFiles.list,
                          defaultId,
                          props.agentIdentityById[selectedAgent.id] ?? null,
                        ),
                        configForm: props.config.form,
                        snapshot: props.channels.snapshot,
                        loading: props.channels.loading,
                        error: props.channels.error,
                        lastSuccess: props.channels.lastSuccess,
                        onRefresh: props.onChannelsRefresh,
                      })
                    : nothing
                }
                ${
                  activePanel === "cron"
                    ? renderAgentCron({
                        context: buildAgentContext(
                          selectedAgent,
                          props.config.form,
                          props.agentFiles.list,
                          defaultId,
                          props.agentIdentityById[selectedAgent.id] ?? null,
                        ),
                        agentId: selectedAgent.id,
                        jobs: props.cron.jobs,
                        status: props.cron.status,
                        loading: props.cron.loading,
                        error: props.cron.error,
                        onRefresh: props.onCronRefresh,
                        onRunNow: props.onCronRunNow,
                      })
                    : nothing
                }
              `
        }
      </section>
    </div>
  `;
}

let actionsMenuOpen = false;

function renderAgentTabs(
  active: AgentsPanel,
  onSelect: (panel: AgentsPanel) => void,
  counts: Record<string, number | null>,
  options?: { showMemory?: boolean },
) {
  const tabs: Array<{ id: AgentsPanel; label: string }> = [
    { id: "overview", label: "Overview" },
    ...(options?.showMemory ? [{ id: "memory" as const, label: "Memory" }] : []),
    { id: "files", label: "Files" },
    { id: "tools", label: "Tools" },
    { id: "skills", label: "Skills" },
    { id: "channels", label: "Channels" },
    { id: "cron", label: "Cron Jobs" },
  ];
  return html`
    <div class="agent-tabs">
      ${tabs.map(
        (tab) => html`
          <button
            class="agent-tab ${active === tab.id ? "active" : ""}"
            type="button"
            @click=${() => onSelect(tab.id)}
          >
            ${tab.label}${counts[tab.id] != null ? html`<span class="agent-tab-count">${counts[tab.id]}</span>` : nothing}
          </button>
        `,
      )}
    </div>
  `;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function isBrainClawInstalled(configForm: Record<string, unknown> | null) {
  const plugins = asRecord(configForm?.plugins);
  const installs = asRecord(plugins?.installs);
  const entries = asRecord(plugins?.entries);
  return Boolean(
    (installs && Object.prototype.hasOwnProperty.call(installs, "brainclaw")) ||
    (entries && Object.prototype.hasOwnProperty.call(entries, "brainclaw")),
  );
}
