import { IntelligenceService } from "../services/intelligence.js";

/**
 * Register the intel_distill tool.
 * Phase 12: Manually trigger knowledge distillation.
 */
export function registerIntelDistillTool(api: any) {
  const service = new IntelligenceService();
  
  api.registerTool({
    name: "intel_distill",
    description: "Manually trigger knowledge distillation to synthesize 'Knowledge Items' (KIs) from recent memory patterns and communities. This represents Phase 12 'Continual Intelligence'.",
    parameters: {
      type: "object",
      properties: {
        tenantId: {
          type: "string",
          description: "The tenant ID to distill knowledge for (optional)."
        }
      }
    },
    execute: async (params: any, ctx: any) => {
      // api.config contains the plugin configuration
      return await service.distill(params.tenantId, api.config || {}, ctx);
    }
  });
}
