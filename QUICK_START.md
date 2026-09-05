# Quick Start Guide - Phase 6.1

## Start the Servers

### Option 1: Manual Start

**Terminal 1 - Backend:**
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### Option 2: Use the Start Script
```bash
./start-dev.sh
```

## Access the Application

- **Frontend UI**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Troubleshooting

### Connection Refused Error

1. **Check if servers are running:**
   ```bash
   lsof -i :8000  # Check backend
   lsof -i :3000  # Check frontend
   ```

2. **Check backend logs:**
   ```bash
   tail -f backend.log
   ```

3. **Check frontend logs:**
   ```bash
   tail -f frontend.log
   ```

4. **Verify environment:**
   - Backend needs `OPENAI_API_KEY` in `backend/.env`
   - Frontend API URL is set in `frontend/lib/api.ts` (defaults to `http://localhost:8000/v1`)

### Common Issues

- **Port already in use**: Kill the process using the port or use a different port
- **CORS errors**: Backend has CORS enabled for all origins (should work)
- **API connection failed**: Make sure backend is running on port 8000 before starting frontend






