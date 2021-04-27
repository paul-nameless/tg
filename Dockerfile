FROM python:3.9.4-slim-buster

WORKDIR /app

ENV PYTHONPATH=/app

RUN pip3 install --disable-pip-version-check --no-cache-dir poetry

COPY poetry.lock pyproject.toml /app/

RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-dev

COPY . /app

CMD python3 -m tg
