param(
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$venvPython = Join-Path $workspaceRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}

Push-Location $projectRoot
try {
    if ($NoReload) {
        & $venvPython -m uvicorn app.main:app
    }
    else {
        & $venvPython -m uvicorn app.main:app --reload --reload-dir app --reload-dir alembic --reload-exclude "tests/*" --reload-exclude "docs/*" --reload-exclude "exports/*" --reload-exclude "imports/*" --reload-exclude "scripts/*" --reload-exclude "*.md"
    }
}
finally {
    Pop-Location
}