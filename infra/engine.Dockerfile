# Processing engine for Google Cloud Run. Build from the repo root:
#   docker build -f infra/engine.Dockerfile -t mend-engine .
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg chromium fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY engine/requirements.txt engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt
COPY engine engine
COPY config config
ENV PYTHONUNBUFFERED=1 MEND_DATA_DIR=/tmp/mend-data MEND_CHROME=/usr/bin/chromium PORT=8080
WORKDIR /app/engine
CMD ["sh", "-c", "python -m uvicorn mend.api:app --host 0.0.0.0 --port ${PORT}"]
