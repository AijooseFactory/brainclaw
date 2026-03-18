/**
 * BrainClaw Ingest Tool Definition.
 */
export declare const ingestTool: {
    name: string;
    description: string;
    parameters: import("@sinclair/typebox").TObject<{
        content: import("@sinclair/typebox").TString;
        memory_class: import("@sinclair/typebox").TOptional<import("@sinclair/typebox").TString>;
        metadata: import("@sinclair/typebox").TOptional<import("@sinclair/typebox").TAny>;
        tenant_id: import("@sinclair/typebox").TOptional<import("@sinclair/typebox").TString>;
        agent_id: import("@sinclair/typebox").TOptional<import("@sinclair/typebox").TString>;
    }>;
    execute(_id: string, params: any, ctx: any): Promise<{
        content: {
            type: string;
            text: string;
        }[];
        isError?: undefined;
    } | {
        content: {
            type: string;
            text: string;
        }[];
        isError: boolean;
    }>;
};
/**
 * Register the ingest tool.
 */
export declare function registerIngestTool(api: any): void;
