# FairLend AI — Startup Guide

## Quick Start (double-click in order)

| Step | File | What it does |
|---|---|---|
| 1 | `start_backend.bat` | Starts FastAPI backend on port 8001 |
| 2 | `start_frontend.bat` | Starts React frontend on port 3001 |

## URLs

| Service | URL | Notes |
|---|---|---|
| React Frontend | http://localhost:3001 | Enterprise UI (new) |
| Backend API | http://localhost:8001 | FastAPI |
| API Docs | http://localhost:8001/docs | Swagger UI |
| Health Check | http://localhost:8001/health | Status endpoint |
| Old Vanilla JS UI | http://localhost:3000 | Run start_frontend_legacy.bat |

## Default Login

| Field | Value |
|---|---|
| Email | admin@fairlend.ai |
| Password | FairLend@Admin2024 |

## Requirements

| Tool | Version | Download |
|---|---|---|
| Python | 3.12 | C:\Users\admn\AppData\Local\Programs\Python\Python312\ |
| Node.js | 20+ LTS | https://nodejs.org |

## Environment Variables (backend/.env)

```
GEMINI_API_KEY=your_gemini_key_here
OPENAI_API_KEY=your_openai_key_here
SECRET_KEY=change-this-in-production-use-32-char-secret
DATABASE_URL=sqlite+aiosqlite:///./backend/fairlending.db
ACCESS_TOKEN_EXPIRE_MINUTES=480
```

## Architecture

```
localhost:3001  →  React (Vite dev server)
                   ↓ proxies /api/* to
localhost:8001  →  FastAPI (uvicorn)
                   ↓
                   SQLite (backend/fairlending.db)
                   ChromaDB (backend/chroma_db/)
                   ML Models (backend/models_store/)
                   Uploads (backend/uploads/)
```

## Troubleshooting

**Backend won't start:** Port 8001 in use — the BAT file kills it automatically.
**Frontend won't start:** Make sure Node.js is installed at `C:\Program Files\nodejs`.
**Login fails:** Make sure backend is running first (admin created on first startup).
**Gemini error:** Add `GEMINI_API_KEY` to `backend/.env` or use AI Settings page in the UI.
