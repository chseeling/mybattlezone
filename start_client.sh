#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")" || exit 1

if [ "${1:-}" = "--setup-only" ]; then
    if python3 -c "from direct.showbase.ShowBase import ShowBase" >/dev/null 2>&1; then
        echo "Using system Python with system Panda3D."
        exit 0
    fi
    if [ ! -x ".venv/bin/python" ]; then
        python3 -m venv .venv
    fi
    .venv/bin/python -m pip install -r requirements.txt
    exit 0
fi

export BATTLEZONE_AUDIO_FOCUS_MUTE="${BATTLEZONE_AUDIO_FOCUS_MUTE:-0}"
export BATTLEZONE_NET_CLIENT_LOW_RENDER_SIZE="${BATTLEZONE_NET_CLIENT_LOW_RENDER_SIZE:-640x360}"
export BATTLEZONE_NET_RENDER_DELAY="${BATTLEZONE_NET_RENDER_DELAY:-0.16}"

if python3 -c "from direct.showbase.ShowBase import ShowBase" >/dev/null 2>&1; then
    python3 -m battlezone.client_launcher "$@"
else
    if [ ! -x ".venv/bin/python" ]; then
        python3 -m venv .venv
    fi
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python -m battlezone.client_launcher "$@"
fi
