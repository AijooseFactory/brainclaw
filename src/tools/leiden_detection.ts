import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

export const leidenDetectionTool = {
  name: "hybrid_graphrag_leiden",
  description: "Activate Leiden community detection in Neo4j for hierarchical knowledge organization.",
  parameters: Type.Object({}),
  async execute(_id: string, params: any, ctx: any) {
    const config = ctx.config || {};
    try {
      const result = await callPythonBackend(
        "bridge_entrypoints",
        "hybrid_graphrag_leiden",
        {},
        config,
        ctx
      );

      if (result.error) {
        return {
          content: [
            {
              type: "text",
              text: `Error running Leiden detection: ${result.error}`,
            },
          ],
          isError: true,
        };
      }

      if (result.status === 'ERROR') {
        return {
          content: [
            {
              type: "text",
              text: `Leiden detection failed: ${result.message}`,
            },
          ],
          isError: true,
        };
      }

      const text = `### Leiden Detection Successful\n\n` +
                   `- **Community Count:** ${result.communityCount}\n` +
                   `- **Levels Ran:** ${result.levels}\n` +
                   `- **Modularity:** ${result.modularity.toFixed(4)}\n\n` +
                   `Entities in Neo4j have been updated with \`community_leiden\` property.`;

      return {
        content: [
          {
            type: "text",
            text,
          },
        ],
      };
    } catch (error: any) {
      return {
        content: [
          {
            type: "text",
            text: `Failed to run Leiden detection: ${error.message}`,
          },
        ],
        isError: true,
      };
    }
  },
};

export function registerLeidenDetectionTool(api: any) {
  api.registerTool(leidenDetectionTool);
}
