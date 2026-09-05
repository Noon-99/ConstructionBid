# Construction Bid AI Backend

A production-grade FastAPI backend for processing construction bid documents.

## Features

- PDF upload and storage
- PDF to image conversion (PNG) at configurable DPI
- Multi-stage processing pipeline (with stubs for AI extraction)
- Structured JSON logging with project tracking
- Dependency injection for maintainability
- Strict typing with Pydantic v2 and mypy

## Setup

### Prerequisites

- Python 3.11+
- `uv` or `pip` for package management

### Installation

```bash
cd backend
uv pip install -e .  # or: pip install -e .
```

### Environment Variables

Create a `.env` file (optional, defaults are provided):

```env
PDF_DPI=200
LOG_LEVEL=INFO
LOG_FORMAT=json
DEBUG=false
STORAGE_ROOT=./storage
```

## Running the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or with custom settings:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level info
```

## API Endpoints

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{"status": "healthy"}
```

### Upload PDF

```bash
curl -X POST "http://localhost:8000/v1/projects/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/your/document.pdf"
```

Example Response:
```json
{
  "project_id": "a1b2c3d4",
  "page_count": 5,
  "status": "completed"
}
```

### Get Full Project Result

```bash
curl http://localhost:8000/v1/projects/{project_id}/result
```

Example Response:
```json
{
  "project_id": "a1b2c3d4",
  "page_count": 5,
  "status": "completed",
  "document_bundle": {
    "project_id": "a1b2c3d4",
    "source_pdf_path": "./storage/a1b2c3d4/source.pdf",
    "page_count": 5,
    "page_image_paths": [
      "./storage/a1b2c3d4/pages/page_1.png",
      "./storage/a1b2c3d4/pages/page_2.png",
      ...
    ]
  },
  "document_analysis": {
    "project_type": "construction_bid",
    "scope_locations": [...],
    "quantity_locations": [...],
    "geometry_sources": [...],
    "confidence": 0.75
  },
  "extraction": {
    "scope_items": [...],
    "materials": [...],
    "quantities": [...],
    "requirements": [...],
    "geometry_for_3d": [...]
  },
  "validation": {
    "missing_critical": [],
    "needs_reread_pages": [],
    "notes": [...]
  }
}
```

## Storage Structure

After uploading a PDF, the following structure is created:

```
storage/
  {project_id}/
    source.pdf
    pages/
      page_1.png
      page_2.png
      ...
```

## PDF Library

This implementation uses **PyMuPDF (fitz)** for PDF processing. It's a robust, fast library that works entirely locally without cloud dependencies.

## Development

### Code Quality

```bash
# Format and lint
ruff check .
ruff format .

# Type checking
mypy app/
```

### Project Structure

```
backend/
  app/
    main.py              # FastAPI app entry point
    api/
      routes/            # API route handlers
    core/                # Core configuration and utilities
    models/              # Pydantic schemas
    services/            # Business logic services
    utils/               # Utility functions
  pyproject.toml         # Project configuration
  README.md
```

## Notes

- All AI extraction stages (1-3) are currently stubs returning placeholder JSON structures
- The pipeline is designed to be easily extended with real GPT-Vision or other AI calls
- Logs include `project_id` and `stage` fields for tracking and debugging
- All file operations are deterministic and use project IDs for organization

