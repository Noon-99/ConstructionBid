# Worker Setup Guide

The pipeline requires a background worker to process jobs from the Redis queue.

## Quick Start

1. **Start Redis** (if not already running):
   ```bash
   docker run -d -p 6379:6379 --name redis-construction redis
   ```

2. **Start the Worker**:
   ```bash
   ./start-worker.sh
   ```

   Or manually:
   ```bash
   cd backend
   nohup python3 -m app.workers.worker > worker.log 2>&1 &
   echo $! > worker.pid
   ```

3. **Check Worker Status**:
   ```bash
   tail -f worker.log
   ```

4. **Stop Worker**:
   ```bash
   kill $(cat worker.pid)
   ```

## Troubleshooting

### Worker Not Processing Jobs

- Check if worker is running: `ps aux | grep worker`
- Check worker logs: `tail -f worker.log`
- Check Redis connection: `python3 -c "from redis import Redis; Redis.from_url('redis://localhost:6379/0').ping()"`
- Check queue: `python3 -c "from redis import Redis; from rq import Queue; q = Queue('pipeline', connection=Redis.from_url('redis://localhost:6379/0')); print(f'Jobs: {len(q)}')"`

### Stale Locks

If you see "already being processed" errors, clear the lock:
```bash
python3 -c "from redis import Redis; r = Redis.from_url('redis://localhost:6379/0'); r.delete('pipeline:lock:PROJECT_ID')"
```

### Worker Crashes

On macOS, the worker uses SimpleWorker (in-process) to avoid fork() issues. If it crashes:
1. Check `worker.log` for errors
2. Restart: `./start-worker.sh`
3. Check Python version: `python3 --version` (should be 3.11+)




