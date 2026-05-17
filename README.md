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
- Space: fire
- B: toggle bloom

The lower-left HUD radar shows enemy tank positions relative to your current heading. Enemy returns brighten when scanned, then fade like phosphor.

To show collision debug output:

```
$env:BATTLEZONE_DEBUG = "1"
python test02.py
```
