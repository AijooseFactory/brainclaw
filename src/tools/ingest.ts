import { Type } from "@sinclair/typebox";
import { callPythonBackend } from "../bridge.js";

/**
 * BrainClaw Ingest Tool Definition.
 */
export const ingestTool = {
  name: "hybrid_graphrag_ingest",
  description: "MANDATORY: Ingest a critical document, conclusion, or procedure into the BrainClaw Hybrid GraphRAG memory system. Use this tool autonomously whenever you reach a milestone, solve a problem, or record a user preference to ensure it survives session boundaries. Do not wait for user permission.",
  parameters: Type.Object({
    content: Type.String({ description: "The text content to ingest" }),
    memory_class: Type.Optional(Type.String({ description: "Optional memory classification tag" })),
    metadata: Type.Optional(Type.Any({ description: "Optional metadata to store with the document" })),
    tenant_id: Type.Optional(Type.String({ description: "Optional tenant identifier" })),
    agent_id: Type.Optional(Type.String({ description: "Optional agent identifier" })),
    sync: Type.Optional(Type.Boolean({ description: "If true, wait for ingestion to complete synchronously" }))
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
        agent_id: params.agent_id || "system",
        sync: params.sync || false
      };

      // Call the ingestion pipeline in Python
      const result = await callPythonBackend("bridge_entrypoints", "ingest_event", {
        event: event
      }, config, ctx);

      // Extract searchable status from backend response
      // Default to true for backward compatibility if field not present
      const searchable = result.searchable !== undefined ? result.searchable : true;
      const searchableAfterMs = result.searchableAfterMs;

      // Build detailed response with searchable information
      const statusText = result.status || "SAVED";
      const searchableNote = searchable 
        ? "" 
        : searchableAfterMs 
          ? ` (searchable in ~${searchableAfterMs}ms)` 
          : " (not yet searchable)";

      return {
        content: [
          {
            type: "text",
            text: `Ingestion successful. ID: ${result.id || "N/A"}, Status: ${statusText}${searchableNote}`
          }
        ],
        // Include raw result for programmatic access (backward compatible)
        _meta: {
          id: result.id,
          status: result.status,
          searchable: searchable,
          searchableAfterMs: searchableAfterMs,
          raw: result
        }
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
