import { spawn as cpSpawn } from "child_process";
import * as path from "path";
import * as fs from "fs";
import { fileURLToPath } from "url";
import { validateRouting, warnIfPlaintextSecret, validateTenantUrl } from "./validation.js";
import { sanitizeError, redactConfigForLogs } from "./sanitization.js";
import { getLogger, classifyError, ErrorCategory } from "./logging.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import * as crypto from "crypto";

function optionalContextValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function canonicalTokenSegment(value: string | undefined): string {
  return value ?? "";
}

function parseBackendJsonOutput(stdout: string): any {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new Error("Python backend returned empty output");
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    const lines = trimmed
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const candidate = lines[index];
      if (!candidate.startsWith("{") && !candidate.startsWith("[")) {
        continue;
      }
      try {
        return JSON.parse(candidate);
      } catch {
        // Continue scanning for the last valid JSON payload.
      }
    }
    throw new Error(`Failed to parse Python output: ${stdout}`);
  }
}

/**
 * Internal reference that can be overridden for tests.
 */
let spawnInstance = cpSpawn;

/**
 * For testing purposes only: allows overriding the child_process.spawn implementation.
 */
export function setSpawn(fn: any) {
  spawnInstance = fn;
}

/**
 * Bridge between TypeScript plugin and Python GraphRAG backend.
 * Uses structured logging for OpenClaw self-improvement.
 */
export async function callPythonBackend(
  module: string, 
  funct: string, 
  params: any, 
  config: Record<string, any> = {},
  ctx: any = {}
): Promise<any> {
  const startTime = Date.now();
  const logger = getLogger();
  
  return new Promise((resolve, reject) => {
    // 1. Security Check: Routing Allowlist
    if (!validateRouting(module, funct)) {
      const error = new Error(`Security Block: Unauthorized backend call to ${module}.${funct}`);
      logger.security('bridge', 'validateRouting', error.message, { module, funct });
      return reject(error);
    }

    // 2. Resource Management: Python paths (configurable)
    // Priority: config > env var > bundled > development fallback
    let pythonBackendPath: string;
    let pythonExecutable: string;
    
    // Get Python backend path (required for production)
    pythonBackendPath = config.pythonBackendPath || process.env.OPENCLAW_PYTHON_BACKEND || '';
    
    if (!pythonBackendPath) {
      // Try bundled Python first (production)
      const bundledPath = path.join(__dirname, "../python/openclaw_memory");
      if (fs.existsSync(bundledPath)) {
        pythonBackendPath = bundledPath;
        logger.info('bridge', 'config', 'Using bundled Python backend', { path: bundledPath });
      } else {
        // Development fallback: try monorepo structure
        const rootDir = path.resolve(__dirname, "../../..");
        const devPath = path.join(rootDir, "packages/openclaw-memory/src");
        if (fs.existsSync(devPath)) {
          pythonBackendPath = devPath;
          logger.info('bridge', 'config', 'Using development Python backend path', { path: devPath });
        } else {
          const error = new Error('pythonBackendPath is required. Set in plugin config, OPENCLAW_PYTHON_BACKEND env var, or run scripts/bundle-python.sh');
          logger.error('bridge', 'config', error, { 
            hint: 'Add pythonBackendPath to plugin configuration or run scripts/bundle-python.sh to bundle the Python backend' 
          });
          return reject(error);
        }
      }
    }
    
    // Get Python executable (defaults to system python3)
    pythonExecutable = config.pythonPath || process.env.OPENCLAW_PYTHON || 'python3';

    // 3. Security Check: Configuration and Secrets
    if (!validateTenantUrl(config.postgresUrl)) {
      getLogger().security('bridge', 'validateConfig', 
        `Tenant DB URL for postgres might be outside the allowed hosts list`,
        { url: config.postgresUrl ? '[REDACTED]' : 'undefined' });
    }
    
    warnIfPlaintextSecret("postgresUrl", config.postgresUrl);
    warnIfPlaintextSecret("neo4jPassword", config.neo4jPassword);

    // 4. Secure Identity Token (BRAINCLAW V2)
    // Create a signed HMAC token to prevent identity spoofing in the Python backend
    const brainclawSecret = config.brainclawSecret || process.env.BRAINCLAW_SECRET;
    if (!brainclawSecret) {
      throw new Error(
        '[BrainClaw] BRAINCLAW_SECRET is required but not configured. ' +
        'Set brainclawSecret in plugin config or the BRAINCLAW_SECRET environment variable. ' +
        'Refusing to start with an unsigned identity token.'
      );
    }

    const agentContext = {
      agentId: optionalContextValue(ctx.agentId),
      agentName: optionalContextValue(ctx.agentName),
      teamId: optionalContextValue(ctx.teamId),
      tenantId:
        optionalContextValue(ctx.tenantId) ||
        optionalContextValue(config.tenantId) ||
        optionalContextValue(process.env.OPENCLAW_TENANT_ID),
      timestamp: Date.now()
    };

    const message = [
      canonicalTokenSegment(agentContext.agentId),
      canonicalTokenSegment(agentContext.agentName),
      canonicalTokenSegment(agentContext.teamId),
      canonicalTokenSegment(agentContext.tenantId),
      String(agentContext.timestamp),
    ].join(":");
    const hmac = crypto.createHmac('sha256', brainclawSecret);
    hmac.update(message);
    const signature = hmac.digest('hex');
    const identityPayload = Object.fromEntries(
      Object.entries(agentContext).filter(([, value]) => value !== undefined),
    );
    const identityToken = Buffer.from(JSON.stringify({ ...identityPayload, signature })).toString('base64');

    const bridgeScript = `
import sys
import json
import dataclasses
from enum import Enum
import os
import base64
sys.path.append("${pythonBackendPath}")

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)

try:
    # BrainClaw V2: Identity Verification
    from openclaw_memory.security.access_control import verify_identity_token
    
    token = os.getenv("BRAINCLAW_IDENTITY_TOKEN")
    secret = os.getenv("BRAINCLAW_SECRET")
    
    # Verify and set global context
    context = verify_identity_token(token, secret)
    
    from openclaw_memory.${module} import ${funct}
    
    # Execute the requested function with params
    result = ${funct}(**json.loads(sys.argv[1]))
    print(json.dumps(result, cls=EnhancedJSONEncoder))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
`;

    // Prepare environment variables for the Python process
    // This allows BrainClaw to be 100% adaptive to OpenClaw configurations
    const pythonEnv = {
      ...process.env,
      // Map OpenClaw config to backend expectations
      POSTGRES_URL: config.postgresUrl || process.env.POSTGRES_URL,
      WEAVIATE_URL: config.weaviateUrl || process.env.WEAVIATE_URL,
      NEO4J_URL: config.neo4jUrl || process.env.NEO4J_URL,
      NEO4J_PASSWORD: config.neo4jPassword || process.env.NEO4J_PASSWORD,
      
      // Inject OpenClaw Agent Context (V2: Signed Token)
      BRAINCLAW_IDENTITY_TOKEN: identityToken,
      BRAINCLAW_SECRET: brainclawSecret,
      
      // Legacy context (for backwards compatibility during migration)
      ...(agentContext.agentId ? { AGENT_ID: agentContext.agentId } : {}),
      ...(agentContext.agentName ? { AGENT_NAME: agentContext.agentName } : {}),
      ...(agentContext.teamId ? { TEAM_ID: agentContext.teamId } : {}),
      
      // Pass the backend path explicitly to sys.path
      OPENCLAW_PYTHON_BACKEND: pythonBackendPath
    };

    const pythonProcess = spawnInstance(pythonExecutable, ["-c", bridgeScript, JSON.stringify(params)], {
      env: pythonEnv
    });

    // 4. Resource Management: Lifecycle & Timeout
    const timeoutMs = config.pythonTimeoutMs || 30000;
    const timeout = setTimeout(() => {
      pythonProcess.kill('SIGTERM');
      const error = new Error(`Timeout: Python backend call to ${module}.${funct} exceeded ${timeoutMs}ms.`);
      const classified = logger.error('bridge', 'timeout', error, { module, funct, timeoutMs });
      logger.timing('bridge', 'callPythonBackend', Date.now() - startTime, { module, funct, result: 'timeout' });
      reject(error);
    }, timeoutMs);

    let stdout = "";
    let stderr = "";

    pythonProcess.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    pythonProcess.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    pythonProcess.on("close", (code) => {
      clearTimeout(timeout);
      const duration = Date.now() - startTime;
      
      if (code !== 0) {
        const errorMsg = `Python process exited with code ${code}. Stderr: ${stderr}`;
        const error = new Error(sanitizeError(errorMsg));
        const classified = logger.error('bridge', 'pythonExit', error, { module, funct, exitCode: code });
        logger.timing('bridge', 'callPythonBackend', duration, { module, funct, result: 'error', category: classified.category });
        reject(error);
      } else {
        try {
          const parsedResult = parseBackendJsonOutput(stdout);
          if (parsedResult.error) {
            const error = new Error(sanitizeError(parsedResult.error));
            const classified = logger.error('bridge', 'pythonError', error, { module, funct });
            logger.timing('bridge', 'callPythonBackend', duration, { module, funct, result: 'error' });
            reject(error);
          } else {
            logger.timing('bridge', 'callPythonBackend', duration, { module, funct, result: 'success' });
            resolve(parsedResult);
          }
        } catch (e) {
          const message = e instanceof Error ? e.message : `Failed to parse Python output: ${stdout}`;
          const error = new Error(sanitizeError(message));
          const classified = logger.error('bridge', 'parseError', error, { module, funct });
          logger.timing('bridge', 'callPythonBackend', duration, { module, funct, result: 'error' });
          reject(error);
        }
      }
    });

    pythonProcess.on("error", (err) => {
      clearTimeout(timeout);
      const error = new Error(sanitizeError(err));
      const classified = logger.error('bridge', 'processError', error, { module, funct });
      logger.timing('bridge', 'callPythonBackend', Date.now() - startTime, { module, funct, result: 'error', category: classified.category });
      reject(error);
    });
  });
}
