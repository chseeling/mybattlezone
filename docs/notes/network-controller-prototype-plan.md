# Network Controller Prototype Plan

Goal: prove the existing tank controller split can support multiplayer without changing the core game loop too much.

## Milestone 1: Local UDP Input

- Host runs the authoritative simulation.
- Client sends input commands for one remote tank.
- Host maps that client to a `RemoteTankController`.
- Host owns shooting, collision, lives, respawn, and investigation state.

## Milestone 2: Host Snapshots

- Host broadcasts state snapshots to the most recent client address.
- Client applies tank, shot, lives, environment, and game-start state from snapshots.
- Client remains non-authoritative: it renders host state and sends input only.
- Current snapshots are immediate state application; interpolation is a later milestone.

## Runtime Modes

- Normal: no networking.
- Host: set `BATTLEZONE_NET_MODE=host`.
- Client: set `BATTLEZONE_NET_MODE=client`.

Useful environment variables:

- `BATTLEZONE_NET_HOST`: host address, default `127.0.0.1`. For LAN hosting, set this to `0.0.0.0` or the machine's LAN address.
- `BATTLEZONE_NET_PORT`: UDP port, default `51515`.
- `BATTLEZONE_NET_TANK`: remote tank id, default `1`.
- `BATTLEZONE_NET_CLIENT_LOW_RENDER`: client-only lighter render mode, default `1`. Set to `0` to compare against the full client HUD/render path.
- `BATTLEZONE_ACTIVE_TANKS`: comma-separated active non-player tanks. Normal mode defaults to `1,2,3`; network host/client mode defaults to `1` for a tank 0 + tank 1 only test.

## Next Milestones

- Add simple join/leave and tank assignment.
- Keep tuning snapshot interpolation and client-side jitter smoothing.
- Later: replace direct UDP join with Steam lobbies or Steam Networking Sockets.
