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

if [ "$#" -gt 0 ]; then
    .venv/bin/python -m battlezone.server "$@"
else
    .venv/bin/python -m battlezone.server --host 0.0.0.0 --port 51515 --ui logs
fi
