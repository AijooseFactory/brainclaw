import { callPythonBackend } from "../bridge.js";
import { getLogger } from "../logging.js";

/**
 * Service for managing Continual Intelligence and Knowledge Distillation.
 * (Phase 12: Lazy and Recursive Wisdom)
 */
export class IntelligenceService {
  /**
   * Run knowledge distillation for a tenant.
   * Synthesizes 'Knowledge Items' (KIs) from meaningful community patterns.
   */
  async distill(tenantId?: string, config: any = {}, ctx: any = {}): Promise<any> {
    const logger = getLogger();
    logger.info('intelligence', 'distill', 'Starting knowledge distillation', { tenantId });
    
    try {
      const result = await callPythonBackend(
        'bridge_entrypoints',
        'intel_distill',
        { tenant_id: tenantId },
        config,
        ctx
      );
      
      logger.info('intelligence', 'distill', 'Knowledge distillation complete', { 
        count: result.distilled_count 
      });
      return result;
    } catch (error) {
      logger.error('intelligence', 'distill', error as Error, { tenantId });
      throw error;
    }
  }

  /**
   * Record memory promotions to trigger lazy distillation.
   * Increments the promotion counter in the distiller state.
   */
  async recordPromotion(count: number = 1, config: any = {}, ctx: any = {}): Promise<any> {
    const logger = getLogger();
    try {
      const result = await callPythonBackend(
        'bridge_entrypoints',
        'intel_record_promotion',
        { count },
        config,
        ctx
      );
      return result;
    } catch (error) {
      logger.error('intelligence', 'recordPromotion', error as Error, { count });
      // Don't throw, just log - recording promotions shouldn't block main flow
      return { status: "error", error: (error as Error).message };
    }
  }
}

/**
 * Register the Intelligence Service for background distillation.
 * Phase 12: Runs on a 'Lazy' schedule or triggered by memory promotions.
 */
export function registerIntelligenceService(api: any) {
  const service = new IntelligenceService();
  const logger = getLogger();
  
  // Every 4 hours, check if distillation is needed (Lazy Trigger)
  setInterval(async () => {
    try {
      const config = api.config || {};
      const ctx = api.context || {};
      await service.distill(undefined, config, ctx);
    } catch (error) {
      // Silent fail for background tasks unless critical
      logger.error('intelligence', 'backgroundDistill', error as Error);
    }
  }, 4 * 60 * 60 * 1000); // 4 hours
}
