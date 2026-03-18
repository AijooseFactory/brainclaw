/**
 * For testing purposes only: allows overriding the child_process.spawn implementation.
 */
export declare function setSpawn(fn: any): void;
/**
 * Bridge between TypeScript plugin and Python GraphRAG backend.
 * Uses structured logging for OpenClaw self-improvement.
 */
export declare function callPythonBackend(module: string, funct: string, params: any, config?: Record<string, any>): Promise<any>;
