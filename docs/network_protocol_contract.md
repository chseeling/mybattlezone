# Network Protocol Contract

This document captures the current multiplayer protocol and the remaining work needed before treating it as a deployable multiplayer contract.

## Status

- Current transport: custom JSON messages over UDP.
- Current target: LAN/local multiplayer prototype.
- Later publishable transport candidates:
  - Steam Networking Sockets, already named in the Plan S network note.
  - ENet, a lightweight reliable-UDP option if we want a smaller non-Steam transport layer.
- Server authority: the server owns terrain, arena state, tank claims, tank poses, shots, hits, lives, damage events, investigation pause, and snapshots.
- Client authority: a client owns only its controller intent and session commands for its claimed player/tank.

## Authority Rules

- The server is authoritative for simulation.
- A player may claim one tank at a time.
- Tank intent is scoped to the claimed tank.
- Session commands are issued by the player/client process, not by the tank avatar itself.
- Terrain selection is server-owned.
- While the arena is an empty lobby, the first connected player gets terrain authority.
- Terrain authority belongs to the player identity, not the tank body.
- For the first release, all teams are teams of one.
- Non-human teams attack human teams only.
- If no human has claimed a nonzero tank, that tank can run as server-side autonomous fallback.
- Late participation is the default model: a player can join by claiming an available tank without synchronizing a full lobby start ceremony.

## Identity And Claiming

Each accepted claim has:

- `tank_id`: claimed tank id.
- `player_id`: server-assigned identity such as `player1`.
- `claim_token`: server-generated secret token.
- `ownership_generation`: monotonically increasing generation for that tank claim.
- `client_sequence`: client-side sequence for tank intent messages.

The server rejects controlled messages when:

- the source address does not match the current claim,
- the claim token does not match,
- the ownership generation does not match,
- an input sequence is stale or duplicated,
- the requested tank is invalid or unclaimable.

## Client To Server Messages

All messages include:

```json
{
  "type": "...",
  "protocol": 1,
  "tank_id": "0"
}
```

### `join`

Purpose: request a tank claim.

Reliability target: reliable or retried until `join_ack`.

Current fields:

```json
{
  "type": "join",
  "protocol": 1,
  "tank_id": "0",
  "controller": "HUMAN"
}
```

### `input`

Purpose: tank intent for the claimed tank.

Reliability target: unreliable, sequenced, latest-wins.

Current fields:

```json
{
  "type": "input",
  "protocol": 1,
  "tank_id": "0",
  "player_id": "player1",
  "claim_token": "...",
  "ownership_generation": 1,
  "client_sequence": 42,
  "controller": "HUMAN",
  "throttle": 0.0,
  "turn": 0.0,
  "fire": false,
  "barrel_tilt": 0.0,
  "desired_world_pos": [0.0, 0.0, 0.0],
  "desired_heading": 0.0,
  "desired_barrel_tilt": 0.0
}
```

`desired_*` fields are optional and mainly support autonomous/controller variants.

### `leave`

Purpose: release the current claim.

Reliability target: best-effort legacy packet. New clients should prefer reliable `release_claim` through the `command` envelope.

Fields:

```json
{
  "type": "leave",
  "protocol": 1,
  "tank_id": "0",
  "claim_token": "...",
  "ownership_generation": 1
}
```

### `ready` / `unready` / `release_claim` / `claim_tank`

Purpose: express lobby participation and claim lifecycle through the reliable session command envelope.

Reliability target: reliable.

Current rules:

- `ready` and `unready` apply to the player's current claim.
- New claims default to ready for the first release, keeping late participation simple.
- `release_claim` returns the tank to the arena pool.
- `claim_tank` validates the requested target tank. Switching to another target is a protocol affordance but is not client-enabled yet.

### `start`

Purpose: request arena start from lobby.

Reliability target: reliable.

Fields are the same claim identity envelope as `leave`.

### `restart`

Purpose: request restart after game over.

Reliability target: reliable.

Current rule: only tank `0` can request restart.

### `terrain`

Purpose: request lobby terrain change.

Reliability target: reliable, ordered with other session commands.

Fields:

```json
{
  "type": "terrain",
  "protocol": 1,
  "tank_id": "0",
  "claim_token": "...",
  "ownership_generation": 1,
  "action": "set",
  "environment_index": 0
}
```

Current actions: `set`, `next`, `previous`.

### `investigation`

Purpose: request investigation pause/resume.

Reliability target: reliable or at least repeated until snapshot confirms state.

Current rule: only tank `0` can request investigation pause/resume.

Fields:

```json
{
  "type": "investigation",
  "protocol": 1,
  "tank_id": "0",
  "claim_token": "...",
  "ownership_generation": 1,
  "active": true
}
```

### `enemy_fire`

Purpose: tank 0 client toggles enemy shooting suspension.

Reliability target: reliable or eventually replaced by a general session command.

Current rule: only tank `0` can issue it.

## Server To Client Messages

### `join_ack`

Purpose: accept or reject a claim.

Reliability target: sent in response to retried `join`.

Fields:

```json
{
  "type": "join_ack",
  "protocol": 1,
  "tank_id": "0",
  "accepted": true,
  "reason": "",
  "connected_tanks": ["0"],
  "claimable_tanks": ["0", "1", "2", "3"],
  "player_id": "player1",
  "claim_token": "...",
  "ownership_generation": 1
}
```

### `snapshot`

Purpose: authoritative state stream.

Reliability target: unreliable, latest-wins.

Current send rate: `NETWORK_SNAPSHOT_RATE`, currently 25 Hz.

Top-level fields:

```json
{
  "type": "snapshot",
  "protocol": 1,
  "time": 0.0,
  "environment_index": 0,
  "waiting_to_start": true,
  "game_over": false,
  "enemy_shooting_suspended": false,
  "terrain_authority_player_id": "player1",
  "terrain_authority_tank_id": "0",
  "terrain_locked": false,
  "player_lives": 3,
  "player_damage_event_serial": 0,
  "player_hit_effect_serial": 0,
  "player_hit_effect_pos": [0.0, 0.0, 0.0],
  "player_hit_effect_hpr": [0.0, 0.0, 0.0],
  "player_investigation_event": null,
  "tank_hit_event_serial": 0,
  "tank_hit_event": {},
  "shot_ground_burst_serial": 0,
  "shot_ground_burst_event": {},
  "connected_tanks": ["0"],
  "claimable_tanks": ["0", "1", "2", "3"],
  "claims": {},
  "lobby": {},
  "server_status": {},
  "tanks": {},
  "shots": {}
}
```

Per-tank state:

```json
{
  "pos": [0.0, 0.0, 0.0],
  "hpr": [0.0, 0.0, 0.0],
  "barrel_tilt": 0.0,
  "hidden": false,
  "shooting": false,
  "alive": true,
  "reconstituting": false,
  "lives": 3,
  "debug_state": ""
}
```

Per-shot state:

```json
{
  "pos": [0.0, 0.0, 0.0],
  "hpr": [0.0, 0.0, 0.0],
  "hidden": true,
  "shooting": false
}
```

Lobby state:

```json
{
  "state": "WAITING",
  "phase": "lobby",
  "start_policy": "tank0_required",
  "can_start": true,
  "required_tanks": ["0"],
  "team_model": "teams_of_one",
  "late_join": true,
  "ready_count": 1,
  "players": [
    {
      "player_id": "player1",
      "tank_id": "0",
      "controller": "HUMAN",
      "team_id": "T0",
      "role": "driver",
      "ready": true
    }
  ],
  "tanks": [
    {
      "tank_id": "0",
      "team_id": "T0",
      "claimable": true,
      "claimed": true,
      "player_id": "player1",
      "controller": "HUMAN",
      "status": "CLAIMED",
      "lives": 3
    }
  ],
  "terrain": {
    "environment_index": 0,
    "environment_name": "SIMPLE RANGE",
    "authority_player_id": "player1",
    "authority_tank_id": "0",
    "locked": false
  }
}
```

## Events In Snapshot Stream

Current event delivery is serial-number based inside snapshots.

- `tank_hit_event_serial` / `tank_hit_event`: tank destruction and hit effects.
- `player_damage_event_serial`: tank 0 damage feedback.
- `player_hit_effect_serial`: tank 0 fatal hit effect.
- `player_investigation_event`: shooter, player, and shot trajectory evidence for I-mode.
- `shot_ground_burst_serial` / `shot_ground_burst_event`: ground impact burst replay.

This works for local/LAN tests, but the contract should eventually become a small ordered event stream with retention/ack rules for important one-shot events.

## Current Reliability Model

Implemented:

- Join is retried until accepted.
- Input is sequenced; stale input is rejected.
- Snapshots are latest-wins.
- Clients time out when snapshots stop.
- Server releases claims when input/presence stops.
- Session commands can use a reliable `command` / `command_ack` envelope.
- Duplicate command retries are acknowledged without reapplying the command.

Missing:

- Ordered event stream for important one-shot events.
- Explicit protocol mismatch response.
- Rich command result/error presentation in the client UI.

## Multiplayer Readiness Gaps

1. Dynamic tank rebinding.
   - The client lobby can show available tanks and issue ready/unready/release actions, but true cross-tank switching still needs the client to rebind camera/control/HUD away from startup `NETWORK_TANK_ID`.

2. Event stream normalization.
   - Needed so hits, deaths, ground bursts, investigation events, drone events, and future team events all follow one serial/retention model.

3. Reconnect behavior.
   - Needed to define whether a returning player can reclaim the same tank/player id after a short disconnect.

4. Multi-human claim/switch flow.
   - `claim_tank` is currently guarded because the client still binds camera/control/HUD to startup `NETWORK_TANK_ID`.
   - Needed for "return tank, then join another team's tank" behavior without restarting the client process.

5. Team affordance.
   - First release can keep teams of one, but snapshots and commands should not block later team ids and team comms.

6. Drone authority decision.
   - Current drone is local/full-render client behavior.
   - Future multiplayer needs a decision: local render helper only, server-authoritative recon asset, or player-owned session ability.

7. Transport decision.
   - Keep custom JSON/UDP for the next hardening slice.
   - Consider Steam Networking Sockets or ENet after command reliability and event semantics are clear.

8. Test matrix.
   - One server plus tank 0 full client.
   - One server plus two human tank clients.
   - Tank 0 human plus claimed autonomous tank.
   - Late join into active arena.
   - Disconnect/reconnect.
   - Terrain change before start.
   - Restart after game over.
   - Investigation pause/resume.

## Reliable Command Envelope

Implemented for session commands while keeping high-rate input and snapshots on the lightweight UDP path.

Client command:

```json
{
  "type": "command",
  "protocol": 1,
  "tank_id": "0",
  "claim_token": "...",
  "ownership_generation": 1,
  "command_id": "player1:17",
  "command": "terrain",
  "payload": {
    "action": "next"
  }
}
```

Server ack:

```json
{
  "type": "command_ack",
  "protocol": 1,
  "command_id": "player1:17",
  "accepted": true,
  "reason": "",
  "result": {}
}
```

Currently routed through this envelope:

- `terrain`
- `start`
- `restart`
- `investigation`
- `enemy_fire`
- `ready`
- `unready`
- `release_claim`
- `claim_tank`

Ready/claim command rules:

- `ready`: marks the current claim ready. New accepted claims default to ready so the current quick-start flow still works.
- `unready`: marks the current claim unready while the arena is still in lobby.
- `release_claim`: reliably releases the current claim.
- `claim_tank`: validates a requested target tank. Current-tank claims succeed as idempotent confirmations; switching to a different tank is rejected until the client can safely rebind all local tank-id assumptions.
- `can_start`: true only when required tanks are connected and ready.

Benefit: lobby/session commands are dependable without rewriting the high-rate input/snapshot path.

## Recommended Next Slice

Add dynamic tank switching on top of the lobby command contract:

- dynamic client tank rebinding for `claim_tank`,
- available-tank selection that can switch away from startup `NETWORK_TANK_ID`,
- reconnect/reclaim policy for short disconnects,
- regression tests for ready/unready/release/rejoin.

Benefit: this makes tank switching and future multi-human lobbies explicit rather than relying on process restart or disconnect behavior.
