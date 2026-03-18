/**
 * BrainClaw Search Tool Definition.
 */
export declare const searchTool: {
    name: string;
    description: string;
    parameters: import("@sinclair/typebox").TObject<{
        query: import("@sinclair/typebox").TString;
        topK: import("@sinclair/typebox").TOptional<import("@sinclair/typebox").TNumber>;
        mode: import("@sinclair/typebox").TOptional<import("@sinclair/typebox").TUnion<[import("@sinclair/typebox").TLiteral<"local">, import("@sinclair/typebox").TLiteral<"global">, import("@sinclair/typebox").TLiteral<"hybrid">]>>;
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
 * Register the search tool.
 */
export declare function registerSearchTool(api: any): void;
