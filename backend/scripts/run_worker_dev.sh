#!/bin/bash
# Development worker script that uses SimpleWorker on macOS to avoid fork() crashes
# On Linux, uses the standard forking worker

set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$BACKEND_DIR/.." && pwd)"

# Change to backend directory
cd "$BACKEND_DIR"

# Set Python path
export PYTHONPATH="$BACKEND_DIR"

# Detect OS
OS_TYPE="$(uname -s)"

# Default queue name (can be overridden)
QUEUE_NAME="${RQ_QUEUE_NAME:-pipeline}"
REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"

echo "🔧 Starting RQ worker..."
echo "   OS: $OS_TYPE"
echo "   Queue: $QUEUE_NAME"
echo "   Redis URL: $REDIS_URL"

# Use our worker.py which auto-detects macOS and uses SimpleWorker
echo "   Starting worker (auto-detects macOS and uses SimpleWorker if needed)"
echo ""
python3 -m app.workers.worker

