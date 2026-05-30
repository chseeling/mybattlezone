$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $root
try {
    python .\scripts\package_server.py @args
}
finally {
    Pop-Location
}
