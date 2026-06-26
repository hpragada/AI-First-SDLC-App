# Backend image — Django API + Temporal worker share this image.
# Built only under the compose `app` profile (P0-T2 onward).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg / builds, plus Node.js so Claude Code can run inside the
# backend container image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev nodejs npm \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && pip install -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
