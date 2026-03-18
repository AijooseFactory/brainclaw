/**
 * Background service for community summarization.
 */
export declare const summarizerService: {
    id: string;
    description: string;
    start(ctx: any): {
        stop(): void;
    };
};
export declare function registerSummarizerService(api: any): void;
