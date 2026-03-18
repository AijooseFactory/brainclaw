import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

/**
 * BrainClaw Graph Health Tool — wired to real Python backend.
 */
export const graphHealthTool = {
  name: "hybrid_graphrag_graph_health",
  description: "Check the health and connectivity of the Neo4j knowledge graph and community structure.",
  parameters: Type.Object({
    tenant_id: Type.Optional(Type.String({ description: "Optional tenant identifier" }))
  }),
  async execute(_id: string, params: any, ctx: any) {
    const config = ctx.config || {};
    try {
      const health = await callPythonBackend("graph.health", "get_health_stats", params, config, ctx);
      return {
        content: [{ type: "text", text: JSON.stringify(health, null, 2) }]
      };
    } catch (error: any) {
      return {
        content: [{ type: "text", text: `Error checking graph health: ${error.message}` }],
        isError: true
      };
    }
  }
};

export function registerGraphHealthTool(api: any) {
  api.registerTool(graphHealthTool);
}
