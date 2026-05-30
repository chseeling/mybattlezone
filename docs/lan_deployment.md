# LAN Deployment Guide

This project now has package entrypoints for deployment while `test02.py` remains the Panda3D game runtime.

## Code Layout

```text
battlezone/
  client.py              command-line LAN client entrypoint
  client_launcher.py     launcher entrypoint
  client_launcher_ui.py  GUI and terminal launcher implementation
  config.py              environment/default configuration helpers
  controllers.py         tank command and controller primitives
  network.py             UDP join, command, snapshot, and claim bridge
  protocol.py            wire protocol constants
  runtime.py             imports and runs the game runtime
  server.py              authoritative LAN server entrypoint
test02.py                current Panda3D game runtime
```

## LAN Prerequisites

- Server and clients must be on the same local network.
- UDP port `51515` must be reachable from each client to the server host.
- Clients connect to the server machine's LAN IP, for example `192.168.1.42`.
- If the server runs in Docker, clients still use the host machine's LAN IP, not the container IP.
- The client needs Python and Panda3D. It does not need pygame.

## Server

Run the server directly on Windows:

```powershell
cd C:\Users\cseel\myProjects\mybattlezone
python -m battlezone.server --host 0.0.0.0 --port 51515 --ui tui
```

From a server ZIP, use:

```powershell
.\start_server.ps1
```

The first-run helper creates `.venv`, installs dependencies, and starts the log-mode LAN server on UDP `51515`.

Run the log-mode server for hosted/headless operation:

```powershell
cd C:\Users\cseel\myProjects\mybattlezone
python -m battlezone.server --host 0.0.0.0 --port 51515 --ui logs --log-interval 5
```

Run the server with Docker:

```powershell
cd C:\Users\cseel\myProjects\mybattlezone
docker build -t mybattlezone-server .
docker run --rm -it -p 51515:51515/udp mybattlezone-server
```

The Docker container has its own internal IP, but that is not the client address. Clients use the host PC's LAN IP because the command above publishes UDP `51515` on the host.

When no human claims remain, the server can hibernate the arena. A later client join wakes it again.

Build a server ZIP for a LAN host machine:

```powershell
python .\scripts\package_server.py
```

The output is written to `dist/mybattlezone-server.zip`.

Build both the client and server ZIPs together:

```powershell
python .\scripts\package_all.py
```

## Client

Run the client launcher:

```powershell
python -m battlezone.client_launcher
```

From a client ZIP, use:

```powershell
.\start_client.ps1
```

The first-run helper creates `.venv`, installs dependencies, and opens the launcher.

On Raspberry Pi OS Buster, pip may not provide a Panda3D wheel. If `panda3d1.11` is installed with apt, `start_client.sh` uses system Python instead of forcing a venv. It also defaults `BATTLEZONE_AUDIO_FOCUS_MUTE=0`, `BATTLEZONE_NET_CLIENT_LOW_RENDER_SIZE=640x360`, and `BATTLEZONE_NET_RENDER_DELAY=0.16` for Pi-friendly play over Wi-Fi.

Run a Windows client directly:

```powershell
python -m battlezone.client --host 192.168.1.42 --port 51515 --tank 0 --controller human --full-render
```

Run a Raspberry Pi or Linux client:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip panda3d1.11
cd ~/mybattlezone
sh start_client.sh --host 192.168.1.42 --tank 0 --low-render --play
```

Use `--low-render` on slower clients.

## Casual Client Distribution

A casual user should not need Git. Package a client-only ZIP containing:

```text
battlezone/
client_launcher.py
play_client.ps1
play_client.sh
start_client.ps1
start_client.sh
test02.py
requirements.txt
config/
models/
sfx/
```

Build the ZIP from a developer checkout:

```powershell
python .\scripts\package_client.py
```

The output is written to `dist/mybattlezone-client.zip`.

Expected first-run flow:

1. Install Python.
2. Start `start_client.ps1` on Windows or `sh start_client.sh` on Linux.
3. Let the helper install dependencies or use system Panda3D on Raspberry Pi OS.
4. Enter the server PC's LAN IP.
5. Click Play.

The launcher writes `client_config.json` beside itself, so the user does not need to re-enter the server IP every time.

## Troubleshooting

- `Could not open display ":99"` means the Panda3D process expected an X display. Use the Docker server image or run under `xvfb-run` for headless Linux.
- `Could not open default OpenAL device` usually means the environment has no audio device. The server image sets null audio for hosted operation.
- If clients cannot join, check firewall rules for UDP `51515` on the server host.
- If the server is in Docker, confirm `-p 51515:51515/udp` is present.
