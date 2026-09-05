# CORS Fix Applied

## Problem
The console shows:
```
Access to fetch at 'http://localhost:8000/v1/projects/86c7fce4/run' from origin 'http://localhost:3000' 
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

## Root Cause
When `allow_credentials=True` in FastAPI CORS middleware, you **cannot** use `"*"` as an origin. This is a browser security restriction.

## Fix Applied
Updated `backend/app/main.py`:
- Removed `"*"` from `allow_origins`
- Kept only specific origins: `http://localhost:3000` and `http://127.0.0.1:3000`
- Explicitly listed allowed methods
- Added `expose_headers=["*"]` for better compatibility

## Action Required

**⚠️ RESTART THE BACKEND SERVER**

The CORS configuration change requires a server restart to take effect.

### Steps:
1. **Stop the current backend** (if running):
   - Press `Ctrl+C` in the terminal where backend is running

2. **Start the backend**:
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Verify it's running**:
   - Check http://localhost:8000/docs (should show FastAPI docs)
   - Check http://localhost:8000/health (should return `{"status": "healthy"}`)

4. **Test upload again**:
   - Go to http://localhost:3000
   - Try uploading a PDF
   - The CORS error should be gone

## Why This Happened

The upload actually **succeeded** (you can see project ID `86c7fce4` in the error), but the **second call** to `/run` was blocked by CORS because:
- The backend was using `"*"` with `allow_credentials=True`
- Browsers reject this combination for security reasons
- The CORS middleware wasn't sending the proper headers

## Verification

After restarting, check the browser console:
- ✅ No CORS errors
- ✅ Upload → Run → Navigate flow works
- ✅ Network tab shows successful requests with CORS headers






