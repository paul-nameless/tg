#!/bin/sh

set -ex

echo Checking and formatting with ruff...
ruff format --check .

echo Python type checking...
mypy tg

echo Checking imports and linting with ruff...
ruff check tg/
