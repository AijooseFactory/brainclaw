/**
 * Background service for audit ledger maintenance.
 */
export declare const auditLoggerService: {
    id: string;
    description: string;
    start(ctx: any): {
        stop(): void;
    };
};
export declare function registerAuditLoggerService(api: any): void;
