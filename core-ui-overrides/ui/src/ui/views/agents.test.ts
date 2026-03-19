import { render } from "lit";
import { describe, expect, it } from "vitest";
import { renderAgents, type AgentsProps } from "./agents.ts";

function createSkill() {
  return {
    name: "Repo Skill",
    description: "Skill description",
    source: "workspace",
    filePath: "/tmp/skill",
    baseDir: "/tmp",
    skillKey: "repo-skill",
    always: false,
    disabled: false,
    blockedByAllowlist: false,
    eligible: true,
    requirements: {
      bins: [],
      env: [],
      config: [],
      os: [],
    },
    missing: {
      bins: [],
      env: [],
      config: [],
      os: [],
    },
    configChecks: [],
    install: [],
  };
}

function createProps(overrides: Partial<AgentsProps> = {}): AgentsProps {
  return {
    basePath: "",
    loading: false,
    error: null,
    agentsList: {
      defaultId: "alpha",
      mainKey: "main",
      scope: "workspace",
      agents: [{ id: "alpha", name: "Alpha" } as never, { id: "beta", name: "Beta" } as never],
    },
    selectedAgentId: "beta",
    activePanel: "overview",
    config: {
      form: null,
      loading: false,
      saving: false,
      dirty: false,
    },
    channels: {
      snapshot: null,
      loading: false,
      error: null,
      lastSuccess: null,
    },
    cron: {
      status: null,
      jobs: [],
      loading: false,
      error: null,
    },
    agentFiles: {
      list: null,
      loading: false,
      error: null,
      active: null,
      contents: {},
      drafts: {},
      saving: false,
    },
    agentMemory: {
      view: "file",
      listLoading: false,
      listError: null,
      list: null,
      selectedId: null,
      draft: "",
      saving: false,
      query: "",
      memoryClass: "all",
      limit: 25,
      includeSuperseded: false,
    },
    agentIdentityLoading: false,
    agentIdentityError: null,
    agentIdentityById: {},
    agentSkills: {
      report: null,
      loading: false,
      error: null,
      agentId: null,
      filter: "",
    },
    toolsCatalog: {
      loading: false,
      error: null,
      result: null,
    },
    onRefresh: () => undefined,
    onSelectAgent: () => undefined,
    onSelectPanel: () => undefined,
    onLoadFiles: () => undefined,
    onSelectFile: () => undefined,
    onFileDraftChange: () => undefined,
    onFileReset: () => undefined,
    onFileSave: () => undefined,
    onSelectMemoryView: () => undefined,
    onBrainClawMemoryRefresh: () => undefined,
    onBrainClawMemorySelect: () => undefined,
    onBrainClawMemoryDraftChange: () => undefined,
    onBrainClawMemoryReset: () => undefined,
    onBrainClawMemorySave: () => undefined,
    onBrainClawMemoryQueryChange: () => undefined,
    onBrainClawMemoryClassChange: () => undefined,
    onBrainClawMemoryLimitChange: () => undefined,
    onBrainClawMemoryIncludeSupersededChange: () => undefined,
    onToolsProfileChange: () => undefined,
    onToolsOverridesChange: () => undefined,
    onConfigReload: () => undefined,
    onConfigSave: () => undefined,
    onModelChange: () => undefined,
    onModelFallbacksChange: () => undefined,
    onChannelsRefresh: () => undefined,
    onCronRefresh: () => undefined,
    onCronRunNow: () => undefined,
    onSkillsFilterChange: () => undefined,
    onSkillsRefresh: () => undefined,
    onAgentSkillToggle: () => undefined,
    onAgentSkillsClear: () => undefined,
    onAgentSkillsDisableAll: () => undefined,
    onSetDefault: () => undefined,
    ...overrides,
  };
}

describe("renderAgents", () => {
  it("shows the skills count only for the selected agent's report", async () => {
    const container = document.createElement("div");
    render(
      renderAgents(
        createProps({
          agentSkills: {
            report: {
              workspaceDir: "/tmp/workspace",
              managedSkillsDir: "/tmp/skills",
              skills: [createSkill()],
            },
            loading: false,
            error: null,
            agentId: "alpha",
            filter: "",
          },
        }),
      ),
      container,
    );
    await Promise.resolve();

    const skillsTab = Array.from(container.querySelectorAll<HTMLButtonElement>(".agent-tab")).find(
      (button) => button.textContent?.includes("Skills"),
    );

    expect(skillsTab?.textContent?.trim()).toBe("Skills");
  });

  it("shows the selected agent's skills count when the report matches", async () => {
    const container = document.createElement("div");
    render(
      renderAgents(
        createProps({
          agentSkills: {
            report: {
              workspaceDir: "/tmp/workspace",
              managedSkillsDir: "/tmp/skills",
              skills: [createSkill()],
            },
            loading: false,
            error: null,
            agentId: "beta",
            filter: "",
          },
        }),
      ),
      container,
    );
    await Promise.resolve();

    const skillsTab = Array.from(container.querySelectorAll<HTMLButtonElement>(".agent-tab")).find(
      (button) => button.textContent?.includes("Skills"),
    );

    expect(skillsTab?.textContent?.trim()).toContain("1");
  });

  it("shows the Memory tab only when BrainClaw is installed", async () => {
    const withoutBrainClaw = document.createElement("div");
    render(renderAgents(createProps()), withoutBrainClaw);
    await Promise.resolve();

    const missingTab = Array.from(
      withoutBrainClaw.querySelectorAll<HTMLButtonElement>(".agent-tab"),
    ).find((button) => button.textContent?.includes("Memory"));
    expect(missingTab).toBeUndefined();

    const withBrainClaw = document.createElement("div");
    render(
      renderAgents(
        createProps({
          config: {
            form: {
              plugins: {
                installs: {
                  brainclaw: {
                    source: "path",
                  },
                },
              },
            },
            loading: false,
            saving: false,
            dirty: false,
          },
        }),
      ),
      withBrainClaw,
    );
    await Promise.resolve();

    const tabLabels = Array.from(
      withBrainClaw.querySelectorAll<HTMLButtonElement>(".agent-tab"),
    ).map((button) => button.textContent?.trim() ?? "");
    expect(tabLabels).toContain("Memory");
    expect(tabLabels.indexOf("Memory")).toBe(tabLabels.indexOf("Overview") + 1);
  });

  it("renders the Memory panel with MEMORY.md and BrainClaw Memory navigation", async () => {
    const container = document.createElement("div");
    render(
      renderAgents(
        createProps({
          activePanel: "memory" as unknown as AgentsProps["activePanel"],
          config: {
            form: {
              plugins: {
                installs: {
                  brainclaw: {
                    source: "path",
                  },
                },
              },
            },
            loading: false,
            saving: false,
            dirty: false,
          },
          agentFiles: {
            list: {
              agentId: "beta",
              workspace: "/tmp/workspace-beta",
              files: [
                {
                  name: "MEMORY.md",
                  path: "/tmp/workspace-beta/MEMORY.md",
                  missing: false,
                  size: 42,
                  updatedAtMs: 123456,
                },
                {
                  name: "IDENTITY.md",
                  path: "/tmp/workspace-beta/IDENTITY.md",
                  missing: false,
                  size: 12,
                  updatedAtMs: 123456,
                },
              ],
            },
            loading: false,
            error: null,
            active: "MEMORY.md",
            contents: {
              "MEMORY.md": "# Memory\n",
            },
            drafts: {
              "MEMORY.md": "# Memory\n",
            },
            saving: false,
          },
          agentMemory: {
            view: "file",
            listLoading: false,
            listError: null,
            list: null,
            selectedId: null,
            draft: "",
            saving: false,
            query: "",
            memoryClass: "all",
            limit: 25,
            includeSuperseded: false,
          },
        }),
      ),
      container,
    );
    await Promise.resolve();

    expect(container.textContent).toContain("Agent Memory");
    expect(container.textContent).toContain("MEMORY.md");
    expect(container.textContent).toContain("BrainClaw Memory");
    expect(container.querySelector(".agent-files-list")).toBeNull();
    expect(container.querySelector("textarea")?.value).toBe("# Memory\n");
  });

  it("renders the BrainClaw Memory manager for the selected agent", async () => {
    const container = document.createElement("div");
    render(
      renderAgents(
        createProps({
          activePanel: "memory" as unknown as AgentsProps["activePanel"],
          config: {
            form: {
              plugins: {
                installs: {
                  brainclaw: {
                    source: "path",
                  },
                },
              },
            },
            loading: false,
            saving: false,
            dirty: false,
          },
          agentMemory: {
            view: "brainclaw",
            listLoading: false,
            listError: null,
            list: {
              agentId: "beta",
              total: 3,
              filtered: 2,
              knowledge: 2,
              conversation: 0,
              page: 1,
              pageSize: 25,
              pageCount: 1,
              items: [
                {
                  id: "mem-1",
                  content: "Albert owns BrainClaw rollout safety.",
                  metadata: {
                    memory_class: "decision",
                    memory_type: "technical",
                    status: "active",
                    visibility_scope: "agent",
                    confidence: 0.93,
                  },
                  provenance: {
                    extractor_name: "brainclaw",
                  },
                  created_at: "2026-03-19T10:00:00.000Z",
                  updated_at: "2026-03-19T11:00:00.000Z",
                },
                {
                  id: "mem-2",
                  content: "Lore specializes in Hybrid GraphRAG memory management.",
                  metadata: {
                    memory_class: "identity",
                    memory_type: "role",
                    status: "active",
                    visibility_scope: "team",
                    confidence: 0.88,
                  },
                  provenance: {
                    extractor_name: "brainclaw",
                  },
                  created_at: "2026-03-19T09:00:00.000Z",
                  updated_at: "2026-03-19T09:30:00.000Z",
                },
              ],
            },
            selectedId: "mem-1",
            draft: "Albert owns BrainClaw rollout safety.",
            saving: false,
            query: "rollout",
            memoryClass: "decision",
            limit: 25,
            includeSuperseded: false,
          },
        }),
      ),
      container,
    );
    await Promise.resolve();

    expect(container.textContent).toContain("BrainClaw Memory");
    expect(container.textContent).toContain("Total");
    expect(container.textContent).toContain("Filtered");
    expect(container.textContent).toContain("Knowledge");
    expect(container.textContent).toContain("Conversation");
    expect(container.textContent).toContain("Albert owns BrainClaw rollout safety.");
    expect(container.textContent).toContain("Lore specializes in Hybrid GraphRAG memory management.");
  });
});
