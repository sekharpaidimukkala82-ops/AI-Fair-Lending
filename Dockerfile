FROM python:3.12-slim

# Cache bust: 2026-07-01
WORKDIR /app

# Copy and install dependencies first (better layer caching)
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy entire project
COPY . .

# Expose port
EXPOSE 8001

# Start
CMD ["python", "run.py"]
