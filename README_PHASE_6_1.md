# Phase 6.1 — Read-Only Project Review UI

## Quick Start

### Backend (Port 8000)
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (Port 3000)
```bash
cd frontend
npm run dev
```

Or use the convenience script:
```bash
./start-dev.sh
```

## Ports

- **Backend API**: `http://localhost:8000`
- **Frontend UI**: `http://localhost:3000`
- **API Base URL**: `http://localhost:8000/v1` (configurable via `NEXT_PUBLIC_API_URL`)

## Environment Variables

### Frontend
Create `frontend/.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
```

### Backend
Create `backend/.env`:
```env
OPENAI_API_KEY=your_key_here
PDF_DPI=200
LOG_LEVEL=INFO
```

## Features

- ✅ PDF upload and processing
- ✅ Project status tracking with auto-polling
- ✅ Bid proposal review with quantity provenance
- ✅ Evidence search
- ✅ 3D model statistics (viewer coming in Phase 6.2)
- ✅ Performance metrics

## API Endpoints

- `GET /v1/projects/{id}/artifacts` - List available artifacts
- `GET /v1/projects/{id}/artifacts/{name}` - Get artifact JSON
- `GET /v1/projects/{id}/summary` - Project summary
- `GET /v1/projects/{id}/status` - Detailed status
- `POST /v1/projects/upload` - Upload PDF






