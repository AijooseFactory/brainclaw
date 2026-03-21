# BrainClaw Testing Harness

A comprehensive testing utility for BrainClaw Hybrid GraphRAG memory system. Generate reproducible synthetic data for benchmarking, testing retrieval quality, and benchmarking graph densification experiments.

---

## Overview

The BrainClaw Testing Harness provides a Python API for generating synthetic test data across the three storage layers:

- **PostgreSQL**: Canonical memory items with temporal versioning
- **Weaviate**: Semantic embedding vectors for hybrid retrieval
- **Neo4j**: Knowledge graph with entities, relationships, and community structures

### What It Provides

| Feature | Description |
|---------|-------------|
| **Synthetic Documents** | Generate structured test documents with configurable entity density |
| **Contradictory Pairs** | Create intentional contradictions to test BrainClaw's self-healing |
| **Entity-Rich Documents** | Dense graphs with high edge-to-node ratios for stress testing |
| **Graph Densification** | Replicate benchmark conditions (1,617:1 edge-to-node ratio) |
| **Seed Reproducibility** | Deterministic data generation for reproducible tests |

---

## Installation

### Prerequisites

```bash
# BrainClaw requires Python 3.11+
python --version  # Must be 3.11 or higher

# Required backend services
- PostgreSQL 15+ (canonical storage)
- Weaviate 1.24+ (semantic retrieval)
- Neo4j 5.14+ (graph reasoning)
```

### Install BrainClaw

```bash
# Clone or navigate to the BrainClaw package
cd /path/to/brainclaw

# Install Python dependencies
pip install -r requirements.txt

# Install BrainClaw Python module
pip install -e python/

# Verify installation
python -c "from openclaw_memory.testing.harness import SyntheticDataConfig; print('OK')"
```

### Environment Configuration

Set required environment variables:

```bash
export POSTGRES_URL="postgresql://brainclaw:brainclaw@localhost:5432/brainclaw_test"
export WEAVIATE_URL="http://localhost:8080"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"
export NEO4J_DATABASE="neo4j"
```

---

## Quick Start

### Minimal Example: Generate Test Data

```python
from openclaw_memory.testing.harness import (
    generate_synthetic_documents,
    SyntheticDataConfig
)

# Configure for 100 documents with 10 entities each
config = SyntheticDataConfig(
    num_documents=100,
    entities_per_document=10,
    relationships_per_entity=5,
    seed=42  # Reproducible output
)

# Generate and ingest into BrainClaw
documents = generate_synthetic_documents(config)

print(f"Generated {len(documents)} documents")
for doc in documents[:3]:
    print(f"  - {doc['id']}: {doc['title']}")
```

### Run the Quick Benchmark

```bash
# From the BrainClaw package directory
cd /home/node/Mac/data/usr/projects/ai_joose_factory/packages/brainclaw

# Run the benchmark script
./scripts/run_benchmark.sh

# Results saved to benchmark_results.json
cat benchmark_results.json | python -m json.tool
```

---

## API Reference

### `generate_synthetic_documents(config: SyntheticDataConfig) -> List[dict]`

Generate structured synthetic documents for testing BrainClaw's hybrid retrieval.

#### Parameters

| Parameter | Type | Default | Description |
|------------|------|---------|-------------|
| `config` | `SyntheticDataConfig` | Required | Configuration object |
| `config.num_documents` | `int` | 10 | Number of documents to generate |
| `config.entities_per_document` | `int` | 5 | Average entities per document |
| `config.relationships_per_entity` | `int` | 3 | Average relationships per entity |
| `config.include_metadata` | `bool` | True | Include timestamp, source metadata |
| `config.seed` | `int` | None | Random seed for reproducibility |

#### Return Type

```python
List[dict]  # Each document is a dictionary with:
# {
#     "id": "doc_0a1b2c3d",
#     "title": "Synthetic Document Title",
#     "content": "Full text content with entities...",
#     "entities": [{"name": "Entity", "type": "CONCEPT", ...}],
#     "relationships": [(source, target, type), ...],
#     "metadata": {"created_at": "2026-03-21T...", "source": "synthetic"}
# }
```

#### Example

```python
from openclaw_memory.testing.harness import generate_synthetic_documents, SyntheticDataConfig

# Generate 50 test documents with moderate complexity
config = SyntheticDataConfig(
    num_documents=50,
    entities_per_document=8,
    relationships_per_entity=4,
    seed=12345
)

docs = generate_synthetic_documents(config)

# Ingest into BrainClaw (requires bridge import)
from openclaw_memory.bridge_entrypoints import ingest_documents

results = ingest_documents(docs)
print(f"Ingested {results['success_count']} documents")
```

---

### `generate_contradictory_documents(config: SyntheticDataConfig) -> List[dict]`

Generate document pairs with intentional contradictions to test BrainClaw's self-healing and contradiction detection.

#### Parameters

Same as `generate_synthetic_documents` with additional options:

| Parameter | Type | Default | Description |
|------------|------|---------|-------------|
| `config.contradiction_rate` | `float` | 0.1 | Percentage of documents with contradictions (0.0-1.0) |
| `config.contradiction_types` | `List[str]` | ["numeric", "temporal", "categorical"] | Types of contradictions to introduce |

#### Return Type

```python
List[dict]  # Returns documents with contradiction flag:
# {
#     "id": "doc_contradiction_001",
#     "has_contradiction": True,
#     "contradiction_type": "numeric",
#     "contradicts_document": "doc_002",  # ID of contradicting doc
#     "original_value": "42",
#     "contradicted_value": "100",
#     ...
# }
```

#### Example

```python
from openclaw_memory.testing.harness import generate_contradictory_documents, SyntheticDataConfig

# Generate documents with 20% containing contradictions
config = SyntheticDataConfig(
    num_documents=30,
    entities_per_document=5,
    contradiction_rate=0.2,
    contradiction_types=["numeric", "temporal"],
    seed=999
)

docs = generate_contradictory_documents(config)

# Analyze contradiction detection
contradictions = [d for d in docs if d.get("has_contradiction")]
print(f"Generated {len(contradictions)} documents with contradictions")

# Run BrainClaw's contradiction check
from openclaw_memory.audit.contradiction import detect_contradictions
results = detect_contradictions([d["id"] for d in docs])
print(f"Detected {len(results)} contradictions")
```

---

### `generate_entity_rich_documents(config: SyntheticDataConfig) -> List[dict]`

Generate dense entity-rich documents for stress testing graph relationships and high-bandwidth retrieval scenarios.

#### Parameters

| Parameter | Type | Default | Description |
|------------|------|---------|-------------|
| `config.num_documents` | `int` | 10 | Number of documents |
| `config.entities_per_document` | `int` | 50 | High entity density |
| `config.relationships_per_entity` | `int` | 20 | Dense relationship graph |
| `config.entity_types` | `List[str]` | All types | Entity type distribution |
| `config.seed` | `int` | None | Random seed |

#### Return Type

```python
List[dict]  # Each document with dense entity/relationship graphs:
# {
#     "id": "doc_dense_001",
#     "content": "...",
#     "entities": [{"name": "Entity", "type": "PERSON", ...}, ...],
#     "relationships": [...],  # Potentially 1000+ relationships
#     "graph_metrics": {
#         "total_entities": 50,
#         "total_relationships": 980,
#         "edge_node_ratio": 19.6
#     }
# }
```

#### Example

```python
from openclaw_memory.testing.harness import generate_entity_rich_documents, SyntheticDataConfig

# Generate dense graph for stress testing
config = SyntheticDataConfig(
    num_documents=20,
    entities_per_document=100,  # High density
    relationships_per_entity=30,
    seed=777
)

docs = generate_entity_rich_documents(config)

# Calculate resulting graph metrics
total_entities = sum(len(d.get("entities", [])) for d in docs)
total_relationships = sum(len(d.get("relationships", [])) for d in docs)
edge_node_ratio = total_relationships / total_entities if total_entities > 0 else 0

print(f"Total entities: {total_entities}")
print(f"Total relationships: {total_relationships}")
print(f"Edge-to-node ratio: {edge_node_ratio:.1f}:1")
```

---

### `SyntheticDataConfig`

Configuration dataclass for synthetic data generation.

#### Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `num_documents` | `int` | 10 | Number of documents to generate |
| `entities_per_document` | `int` | 5 | Average entities per document |
| `relationships_per_entity` | `int` | 3 | Average relationships per entity |
| `entity_types` | `List[str]` | ["PERSON", "ORGANIZATION", "LOCATION", "CONCEPT", "EVENT", "TECHNOLOGY"] | Available entity types |
| `relationship_types` | `List[str]` | ["KNOWS", "WORKS_AT", "LOCATED_IN", "RELATED_TO", "USES", "CREATED", "PARTICIPATES_IN"] | Available relationship types |
| `contradiction_rate` | `float` | 0.0 | Proportion with contradictions (0.0-1.0) |
| `contradiction_types` | `List[str]` | ["numeric", "temporal", "categorical"] | Types of contradictions |
| `seed` | `int` | None | Random seed for reproducibility |
| `include_metadata` | `bool` | True | Include timestamp and source metadata |
| `content_template` | `str` | None | Custom content template |
| `tenant_id` | `str` | "default" | Tenant identifier for multi-tenancy |

#### Example: Full Configuration

```python
from openclaw_memory.testing.harness import SyntheticDataConfig

config = SyntheticDataConfig(
    # Document generation
    num_documents=100,
    entities_per_document=15,
    relationships_per_entity=8,
    
    # Domain configuration
    entity_types=["PERSON", "ORGANIZATION", "TECHNOLOGY", "CONCEPT"],
    relationship_types=["DEVELOPS", "COLLABORATES_WITH", "USES", "DEPENDS_ON"],
    
    # Contradiction testing
    contradiction_rate=0.15,
    contradiction_types=["numeric", "categorical"],
    
    # Reproducibility
    seed=20260321,
    include_metadata=True,
    
    # Multi-tenancy
    tenant_id="acme_corp"
)
```

---

## Graph Densification Experiments

Replicate BrainClaw's benchmark conditions (1,617:1 edge-to-node ratio) for retrieval performance testing.

### Understanding Graph Density

| Benchmark Level | Nodes | Edges | Edge-to-Node Ratio |
|-----------------|-------|-------|---------------------|
| Low Density | 100 | 300 | 3:1 |
| Medium Density | 100 | 1,000 | 10:1 |
| High Density | 100 | 10,000 | 100:1 |
| **Benchmark (v1.6.0)** | **766** | **1,238,953** | **1,617:1** |

### Running Densification Benchmark

```python
from openclaw_memory.testing.harness import (
    generate_entity_rich_documents,
    SyntheticDataConfig,
    create_densification_test
)
from openclaw_memory.bridge_entrypoints import ingest_documents
from openclaw_memory.graph.health import get_health_stats

# Step 1: Generate dense graph matching benchmark conditions
# To achieve 1,617:1 ratio with ~766 nodes:
# 766 nodes * 1617 edges = 1,237,482 edges (~1.2M target)
config = SyntheticDataConfig(
    num_documents=50,
    entities_per_document=15,  # ~750 total entities
    relationships_per_entity=108,  # Achieve ~1,600:1 ratio
    seed=42
)

print("Generating entity-rich documents...")
docs = generate_entity_rich_documents(config)

print(f"Generated {len(docs)} documents")
print(f"Total entities: {sum(len(d.get('entities', [])) for d in docs)}")
print(f"Total relationships: {sum(len(d.get('relationships', [])) for d in docs)}")

# Step 2: Ingest into BrainClaw
print("\nIngesting into BrainClaw...")
results = ingest_documents(docs)
print(f"Ingested: {results['success_count']} success, {results['failure_count']} failed")

# Step 3: Verify graph health
print("\nChecking graph health...")
stats = get_health_stats()
print(f"  Status: {stats['status']}")
print(f"  Nodes: {stats['node_count']}")
print(f"  Edges: {stats['edge_count']}")
print(f"  Communities: {stats['community_count']}")

# Calculate achieved ratio
if stats['node_count'] > 0:
    ratio = stats['edge_count'] / stats['node_count']
    print(f"  Edge-to-node ratio: {ratio:.1f}:1")
```

### Automated Benchmark Script

```bash
#!/bin/bash
# graph_densification_benchmark.sh

set -e

CONFIG=(
    "num_documents=50"
    "entities_per_document=15"
    "relationships_per_entity=108"
    "seed=42"
)

echo "=== Graph Densification Benchmark ==="
echo "Target: 1,617:1 edge-to-node ratio"
echo ""

# Generate and ingest
python3 << 'EOF'
import os
import sys
sys.path.insert(0, '/home/node/Mac/data/usr/projects/ai_joose_factory/packages/brainclaw/python')

from openclaw_memory.testing.harness import generate_entity_rich_documents, SyntheticDataConfig

config = SyntheticDataConfig(
    num_documents=50,
    entities_per_document=15,
    relationships_per_entity=108,
    seed=42
)

docs = generate_entity_rich_documents(config)

# Ingest
from openclaw_memory.bridge_entrypoints import ingest_documents
results = ingest_documents(docs)
print(f"Ingested: {results}")

# Check health
from openclaw_memory.graph.health import get_health_stats
stats = get_health_stats()

n = stats['node_count']
e = stats['edge_count']
ratio = e / n if n > 0 else 0

print(f"Nodes: {n}")
print(f"Edges: {e}")
print(f"Ratio: {ratio:.1f}:1")
EOF

echo ""
echo "=== Benchmark Complete ==="
```

---

## Complete Working Examples

### Example 1: Basic Retrieval Test

```python
"""Basic retrieval test with synthetic data."""
import sys
sys.path.insert(0, '/path/to/brainclaw/python')

from openclaw_memory.testing.harness import (
    generate_synthetic_documents,
    SyntheticDataConfig
)
from openclaw_memory.bridge_entrypoints import ingest_documents, hybrid_retrieve

# Generate test data
config = SyntheticDataConfig(
    num_documents=20,
    entities_per_document=6,
    relationships_per_entity=3,
    seed=42
)

print("Generating synthetic documents...")
docs = generate_synthetic_documents(config)

print(f"Ingesting {len(docs)} documents...")
result = ingest_documents(docs)
print(f"  Success: {result['success_count']}")
print(f"  Failed: {result['failure_count']}")

# Test retrieval
query = "artificial intelligence machine learning neural networks"
print(f"\nTesting retrieval with query: {query}")

results = hybrid_retrieve(
    query=query,
    mode="local",  # local, global, drift, lazy
    top_k=5,
    tenant_id="default"
)

print(f"\nTop {len(results)} results:")
for i, r in enumerate(results, 1):
    print(f"  {i}. {r.get('title', 'N/A')} (score: {r.get('score', 0):.3f})")
```

### Example 2: Contradiction Detection Test

```python
"""Test BrainClaw's self-healing contradiction detection."""
import sys
sys.path.insert(0, '/path/to/brainclaw/python')

from openclaw_memory.testing.harness import (
    generate_contradictory_documents,
    SyntheticDataConfig
)
from openclaw_memory.bridge_entrypoints import ingest_documents
from openclaw_memory.audit.contradiction import detect_contradictions

# Generate documents with contradictions
config = SyntheticDataConfig(
    num_documents=25,
    entities_per_document=4,
    contradiction_rate=0.2,  # 20% have contradictions
    contradiction_types=["numeric", "temporal"],
    seed=12345
)

print("Generating contradictory documents...")
docs = generate_contradictory_documents(config)

# Ingest
result = ingest_documents(docs)
print(f"Ingested: {result['success_count']} documents")

# Run contradiction detection
print("\nRunning contradiction detection...")
contradictions = detect_contradictions(
    tenant_id="default",
    min_confidence=0.7
)

print(f"Found {len(contradictions)} contradictions:")
for c in contradictions:
    print(f"  - {c['type']}: {c['entity_a']} vs {c['entity_b']}")
    print(f"    Confidence: {c['confidence']:.2f}")
```

### Example 3: Full Benchmark Suite

```python
"""Complete benchmark suite for BrainClaw performance testing."""
import sys
import time
import json
sys.path.insert(0, '/path/to/brainclaw/python')

from openclaw_memory.testing.harness import (
    generate_synthetic_documents,
    generate_entity_rich_documents,
    SyntheticDataConfig
)
from openclaw_memory.bridge_entrypoints import ingest_documents, hybrid_retrieve
from openclaw_memory.graph.health import get_health_stats

def benchmark_ingestion(num_docs, entities_per_doc, relationships_per_entity, seed):
    """Benchmark document ingestion."""
    config = SyntheticDataConfig(
        num_documents=num_docs,
        entities_per_document=entities_per_doc,
        relationships_per_entity=relationships_per_entity,
        seed=seed
    )
    
    docs = generate_entity_rich_documents(config)
    
    start = time.time()
    result = ingest_documents(docs)
    elapsed = time.time() - start
    
    return {
        "document_count": len(docs),
        "success_count": result["success_count"],
        "failure_count": result["failure_count"],
        "elapsed_seconds": round(elapsed, 2),
        "docs_per_second": round(len(docs) / elapsed, 2) if elapsed > 0 else 0
    }

def benchmark_retrieval(query, mode, iterations=10):
    """Benchmark retrieval latency."""
    latencies = []
    
    for _ in range(iterations):
        start = time.time()
        results = hybrid_retrieve(query=query, mode=mode, top_k=5)
        elapsed = (time.time() - start) * 1000  # ms
        latencies.append(elapsed)
    
    return {
        "query": query,
        "mode": mode,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
        "min_latency_ms": round(min(latencies), 2),
        "max_latency_ms": round(max(latencies), 2),
        "iterations": iterations
    }

def run_benchmark_suite():
    """Run complete benchmark suite."""
    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "graph_health": get_health_stats(),
        "ingestion_benchmarks": [],
        "retrieval_benchmarks": []
    }
    
    # Test various scales
    for scale in [(10, 5, 3), (50, 10, 8), (100, 15, 12)]:
        print(f"Benchmarking ingestion at scale {scale}...")
        bench = benchmark_ingestion(*scale, seed=42)
        results["ingestion_benchmarks"].append(bench)
        print(f"  {bench['docs_per_second']} docs/sec")
    
    # Test retrieval modes
    queries = [
        "machine learning neural networks",
        "software development DevOps",
        "data science analytics"
    ]
    
    for query in queries:
        for mode in ["local", "global", "drift"]:
            print(f"Benchmarking retrieval: {query} ({mode})...")
            bench = benchmark_retrieval(query, mode)
            results["retrieval_benchmarks"].append(bench)
            print(f"  Avg latency: {bench['avg_latency_ms']}ms")
    
    # Save results
    with open("benchmark_suite_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n=== Benchmark Complete ===")
    print(f"Results saved to: benchmark_suite_results.json")
    return results

if __name__ == "__main__":
    run_benchmark_suite()
```

---

## Seed Reproducibility

BrainClaw's testing harness uses seeded random generation to ensure reproducible test data across runs.

### How Seeds Work

```python
from openclaw_memory.testing.harness import SyntheticDataConfig, generate_synthetic_documents

# Same seed = identical output
config1 = SyntheticDataConfig(num_documents=10, seed=42)
config2 = SyntheticDataConfig(num_documents=10, seed=42)

docs1 = generate_synthetic_documents(config1)
docs2 = generate_synthetic_documents(config2)

# Verify reproducibility
assert docs1[0]["id"] == docs2[0]["id"], "Seed reproducibility failed!"
print("✓ Same seed produces identical documents")
```

### Seed Best Practices

| Scenario | Recommended Seed Strategy |
|----------|--------------------------|
| Unit tests | Fixed seed (e.g., `seed=12345`) |
| Integration tests | Environment variable seed |
| CI/CD benchmarks | Timestamp-based seed, log for reproducibility |
| Debugging failures | Fixed seed from failed run (log the seed!) |

### Reproducible Benchmarking in CI

```yaml
# .github/workflows/benchmark.yml
name: BrainClaw Benchmark

on:
  schedule:
    - cron: '0 0 * * *'  # Daily
  push:
    branches: [main]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run benchmark with fixed seed
        run: |
          # Log seed for reproducibility
          SEED=$(date +%Y%m%d)
          echo "Benchmark seed: $SEED"
          
          # Run with tracked seed
          python3 run_benchmark.py --seed $SEED
          
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: benchmark_results.json
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: No module named 'openclaw_memory'` | Python path not set | Add BrainClaw to PYTHONPATH or install with `pip install -e` |
| `ConnectionError: Neo4j unreachable` | Neo4j not running | Start Neo4j: `docker compose up -d neo4j` |
| `contradiction_rate must be 0.0-1.0` | Invalid config | Ensure `contradiction_rate` is between 0 and 1 |
| `Seed not integer` | Wrong seed type | Use integer seeds: `seed=42`, not `seed="42"` |

### Getting Help

- **Documentation**: See [README.md](../README.md) and [BENCHMARK.md](../BENCHMARK.md)
- **Issues**: Report at https://github.com/aijoosefactory/brainclaw/issues
- **Discussions**: Join the discussion at https://github.com/aijoosefactory/brainclaw/discussions