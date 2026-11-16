FROM python:3.13.3-slim-bullseye

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

WORKDIR /app

ENV PYTHONPATH=/app \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY uv.lock pyproject.toml /app/

RUN uv sync --locked --no-dev --no-install-project --inexact

COPY . /app

CMD ["python3", "-m", "tg"]
