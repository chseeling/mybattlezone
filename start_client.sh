#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt

if [ "${1:-}" = "--setup-only" ]; then
    exit 0
fi

.venv/bin/python -m battlezone.client_launcher "$@"
