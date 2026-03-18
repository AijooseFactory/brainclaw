import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

/**
 * BrainClaw Contradiction Check Tool Definition.
 */
export const contradictionCheckTool = {
  name: "hybrid_graphrag_contradiction_check",
  description: "Scan the knowledge base for contradictory claims or inconsistent entity properties.",
  parameters: Type.Object({
    entity_name: Type.Optional(Type.String({ description: "Optional entity name to focus the check on" })),
    tenant_id: Type.Optional(Type.String({ description: "Optional tenant identifier" }))
  }),
  async execute(_id: string, params: any, ctx: any) {
    const config = ctx.config || {};
    try {
      const result = await callPythonBackend(
        "bridge_entrypoints",
        "check_contradictions",
        {
          entity_name: params.entity_name || "",
          tenant_id: params.tenant_id || "",
          limit: 20,
        },
        config,
        ctx,
      );

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result, null, 2)
          }
        ]
      };
    } catch (error: any) {
      return {
        content: [
          {
            type: "text",
            text: `Error executing contradiction check: ${error.message}`
          }
        ],
        isError: true
      };
    }
  }
};

/**
 * Register the contradiction check tool.
 */
export function registerContradictionTool(api: any) {
  api.registerTool(contradictionCheckTool);
}
