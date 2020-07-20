#!/bin/sh

set -ex

echo Checking and formatting with black...
black --check .

echo Python type checking...
mypy tg --warn-redundant-casts --warn-unused-ignores \
    --no-warn-no-return --warn-unreachable --strict-equality \
    --ignore-missing-imports --warn-unused-configs \
    --disallow-untyped-calls --disallow-untyped-defs \
    --disallow-incomplete-defs --check-untyped-defs \
    --disallow-untyped-decorators

echo Checking import sorting...
isort -c tg/*.py

echo Checking unused imports...
flake8 --select=F401
