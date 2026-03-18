import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";
/**
 * BrainClaw Search Tool Definition.
 */
export const searchTool = {
    name: "hybrid_graphrag_search",
    description: "Run hybrid GraphRAG search using BM25, vector, and graph community signals.",
    parameters: Type.Object({
        query: Type.String({ description: "The search query string" }),
        topK: Type.Optional(Type.Number({ minimum: 1, default: 8, description: "Number of results to return" })),
        mode: Type.Optional(Type.Union([
            Type.Literal("local", { description: "Focus on specific entity neighborhoods" }),
            Type.Literal("global", { description: "Search across broad community themes" }),
            Type.Literal("hybrid", { description: "Combine local and global retrieval" })
        ], { default: "hybrid" })),
        tenant_id: Type.Optional(Type.String({ description: "Optional tenant identifier" }))
    }),
    async execute(_id, params, ctx) {
        const config = ctx.config || {};
        try {
            // 1. Classify intent (needed for the retrieve function)
            const classification = await callPythonBackend("retrieval", "classify", {
                query: params.query
            }, config);
            // 2. Execute retrieval
            const results = await callPythonBackend("retrieval", "retrieve_sync", {
                query: params.query,
                intent: classification,
                tenant_id: params.tenant_id || "default",
                limit: params.topK || 8
            }, config);
            return {
                content: [
                    {
                        type: "text",
                        text: JSON.stringify(results, null, 2)
                    }
                ]
            };
        }
        catch (error) {
            return {
                content: [
                    {
                        type: "text",
                        text: `Error executing hybrid search: ${error.message}`
                    }
                ],
                isError: true
            };
        }
    }
};
/**
 * Register the search tool.
 */
export function registerSearchTool(api) {
    api.registerTool(searchTool);
}
