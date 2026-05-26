# Plan S: Network Process Split

Goal: make all tanks symmetrical network actors by separating the authoritative simulation from tank view/control processes.

## Target Shape

```text
battle-server
  authoritative world simulation
  owns terrain, obstacles, shots, hits, lives, respawn, timing
  no full player HUD; eventually no GPU-heavy rendering
  receives tank inputs and broadcasts snapshots/events

tank-client-0
  human/controller process for tank 0
  renders tank 0 view from server snapshots
  sends tank 0 input to server

tank-client-1
  human/controller process for tank 1
  renders tank 1 view from server snapshots
  sends tank 1 input to server
```

## GPU Policy

- The server should not require GPU-heavy rendering.
- On a one-GPU development machine, give tank 0 the full render path by convention.
- Additional local tank clients should run with `BATTLEZONE_NET_CLIENT_LOW_RENDER=1` until we have stronger GPU scheduling.
- GPU sharing should remain optional; controller input and server authority must not depend on full rendering.

## Milestone 1: Explicit Server Mode

- Add `BATTLEZONE_NET_MODE=server` as the authoritative process name.
- Keep `BATTLEZONE_NET_MODE=host` as a compatibility alias while we transition.
- Server mode owns simulation, shots, lives, respawn, investigation state, and snapshots.
- Existing `client` mode remains a non-authoritative tank controller/view.

## Milestone 2: Tank 0 As A Client

- Allow `BATTLEZONE_NET_TANK=0` on a client.
- Move tank 0 view rendering onto the same snapshot path as tank 1.
- Server should treat tank 0 input like any other `RemoteTankController`.
- Remove special cases where tank 0 is the authoritative camera.

## Milestone 3: Multiple Tank Clients

- Track multiple client addresses keyed by tank id.
- Accept input packets for tank 0, 1, 2, and 3.
- Broadcast snapshots to every connected client.
- Add simple join/leave status before introducing lobbies.

## Milestone 4: Publishable Transport

- Keep local UDP for development.
- Later replace or wrap local UDP with Steam lobbies / Steam Networking Sockets for public play.

## Runtime Modes

- Normal: no networking.
- Server: set `BATTLEZONE_NET_MODE=server`.
- Compatibility host: set `BATTLEZONE_NET_MODE=host`.
- Client: set `BATTLEZONE_NET_MODE=client`.

Useful environment variables:

- `BATTLEZONE_NET_HOST`: server address. Use `0.0.0.0` for the server bind address; use the host PC LAN IP from clients.
- `BATTLEZONE_NET_PORT`: UDP port, default `51515`.
- `BATTLEZONE_NET_TANK`: controlled tank id, default `1`.
- `BATTLEZONE_NET_CLIENT_LOW_RENDER`: client-only lighter render mode, default `1`.
- `BATTLEZONE_NET_SERVER_LOW_RENDER`: server-only lighter render mode, default `1`.
- `BATTLEZONE_ACTIVE_TANKS`: comma-separated active non-player tanks. Network modes default to `1` for a tank 0 + tank 1 test.

## Local Test Recipes

Authoritative server:

```powershell
$env:BATTLEZONE_NET_MODE="server"
$env:BATTLEZONE_NET_HOST="0.0.0.0"
$env:BATTLEZONE_NET_PORT="51515"
$env:BATTLEZONE_ACTIVE_TANKS="1"
$env:BATTLEZONE_NET_SERVER_LOW_RENDER="1"
.\run.ps1
```

Tank 0 full-render client:

```powershell
$env:BATTLEZONE_NET_MODE="client"
$env:BATTLEZONE_NET_HOST="127.0.0.1"
$env:BATTLEZONE_NET_PORT="51515"
$env:BATTLEZONE_NET_TANK="0"
$env:BATTLEZONE_ACTIVE_TANKS="1"
$env:BATTLEZONE_NET_CLIENT_LOW_RENDER="0"
.\run.ps1
```

Tank 1 low-render local client:

```powershell
$env:BATTLEZONE_NET_MODE="client"
$env:BATTLEZONE_NET_HOST="127.0.0.1"
$env:BATTLEZONE_NET_PORT="51515"
$env:BATTLEZONE_NET_TANK="1"
$env:BATTLEZONE_ACTIVE_TANKS="1"
$env:BATTLEZONE_NET_CLIENT_LOW_RENDER="1"
.\run.ps1
```
