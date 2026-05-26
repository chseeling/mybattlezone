# Plan S: Network Process Split

Goal: make all tanks symmetrical network actors by separating the authoritative simulation from tank view/control processes.

## Target Shape

```text
battle-server
  authoritative world simulation
  owns terrain, obstacles, shots, hits, lives, respawn, timing
  no full player HUD; eventually no GPU-heavy rendering
  receives tank inputs and broadcasts snapshots/events
  runs unclaimed nonzero tanks as local autonomous enemies

tank-client-0
  human/controller process for tank 0
  renders tank 0 view from server snapshots
  sends tank 0 input to server

tank-client-1
  human or autonomous controller process for tank 1
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
- In single-player client/server mode, tank 0 is the only required client; tanks 1-3 can remain server-side AI.
- Remove special cases where tank 0 is the authoritative camera.
- Share tank hit events across all tank ids so clients can render destruction for tank 0 and tank 1 from the same snapshot event.
- Track and display remaining lives for every active tank, not just tank 0.

## Milestone 3: Multiple Tank Clients

- Track multiple client addresses keyed by tank id.
- Accept input packets for tank 0, 1, 2, and 3.
- Broadcast snapshots to every connected client.
- Add simple join/leave status before introducing lobbies.
- Expire clients that stop sending input/presence packets so stale local test windows do not remain connected.
- Clients send `join` packets before input; the server replies with `join_ack` accepted/rejected state for the requested tank.
- Clients send `leave` on clean window close so the server can release the tank immediately.

## Milestone 4: Publishable Transport

- Keep local UDP for development.
- Later replace or wrap local UDP with Steam lobbies / Steam Networking Sockets for public play.

## Runtime Modes

- Normal: no networking.
- Server: set `BATTLEZONE_NET_MODE=server`.
- Compatibility host: set `BATTLEZONE_NET_MODE=host`.
- Client: set `BATTLEZONE_NET_MODE=client`.
- Tank clients choose their controller with `BATTLEZONE_NET_CONTROLLER=human` or `autonomous`.
- Unclaimed nonzero tanks remain server-side autonomous tanks. A tank client can claim one later for multiplayer or AI-offload tests.
- Start/restart is client-driven: connected tank clients send requests, and the server validates readiness before changing authoritative simulation state.

Useful environment variables:

- `BATTLEZONE_NET_HOST`: server address. Use `0.0.0.0` for the server bind address; use the host PC LAN IP from clients.
- `BATTLEZONE_NET_PORT`: UDP port, default `51515`.
- `BATTLEZONE_NET_TANK`: controlled tank id, default `1`.
- `BATTLEZONE_NET_CONTROLLER`: `human` or `autonomous`. Defaults to `human` for tank 0 and `autonomous` for other tank clients.
- Autonomous/nonzero tank clients currently start with 10 lives; tank 0 starts with 3 lives.
- Client presence timeout is currently `2.5` seconds.
- Client join requests are sent once per second until accepted.
- `BATTLEZONE_NET_CLIENT_LOW_RENDER`: client-only lighter render mode. Defaults to `0` for tank 0 and `1` for other tank clients.
- `BATTLEZONE_NET_SERVER_LOW_RENDER`: server-only lighter render mode, default `1`.
- Full-render tank clients use a short vector afterimage to soften 25 Hz snapshot motion without increasing network rate.
- `BATTLEZONE_AUDIO_FOCUS_MUTE`: mute this process when its window is not focused. Defaults to `0` for the tank 0 human client so OBS can capture it, and `1` for server/autonomous/secondary clients.
- `BATTLEZONE_ACTIVE_TANKS`: comma-separated active non-player tanks. Defaults to `1,2,3`; set it to `1` for a minimal tank 0 + tank 1 test.

## Local Test Recipes

Authoritative server with three server-side AI enemies:

```powershell
$env:BATTLEZONE_NET_MODE="server"
$env:BATTLEZONE_NET_HOST="0.0.0.0"
$env:BATTLEZONE_NET_PORT="51515"
Remove-Item Env:\BATTLEZONE_ACTIVE_TANKS -ErrorAction SilentlyContinue
$env:BATTLEZONE_NET_SERVER_LOW_RENDER="1"
.\run.ps1
```

Tank 0 full-render client:

```powershell
$env:BATTLEZONE_NET_MODE="client"
$env:BATTLEZONE_NET_HOST="127.0.0.1"
$env:BATTLEZONE_NET_PORT="51515"
$env:BATTLEZONE_NET_TANK="0"
$env:BATTLEZONE_NET_CONTROLLER="human"
Remove-Item Env:\BATTLEZONE_ACTIVE_TANKS -ErrorAction SilentlyContinue
$env:BATTLEZONE_NET_CLIENT_LOW_RENDER="0"
.\run.ps1
```

Optional tank 1 autonomous low-render local client, for testing a claimed nonzero tank process:

```powershell
$env:BATTLEZONE_NET_MODE="client"
$env:BATTLEZONE_NET_HOST="127.0.0.1"
$env:BATTLEZONE_NET_PORT="51515"
$env:BATTLEZONE_NET_TANK="1"
$env:BATTLEZONE_NET_CONTROLLER="autonomous"
Remove-Item Env:\BATTLEZONE_ACTIVE_TANKS -ErrorAction SilentlyContinue
$env:BATTLEZONE_NET_CLIENT_LOW_RENDER="1"
.\run.ps1
```
