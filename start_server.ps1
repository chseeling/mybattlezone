param(
    [switch]$SetupOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

Push-Location $root
try {
    if (-not (Test-Path $venvPython)) {
        python -m venv .venv
    }

    & $venvPython -m pip install -r requirements.txt

    if ($SetupOnly) {
        exit 0
    }

    if ($args.Count -gt 0) {
        & $venvPython -m battlezone.server @args
    }
    else {
        & $venvPython -m battlezone.server --host 0.0.0.0 --port 51515 --ui logs
    }
}
finally {
    Pop-Location
}
