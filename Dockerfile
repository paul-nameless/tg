FROM python:3.13.3-slim-bullseye

WORKDIR /app

ENV PYTHONPATH=/app

RUN pip3 install --disable-pip-version-check --no-cache-dir poetry

COPY poetry.lock pyproject.toml /app/

# Use --without dev to skip dev dependencies (--no-dev is deprecated)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --without dev --no-root

COPY . /app

CMD ["python3", "-m", "tg"]
