#!/bin/sh

set -ex

echo Checking and formatting with ruff...
ruff format --check .

echo Python type checking...
mypy tg --warn-redundant-casts --warn-unused-ignores \
    --no-warn-no-return --warn-unreachable --strict-equality \
    --ignore-missing-imports --warn-unused-configs \
    --disallow-untyped-calls --disallow-untyped-defs \
    --disallow-incomplete-defs --check-untyped-defs \
    --disallow-untyped-decorators

echo Checking imports and linting with ruff...
ruff check tg/
