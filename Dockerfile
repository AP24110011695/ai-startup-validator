FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

ENV PYTHONUNBUFFERED=1
# Default to real mode in the image; override per environment (Render env vars).
ENV USE_MOCK=false

EXPOSE 8000
# Render sets PORT for Docker services; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
