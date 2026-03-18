#!/bin/bash
# Bundle Python backend into the plugin package
# This makes the plugin self-contained for production deployment

set -e

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONOREPO_ROOT="$(cd "$PLUGIN_DIR/../.." && pwd)"
PYTHON_SRC="$MONOREPO_ROOT/packages/openclaw-memory/src"
PYTHON_DEST="$PLUGIN_DIR/python/openclaw_memory"

echo "Bundling Python backend..."

# Clean previous bundle
if [ -d "$PYTHON_DEST" ]; then
    rm -rf "$PYTHON_DEST"
fi

# Copy Python source
if [ -d "$PYTHON_SRC" ]; then
    mkdir -p "$PYTHON_DEST"
    cp -r "$PYTHON_SRC"/* "$PYTHON_DEST/"
    echo "✓ Python backend bundled to python/openclaw_memory/"
else
    echo "✗ Python source not found at $PYTHON_SRC"
    echo "  Run this script from the monorepo root or ensure openclaw-memory is present"
    exit 1
fi

# Copy requirements for the bundled package
if [ -f "$MONOREPO_ROOT/packages/openclaw-memory/pyproject.toml" ]; then
    cp "$MONOREPO_ROOT/packages/openclaw-memory/pyproject.toml" "$PLUGIN_DIR/python/"
    echo "✓ pyproject.toml copied"
fi

# Create __init__.py if not present
if [ ! -f "$PYTHON_DEST/__init__.py" ]; then
    touch "$PYTHON_DEST/__init__.py"
    echo "✓ __init__.py created"
fi

echo "Bundle complete!"