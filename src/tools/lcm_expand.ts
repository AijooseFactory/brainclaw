import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

export const lcmExpandTool = {
  name: "lcm_expand",
  description: "Expand a Lossless-Claw summary into its constituent chunks for deep context retrieval.",
  parameters: Type.Object({
    summary_id: Type.String({ description: "The ID of the summary to expand" }),
  }),
  async execute(_id: string, params: any, ctx: any) {
    const config = ctx.config || {};
    try {
      const result = await callPythonBackend(
        "bridge_entrypoints",
        "lcm_expand",
        { summary_id: params.summary_id },
        config,
        ctx
      );

      if (result.error) {
        return {
          content: [
            {
              type: "text",
              text: `Error expanding summary: ${result.error}`,
            },
          ],
          isError: true,
        };
      }

      const chunks = result.chunks || [];
      let text = `### Expanded Summary: ${params.summary_id}\n\n`;
      text += `This summary contains ${result.count} source chunks.\n\n`;

      chunks.forEach((chunk: any, index: number) => {
        text += `#### Chunk ${index + 1} (${chunk.id})\n`;
        text += `${chunk.content}\n\n`;
      });

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
            text: `Failed to expand summary: ${error.message}`,
          },
        ],
        isError: true,
      };
    }
  },
};

export function registerLcmExpandTool(api: any) {
  api.registerTool(lcmExpandTool);
}
