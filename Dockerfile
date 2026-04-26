FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY config.yaml ./config.yaml
COPY config ./config
COPY prompts ./prompts
COPY src ./src

RUN mkdir -p \
    data/avatars \
    data/chats \
    data/characters \
    data/live2d/models \
    data/qdrant \
    logs \
    models

EXPOSE 8430

CMD ["python", "-m", "src.main"]
