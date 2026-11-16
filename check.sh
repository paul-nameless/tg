#!/bin/sh

set -ex

echo Checking and formatting with ruff...
ruff format --check .

echo Python type checking...
mypy tg tests

echo Checking imports and linting with ruff...
ruff check .

echo Running tests...
python -m unittest discover -s tests -t .
