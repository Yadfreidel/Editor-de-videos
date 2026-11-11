# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY next.config.ts tsconfig.json postcss.config.mjs ./
COPY app ./app
COPY scripts/build-pages.cjs ./scripts/build-pages.cjs
ENV NEXT_PUBLIC_BASE_PATH="" NEXT_PUBLIC_SERVER_HOSTED=true
RUN npm run build:pages

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 CLIP_REMOTE=true \
    CLIP_WORKSPACE=/data CLIP_FRONTEND_DIR=/app/frontend \
    FFMPEG_PATH=/usr/bin/ffmpeg FFPROBE_PATH=/usr/bin/ffprobe \
    WHISPER_MODEL=/opt/clip-models/whisper-tiny WHISPER_DEVICE=cpu \
    PIPER_MODEL=/opt/clip-models/piper/es_ES-sharvard-medium.onnx \
    CLIP_RENDER_THREADS=2 CLIP_MAX_UPLOAD_MB=256 OMP_NUM_THREADS=2
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements-optional.txt ./backend/
RUN pip install -r backend/requirements-optional.txt
COPY backend ./backend
RUN python backend/cloud_models.py
COPY scripts/cloud_start.py ./scripts/cloud_start.py
COPY scripts/cloud_container_smoke.py ./scripts/cloud_container_smoke.py
COPY docs/PROVIDERS.md docs/TEST-FIXTURES.md ./docs/
COPY --from=frontend /build/.next-pages /app/frontend
RUN mkdir -p /data
EXPOSE 8000
CMD ["python","scripts/cloud_start.py"]
