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

## Controls

- Arrow keys: move and turn
- Space, F, Ctrl, or left mouse: fire
- B: toggle GPU bloom
- R: restart after game over

The lower-left HUD radar shows enemy tank positions relative to your current heading. Enemy returns brighten when scanned, then fade like phosphor.
A stitched HUD panorama shows the forward side views, with a separate rear view below.
GPU bloom uses a post-process filter for vector glow, falling back to the older geometry bloom if the filter is unavailable.
Wireframe blocks, pyramids, and cones act as obstacles. The player is blocked by them, enemy tanks route around their footprints, and shots stop when they hit them.

To show collision debug output:

```
$env:BATTLEZONE_DEBUG = "1"
python test02.py
```
