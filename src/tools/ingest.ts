import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

/**
 * BrainClaw Ingest Tool Definition.
 */
export const ingestTool = {
  name: "hybrid_graphrag_ingest",
  description: "Ingest a document or memory into the BrainClaw system (PG + Weaviate + Neo4j).",
  parameters: Type.Object({
    content: Type.String({ description: "The text content to ingest" }),
    memory_class: Type.Optional(Type.String({ description: "Optional memory classification tag" })),
    metadata: Type.Optional(Type.Any({ description: "Optional metadata to store with the document" })),
    tenant_id: Type.Optional(Type.String({ description: "Optional tenant identifier" })),
    agent_id: Type.Optional(Type.String({ description: "Optional agent identifier" }))
  }),
  async execute(_id: string, params: any, ctx: any) {
    const config = ctx.config || {};
    try {
      // Prepare the ingestion event for the Python backend
      const event = {
        content: params.content,
        memory_class: params.memory_class || "general",
        metadata: params.metadata || {},
        tenant_id: params.tenant_id || "default",
        agent_id: params.agent_id || "system"
      };

      // Call the ingestion pipeline in Python
      const result = await callPythonBackend("bridge_entrypoints", "ingest_event", {
        event: event
      }, config, ctx);

      return {
        content: [
          {
            type: "text",
            text: `Ingestion successful. ID: ${result.id || "N/A"}, Status: ${result.status || "SAVED"}`
          }
        ]
      };
    } catch (error: any) {
      return {
        content: [
          {
            type: "text",
            text: `Error executing ingestion: ${error.message}`
          }
        ],
        isError: true
      };
    }
  }
};

/**
 * Register the ingest tool.
 */
export function registerIngestTool(api: any) {
  api.registerTool(ingestTool);
}
