# BrainClaw Plugin for OpenClaw

BrainClaw is a Hybrid GraphRAG plugin for OpenClaw that serves as its memory and knowledge system. It enables OpenClaw agents to retain, learn from, and retrieve context across conversations and sessions, with enterprise-grade observability, automatic summarization, and active learning capabilities.

## Features

- **Multi-store Retrieval**: PostgreSQL (canonical), Weaviate (vector), Neo4j (graph)
- **Community Detection**: Leiden algorithm for hierarchical clustering
- **Audit Ledger**: Immutable audit trail for compliance
- **Structured Logging**: Error categorization for self-improvement

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Plugin

Add to your `openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "brainclaw": {
        "enabled": true,
        "postgresUrl": "${POSTGRES_URL}",
        "weaviateUrl": "${WEAVIATE_URL}",
        "neo4jUrl": "${NEO4J_URL}",
        "neo4jUser": "neo4j",
        "neo4jPassword": "${NEO4J_PASSWORD}",
        "pythonBackendPath": "/path/to/openclaw-memory/src"
      }
    }
  }
}
```

### 3. Bundle Python Backend (Production)

For production deployment, bundle the Python backend into the plugin:

```bash
npm run bundle
# or
./scripts/bundle-python.sh
```

This creates `python/openclaw_memory/` with the bundled backend.

## Configuration

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `postgresUrl` | Yes | - | PostgreSQL connection URL |
| `weaviateUrl` | Yes | - | Weaviate connection URL |
| `neo4jUrl` | Yes | - | Neo4j connection URL |
| `neo4jUser` | No | `neo4j` | Neo4j username |
| `neo4jPassword` | No | - | Neo4j password |
| `pythonPath` | No | `python3` | Python executable path |
| `pythonBackendPath` | No | bundled | Path to openclaw-memory package |
| `pythonTimeoutMs` | No | `30000` | Timeout for Python calls (ms) |
| `embeddingModel` | No | - | Embedding model name |
| `extractionModel` | No | - | Extraction model name |
| `enableAuditLedger` | No | `true` | Enable audit ledger |
| `enableCommunityDetection` | No | `true` | Enable community detection |

## Path Resolution

The plugin resolves Python backend paths in this order:

1. `config.pythonBackendPath` (highest priority)
2. `process.env.OPENCLAW_PYTHON_BACKEND`
3. Bundled: `python/openclaw_memory/`
4. Development: `packages/openclaw-memory/src/`

## Security

- **Tenant Isolation**: URL allowlist prevents data exfiltration
- **Code Injection Prevention**: Module/function routing allowlist
- **Credential Protection**: Sensitive fields marked, plaintext warnings
- **Error Sanitization**: User paths stripped from error messages

## Development

```bash
# Build
npm run build

# Test
npm test

# Bundle Python
npm run bundle
```

## License

MIT
