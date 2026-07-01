FROM python:3.12-slim

# Cache bust: 2026-07-01-v4-200mb-upload
WORKDIR /app

# Copy and install dependencies first (better layer caching)
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy entire project
COPY . .

# /data is where Railway Volume gets mounted
# SQLite DB, uploads, and models all live here so they survive restarts
ENV DATABASE_URL=sqlite+aiosqlite:////data/fairlending.db
ENV UPLOAD_DIR=/data/uploads
ENV MODELS_DIR=/data/models_store
ENV CHROMA_PERSIST_DIR=/data/chroma_db
ENV DISABLE_FASTEMBED=true

# Allow large file uploads (200MB) — Railway proxy default is 50MB
# Setting this tells uvicorn/the app to accept larger bodies
ENV MAX_FILE_SIZE_MB=200

# Ensure /data exists at build time (Railway volume will override this at runtime)
RUN mkdir -p /data/uploads /data/models_store /data/chroma_db

# Expose port
EXPOSE 8001

# Start
CMD ["python", "run.py"]
