import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

export const lcmDescribeTool = {
  name: "lcm_describe",
  description: "Get detailed metadata and provenance for a Lossless-Claw summary.",
  parameters: Type.Object({
    summary_id: Type.String({ description: "The ID of the summary to describe" }),
  }),
  async execute(_id: string, params: any, ctx: any) {
    const config = ctx.config || {};
    try {
      const result = await callPythonBackend(
        "bridge_entrypoints",
        "lcm_describe",
        { summary_id: params.summary_id },
        config,
        ctx
      );

      if (result.error) {
        return {
          content: [
            {
              type: "text",
              text: `Error describing summary: ${result.error}`,
            },
          ],
          isError: true,
        };
      }

      let text = `### Summary Metadata: ${params.summary_id}\n\n`;
      text += `**Content:** ${result.content || 'N/A'}\n\n`;
      text += `**Status:** ${result.status || 'N/A'}\n`;
      text += `**Created At:** ${result.created_at || 'N/A'}\n`;
      text += `**Updated At:** ${result.updated_at || 'N/A'}\n`;
      text += `**Agent ID:** ${result.agent_id || 'N/A'}\n\n`;
      
      if (result.metadata) {
        text += `#### Metadata\n\`\`\`json\n${JSON.stringify(result.metadata, null, 2)}\n\`\`\`\n`;
      }

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
            text: `Failed to describe summary: ${error.message}`,
          },
        ],
        isError: true,
      };
    }
  },
};

export function registerLcmDescribeTool(api: any) {
  api.registerTool(lcmDescribeTool);
}
