# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENIZERS_PARALLELISM=false

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libmagic1 \
        libxml2 \
        libxslt1.1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (Hugging Face Spaces requires UID 1000).
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/user/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/user/.cache/huggingface

WORKDIR /home/user/app

COPY --chown=user:user backend/requirements.txt ./backend/requirements.txt
RUN pip install --user -r backend/requirements.txt

# Pre-download the embedding model into the image so cold start is fast and
# the container doesn't need to pull ~420 MB on first request.
ARG EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

COPY --chown=user:user backend ./backend
COPY --chown=user:user frontend ./frontend
COPY --chown=user:user data/source ./data/source

ENV HOST=0.0.0.0 \
    PORT=8000 \
    SOURCE_DATA_DIR=/home/user/app/data/source \
    CHROMA_DB_PATH=/home/user/app/data/chroma \
    AUTO_INGEST_ON_STARTUP=1

RUN mkdir -p /home/user/app/data/chroma

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS http://localhost:${PORT}/api/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host ${HOST} --port ${PORT} --workers 1"]
