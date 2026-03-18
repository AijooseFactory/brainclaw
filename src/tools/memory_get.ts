import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

function parseBrainClawMemoryPath(path: string): string | null {
  const prefix = "brainclaw://memory/";
  return path.startsWith(prefix) ? path.slice(prefix.length) : null;
}

export const memoryGetTool = {
  name: "memory_get",
  description:
    "Read a cited BrainClaw memory record using the portable citation returned by memory_search.",
  parameters: Type.Object({
    path: Type.String({ description: "A citation path returned by memory_search" }),
    from: Type.Optional(Type.Number({ minimum: 1, description: "Unused line offset for compatibility" })),
    lines: Type.Optional(Type.Number({ minimum: 1, description: "Unused line count for compatibility" })),
  }),
  async execute(_id: string, params: any, ctx: any) {
    const memoryId = parseBrainClawMemoryPath(params.path);
    if (!memoryId) {
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                path: params.path,
                text: "",
                disabled: true,
                error: "Unsupported BrainClaw memory citation path.",
              },
              null,
              2,
            ),
          },
        ],
        isError: true,
      };
    }

    const config = ctx?.config || {};

    try {
      const record = await callPythonBackend(
        "bridge_entrypoints",
        "get_memory",
        { memory_id: memoryId },
        config,
        ctx,
      );

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                path: params.path,
                text: record?.content ?? "",
                citation: params.path,
                metadata: record?.metadata ?? {},
                provenance: record?.provenance ?? {},
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
                path: params.path,
                text: "",
                disabled: true,
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

export function registerMemoryGetTool(api: any) {
  api.registerTool(memoryGetTool);
}
