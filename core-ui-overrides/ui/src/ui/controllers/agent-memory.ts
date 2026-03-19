import type { GatewayBrowserClient } from "../gateway.ts";
import type {
  AgentsBrainClawMemoryListResult,
  AgentsBrainClawMemoryRecord,
  AgentsBrainClawMemoryUpdateResult,
} from "../types.ts";

export type AgentBrainClawMemoryState = {
  client: GatewayBrowserClient | null;
  connected: boolean;
  agentBrainClawMemoryLoading: boolean;
  agentBrainClawMemoryError: string | null;
  agentBrainClawMemoryList: AgentsBrainClawMemoryListResult | null;
  agentBrainClawMemorySelectedId: string | null;
  agentBrainClawMemoryDraft: string;
  agentBrainClawMemorySaving: boolean;
  agentBrainClawMemoryQuery: string;
  agentBrainClawMemoryClass: string;
  agentBrainClawMemoryLimit: number;
  agentBrainClawMemoryIncludeSuperseded: boolean;
};

const DEFAULT_THRESHOLD = 0.6;

function findRecord(
  list: AgentsBrainClawMemoryListResult | null,
  memoryId: string | null,
): AgentsBrainClawMemoryRecord | null {
  if (!list || !memoryId) {
    return null;
  }
  return list.items.find((item) => item.id === memoryId) ?? null;
}

function syncSelection(state: AgentBrainClawMemoryState) {
  const current = findRecord(state.agentBrainClawMemoryList, state.agentBrainClawMemorySelectedId);
  if (current) {
    state.agentBrainClawMemoryDraft = current.content;
    return;
  }
  const fallback = state.agentBrainClawMemoryList?.items?.[0] ?? null;
  state.agentBrainClawMemorySelectedId = fallback?.id ?? null;
  state.agentBrainClawMemoryDraft = fallback?.content ?? "";
}

export function selectAgentBrainClawMemory(state: AgentBrainClawMemoryState, memoryId: string) {
  state.agentBrainClawMemorySelectedId = memoryId;
  const record = findRecord(state.agentBrainClawMemoryList, memoryId);
  state.agentBrainClawMemoryDraft = record?.content ?? "";
}

export async function loadAgentBrainClawMemories(
  state: AgentBrainClawMemoryState,
  agentId: string,
  opts?: { page?: number },
) {
  if (!state.client || !state.connected || state.agentBrainClawMemoryLoading) {
    return;
  }
  state.agentBrainClawMemoryLoading = true;
  state.agentBrainClawMemoryError = null;
  try {
    const res = await state.client.request<AgentsBrainClawMemoryListResult | null>(
      "agents.memory.list",
      {
        agentId,
        query: state.agentBrainClawMemoryQuery,
        area: state.agentBrainClawMemoryClass,
        limit: state.agentBrainClawMemoryLimit,
        page: opts?.page ?? state.agentBrainClawMemoryList?.page ?? 1,
        threshold: DEFAULT_THRESHOLD,
        includeSuperseded: state.agentBrainClawMemoryIncludeSuperseded,
      },
    );
    if (res) {
      state.agentBrainClawMemoryList = res;
      syncSelection(state);
    }
  } catch (err) {
    state.agentBrainClawMemoryError = String(err);
  } finally {
    state.agentBrainClawMemoryLoading = false;
  }
}

export async function saveAgentBrainClawMemory(
  state: AgentBrainClawMemoryState,
  agentId: string,
  memoryId: string,
  content: string,
) {
  if (!state.client || !state.connected || state.agentBrainClawMemorySaving) {
    return;
  }
  state.agentBrainClawMemorySaving = true;
  state.agentBrainClawMemoryError = null;
  try {
    const res = await state.client.request<AgentsBrainClawMemoryUpdateResult | null>(
      "agents.memory.update",
      {
        agentId,
        memoryId,
        content,
        reason: "Control UI BrainClaw memory edit",
      },
    );
    if (res?.memory) {
      state.agentBrainClawMemorySelectedId = res.memory.id;
      state.agentBrainClawMemoryDraft = res.memory.content;
    }
  } catch (err) {
    state.agentBrainClawMemoryError = String(err);
  } finally {
    state.agentBrainClawMemorySaving = false;
  }
  await loadAgentBrainClawMemories(state, agentId, { page: 1 });
}
