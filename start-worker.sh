#!/bin/bash
# Start the RQ worker for pipeline jobs
# This script ensures the worker stays running

cd "$(dirname "$0")"

# Kill any existing worker
if [ -f worker.pid ]; then
    OLD_PID=$(cat worker.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        echo "Stopping existing worker (PID: $OLD_PID)"
        kill $OLD_PID 2>/dev/null
        sleep 2
    fi
    rm -f worker.pid
fi

# Start new worker (set PYTHONPATH to backend directory, clear Python cache)
echo "Starting RQ worker..."
cd "$(dirname "$0")"
# Clear Python cache to ensure fresh imports
find backend -name "*.pyc" -delete 2>/dev/null
find backend -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
PYTHONPATH=backend python3 -B -m app.workers.worker > worker.log 2>&1 &
echo $! > worker.pid
echo "Worker started with PID $(cat worker.pid)"
echo "Logs: tail -f worker.log"
echo ""
echo "To stop: kill \$(cat worker.pid)"

