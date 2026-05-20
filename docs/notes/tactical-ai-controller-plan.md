# Tactical AI Controller Branch Plan

## Goal

Create a smarter enemy tank controller that uses the existing `TankController` interface and prepares the codebase for a later reinforcement-learning controller.

## Scope

- Add a `TacticalAiTankController` alongside the existing sine-path controller.
- Keep shot physics centralized and barrel-direction constrained.
- Keep movement dt-based and obstacle-respecting.
- Avoid training or external ML dependencies in this branch.

## First Implementation

1. Add an observation helper for enemy controllers:
   - own tank pose
   - player relative bearing and distance
   - approximate line of sight
   - nearby obstacle clearance
   - current shooting state

2. Add tactical rule states:
   - seek line of sight
   - aim at player
   - fire only when near aligned
   - reposition after firing or when blocked

3. Add a controller switch constant:
   - `ENEMY_CONTROLLER_MODE = "TACTICAL"` or `"SINE"`

4. Verify:
   - compile
   - offscreen startup
   - enemies still fire only along barrel direction
   - no obstacle-leaping regression

## Current Branch Status

- Added `ENEMY_CONTROLLER_MODE` with `TACTICAL` as the active mode.
- Added `TacticalAiTankController`.
- Added `build_tank_observation(...)` for later RL reuse.
- Added obstacle-aware line-of-sight checks through existing shot intersection logic.
- Tactical AI aims in place when it has line of sight and a usable range.
- Tactical AI repositions laterally/forward/back when blocked or outside preferred range.
- Verified compile and offscreen tactical simulation with no large movement jumps.

## Later RL Path

- Reuse the observation helper as the RL observation vector.
- Reuse `TankCommand` as the action output.
- Train outside the rendered Panda3D loop when possible.
- Deploy a trained policy as `RlTankController`.
