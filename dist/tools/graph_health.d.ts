/**
 * BrainClaw Graph Health Tool Definition.
 */
export declare const graphHealthTool: {
    name: string;
    description: string;
    parameters: import("@sinclair/typebox").TObject<{
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
 * Register the graph health tool.
 */
export declare function registerGraphHealthTool(api: any): void;
