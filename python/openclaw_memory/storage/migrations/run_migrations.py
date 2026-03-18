"""
run_migrations.py — BrainClaw Database Migration Runner

Applies pending SQL migrations to PostgreSQL in order.
Tracks applied migrations in a `schema_migrations` table.

Usage:
    python -m openclaw_memory.storage.migrations.run_migrations
    python -m openclaw_memory.storage.migrations.run_migrations --dry-run
"""

import argparse
import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import DictCursor

MIGRATIONS_DIR = Path(__file__).parent
MIGRATIONS_TABLE = "schema_migrations"


def get_connection():
    """Get a PostgreSQL connection from environment."""
    url = os.environ.get("POSTGRES_URL") or os.environ.get("POSTGRESQL_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "POSTGRESQL_URL or DATABASE_URL environment variable is required."
        )
    return psycopg2.connect(url)


def ensure_migrations_table(conn):
    """Create the schema_migrations tracking table if not exists."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     TEXT PRIMARY KEY,
                applied_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
    conn.commit()


def get_applied_migrations(conn) -> set:
    """Return set of already-applied migration versions."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT version FROM {MIGRATIONS_TABLE};")
        return {row[0] for row in cur.fetchall()}


def get_pending_migrations(applied: set) -> list:
    """Return sorted list of (version, path) tuples for pending migrations."""
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    pending = []
    for sql_file in sql_files:
        version = sql_file.stem  # e.g. "001_agent_isolation"
        if version not in applied:
            pending.append((version, sql_file))
    return pending


def apply_migration(conn, version: str, sql_path: Path, dry_run: bool = False):
    """Apply a single migration and record it."""
    sql = sql_path.read_text(encoding="utf-8")
    print(f"  {'[DRY-RUN] ' if dry_run else ''}Applying {version}...")
    if dry_run:
        print(f"  SQL preview:\n{sql[:300]}{'...' if len(sql) > 300 else ''}")
        return

    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            f"INSERT INTO {MIGRATIONS_TABLE} (version) VALUES (%s);",
            (version,)
        )
    conn.commit()
    print(f"  ✅ {version} applied.")


def run(dry_run: bool = False):
    """Run all pending migrations."""
    print("🦞 BrainClaw Migration Runner")
    print(f"   Migrations dir: {MIGRATIONS_DIR}")
    print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    conn = get_connection()
    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)
        pending = get_pending_migrations(applied)

        if not pending:
            print("✅ No pending migrations. Database is up to date.")
            return

        print(f"Found {len(pending)} pending migration(s):\n")
        for version, path in pending:
            apply_migration(conn, version, path, dry_run=dry_run)

        if not dry_run:
            print(f"\n✅ {len(pending)} migration(s) applied successfully.")
        else:
            print(f"\n[DRY-RUN] {len(pending)} migration(s) would be applied.")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BrainClaw migration runner")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migrations without applying them",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
