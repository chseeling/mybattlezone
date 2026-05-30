# mybattlezone

Wireframe Battlezone-style prototype built with Panda3D.

## Setup

```
python -m pip install -r requirements.txt
```

On Windows, this repo also has a local virtual environment setup:

```
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```
cd mybattlezone
python test02.py
```

Or from PowerShell on Windows:

```
.\run.ps1
```

## Deployment Layout

The deployment entrypoints live under the `battlezone` package:

```text
battlezone.client              LAN client entrypoint
battlezone.client_launcher     client launcher entrypoint
battlezone.client_launcher_ui  launcher implementation
battlezone.config              environment/default configuration
battlezone.controllers         tank command/controller primitives
battlezone.network             UDP networking bridge
battlezone.protocol            wire protocol constants
battlezone.runtime             runtime importer
battlezone.server              authoritative LAN server entrypoint
```

`test02.py` remains the legacy game engine entrypoint while the runtime is split into cleaner client/server launch paths.

See [docs/lan_deployment.md](docs/lan_deployment.md) for LAN setup, Raspberry Pi commands, Docker notes, and casual-client packaging.

## Network Server

Authoritative server with the terminal dashboard:

```powershell
cd C:\Users\cseel\myProjects\mybattlezone
python -m battlezone.server --ui tui
```

Authoritative server with JSON status logs for hosted/headless-style deployment:

```powershell
cd C:\Users\cseel\myProjects\mybattlezone
python -m battlezone.server --ui logs --log-interval 5
```

In `tui`, `logs`, `headless`, and `none` server UI modes, the Panda server window is minimized by default. Set `$env:BATTLEZONE_SERVER_WINDOW="visible"` before launch if you want to inspect the server render window.

Tank 0 human client on the same machine:

```powershell
cd C:\Users\cseel\myProjects\mybattlezone
python -m battlezone.client --host 127.0.0.1 --tank 0 --full-render
```

Use `--host 0.0.0.0` on the server when accepting LAN clients, and use the server machine's LAN IP on the client.

## Client Launcher

For LAN clients, use the launcher instead of setting environment variables by hand:

```powershell
python -m battlezone.client_launcher
```

On Windows you can also run:

```powershell
.\play_client.ps1
```

From a client ZIP, use the first-run helper to create `.venv`, install Panda3D, and open the launcher:

```powershell
.\start_client.ps1
```

On Raspberry Pi or Linux:

```bash
python3 -m battlezone.client_launcher
```

or:

```bash
sh play_client.sh
```

or from a client ZIP:

```bash
sh start_client.sh
```

On Raspberry Pi OS Buster, `start_client.sh` uses the system Panda3D package when available and disables audio-focus muting by default.

The launcher saves the server IP, port, tank, controller, and render mode in `client_config.json`. Use the server PC's LAN IP, for example `192.168.1.42`, not the Docker container IP. The client needs Python and Panda3D; it does not need pygame.

To launch directly from a terminal:

```bash
python3 -m battlezone.client_launcher --host 192.168.1.42 --tank 0 --low-render --play
```

A client-only ZIP should include:

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

Build that ZIP from the repo with:

```powershell
python .\scripts\package_client.py
```

or:

```powershell
.\scripts\package_client.ps1
```

For Raspberry Pi or Linux:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip panda3d1.11
sh start_client.sh --host 192.168.1.42 --tank 0 --low-render --play
```

## Docker Server

Build and run the log-mode UDP server locally:

```powershell
cd C:\Users\cseel\myProjects\mybattlezone
docker build -t mybattlezone-server .
docker run --rm -it -p 51515:51515/udp `
  mybattlezone-server
```

Then run a local client with `$env:BATTLEZONE_NET_HOST="127.0.0.1"`.

For LAN clients, keep the Docker port publish as UDP and connect to the Docker host's LAN IP:

```powershell
docker run --rm -it -p 51515:51515/udp mybattlezone-server
```

The container has an internal IP, but casual clients should not use it.

Build a server ZIP for a LAN host machine:

```powershell
python .\scripts\package_server.py
```

or:

```powershell
.\scripts\package_server.ps1
```

From a server ZIP, run the direct-host first-run helper:

```powershell
.\start_server.ps1
```

On Linux:

```bash
sh start_server.sh
```

Build both client and server ZIPs together:

```powershell
python .\scripts\package_all.py
```

## Controls

- Arrow keys: move and turn
- Space, F, Ctrl, or left mouse: fire
- B: toggle GPU bloom
- D: deploy or recall recon drone
- I: investigate a recent hit on your tank before the timer expires
- R: restart after game over
- Network lobby: number keys claim tanks, Y marks ready, U marks unready, L releases the current claim, J rejoins after release

The lower-left HUD radar shows enemy tank positions relative to your current heading. Enemy returns brighten when scanned, then fade like phosphor.
A stitched HUD panorama shows the forward side views, with a separate rear view below.
GPU bloom uses a post-process filter for vector glow, falling back to the older geometry bloom if the filter is unavailable.
The recon drone opens with a wide blue-hued battlefield survey, then glides toward enemy tanks for slower recon sweeps before returning on low battery.
When your tank is hit, a short investigation timer appears. Press I before it expires to freeze the scene, glide through it with the normal movement keys, see the shooter in red at firing time, see your tank in blue at impact time, and show the shot trajectory. If the hit ends the game, the last-shot investigation remains available from the game-over screen.
Wireframe blocks, pyramids, and cones act as obstacles. The player is blocked by them, enemy tanks route around their footprints, and shots stop when they hit them.

To show collision debug output:

```
$env:BATTLEZONE_DEBUG = "1"
python test02.py
```
