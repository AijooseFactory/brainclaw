"""
migrate_weaviate_schema.py — BrainClaw Weaviate Schema Migration

Adds `agent_id` property to existing Weaviate collections without
dropping or re-indexing data. Safe to run on live installations.

Usage:
    python -m openclaw_memory.storage.migrations.migrate_weaviate_schema
    python -m openclaw_memory.storage.migrations.migrate_weaviate_schema --dry-run
"""

import argparse
import os
import sys

COLLECTIONS = ["MemoryChunk", "Entity", "Decision", "Pattern", "EpisodicEvent"]
AGENT_ID_PROPERTY = {
    "name": "agent_id",
    "dataType": ["uuid"],
    "description": "Agent that owns this record (v1.5.0-intel-perfection multi-agent isolation)",
    "indexSearchable": False,
    "indexFilterable": True,
}


def get_client():
    """Connect to Weaviate."""
    try:
        import weaviate
        from weaviate.classes.init import Auth
    except ImportError:
        print("❌ weaviate-client not installed. Run: pip install weaviate-client")
        sys.exit(1)

    url = os.environ.get("WEAVIATE_URL", "http://localhost:8080")
    api_key = os.environ.get("WEAVIATE_API_KEY")

    if api_key:
        return weaviate.connect_to_custom(
            http_host=url.replace("http://", "").replace("https://", "").split(":")[0],
            http_port=int(url.split(":")[-1]) if ":" in url else 8080,
            http_secure=url.startswith("https"),
            grpc_host=url.replace("http://", "").replace("https://", "").split(":")[0],
            grpc_port=50051,
            grpc_secure=False,
            auth_credentials=Auth.api_key(api_key),
        )
    else:
        return weaviate.connect_to_local(
            host=url.replace("http://", "").split(":")[0],
            port=int(url.split(":")[-1]) if ":" in url else 8080,
        )


def collection_exists(client, name: str) -> bool:
    """Check if a collection exists."""
    try:
        client.collections.get(name)
        return True
    except Exception:
        return False


def property_exists(client, collection_name: str, prop_name: str) -> bool:
    """Check if a property already exists on a collection."""
    try:
        col = client.collections.get(collection_name)
        config = col.config.get()
        return any(p.name == prop_name for p in config.properties)
    except Exception:
        return False


def add_agent_id_property(client, collection_name: str, dry_run: bool = False):
    """Add agent_id to a Weaviate collection (non-destructive)."""
    if not collection_exists(client, collection_name):
        print(f"  ⚠️  Collection '{collection_name}' does not exist — skipping.")
        return

    if property_exists(client, collection_name, "agent_id"):
        print(f"  ✅ '{collection_name}' already has agent_id — no change needed.")
        return

    print(f"  {'[DRY-RUN] ' if dry_run else ''}Adding agent_id to '{collection_name}'...")
    if dry_run:
        return

    try:
        import weaviate.classes.config as wc
        col = client.collections.get(collection_name)
        col.config.add_property(
            wc.Property(
                name="agent_id",
                data_type=wc.DataType.UUID,
                description="Agent that owns this record (v1.5.0-intel-perfection isolation)",
                index_searchable=False,
                index_filterable=True,
            )
        )
        print(f"  ✅ agent_id added to '{collection_name}'.")
    except Exception as e:
        print(f"  ❌ Failed to add agent_id to '{collection_name}': {e}")


def run(dry_run: bool = False):
    """Run the Weaviate schema migration."""
    print("🦞 BrainClaw Weaviate Schema Migration")
    print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    client = get_client()
    try:
        for collection in COLLECTIONS:
            add_agent_id_property(client, collection, dry_run=dry_run)
        print(
            f"\n{'[DRY-RUN] Weaviate schema migration preview complete.' if dry_run else '✅ Weaviate schema migration complete.'}"
        )
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BrainClaw Weaviate schema migration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
