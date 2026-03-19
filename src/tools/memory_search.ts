import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

function normalizeSearchResults(results: any[]) {
  return results.map((entry, index) => {
    const id = entry?.id ?? entry?.memory_id ?? `result-${index + 1}`;
    const snippet = entry?.content ?? entry?.summary ?? entry?.text ?? JSON.stringify(entry);
    return {
      path: `brainclaw://memory/${id}`,
      snippet,
      score: entry?.score ?? entry?.relevance ?? entry?.confidence ?? null,
      startLine: 1,
      endLine: 1,
      metadata: entry?.metadata ?? {},
    };
  });
}

export const memorySearchTool = {
  name: "memory_search",
  description:
    "Search BrainClaw Hybrid GraphRAG memory using hybrid retrieval and return portable citations.",
  parameters: Type.Object({
    query: Type.String({ description: "The memory search query" }),
    maxResults: Type.Optional(
      Type.Number({ minimum: 1, default: 8, description: "Maximum number of results to return" }),
    ),
    minScore: Type.Optional(
      Type.Number({ minimum: 0, maximum: 1, description: "Optional minimum result score" }),
    ),
    tenant_id: Type.Optional(Type.String({ description: "Optional tenant identifier" })),
  }),
  async execute(_id: string, params: any, ctx: any) {
    const config = ctx.config || {};
    try {
      const classification = await callPythonBackend(
        "bridge_entrypoints",
        "classify",
        { query: params.query },
        config,
        ctx,
      );

      const rawResults = await callPythonBackend(
        "bridge_entrypoints",
        "retrieve_sync",
        {
          query: params.query,
          intent: classification?.intent ?? classification,
          tenant_id: params.tenant_id,
          limit: params.maxResults || 8,
        },
        config,
        ctx,
      );

      const resultList = Array.isArray(rawResults)
        ? rawResults
        : Array.isArray(rawResults?.results)
          ? rawResults.results
          : [];
      const results = normalizeSearchResults(resultList);
      const filtered =
        typeof params.minScore === "number"
          ? results.filter((entry) => entry.score == null || entry.score >= params.minScore)
          : results;

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                results: filtered,
                provider: "brainclaw",
                mode: "hybrid",
              },
              null,
              2,
            ),
          },
        ],
      };
    } catch (error: any) {
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                results: [],
                disabled: true,
                unavailable: true,
                error: error.message,
              },
              null,
              2,
            ),
          },
        ],
        isError: true,
      };
    }
  },
};

export function registerMemorySearchTool(api: any) {
  api.registerTool(memorySearchTool);
}
