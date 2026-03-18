/**
 * BrainClaw Contradiction Check Tool Definition.
 */
export declare const contradictionCheckTool: {
    name: string;
    description: string;
    parameters: import("@sinclair/typebox").TObject<{
        entity_name: import("@sinclair/typebox").TOptional<import("@sinclair/typebox").TString>;
        tenant_id: import("@sinclair/typebox").TOptional<import("@sinclair/typebox").TString>;
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
 * Register the contradiction check tool.
 */
export declare function registerContradictionTool(api: any): void;
