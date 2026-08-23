$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$desktopRoot = Join-Path $projectRoot "desktop"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment was not found: $python"
}

Push-Location $projectRoot
try {
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath (Join-Path $PSScriptRoot "dist") `
        --workpath (Join-Path $PSScriptRoot "work") `
        (Join-Path $PSScriptRoot "rusty-backend.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "Python backend packaging failed."
    }
}
finally {
    Pop-Location
}

Push-Location $desktopRoot
try {
    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Electron production build failed."
    }

    npm exec electron-builder -- --win nsis --x64
    if ($LASTEXITCODE -ne 0) {
        throw "Windows installer packaging failed."
    }
}
finally {
    Pop-Location
}
