$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $projectRoot "frontend"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$backendLog = Join-Path $projectRoot "backend-dev.log"
$backendErrLog = Join-Path $projectRoot "backend-dev.err.log"
$backendPort = 8000

function Test-PortListening {
  param([int]$Port)

  try {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
    return $null -ne $listener
  } catch {
    return $false
  }
}

if (-not (Test-Path $pythonExe)) {
  throw "Python virtual environment not found at $pythonExe. Please prepare the project .venv first."
}

if (-not (Test-PortListening -Port $backendPort)) {
  $backendArgs = @(
    "-m",
    "uvicorn",
    "backend.app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$backendPort"
  )

  Start-Process -FilePath $pythonExe `
    -ArgumentList $backendArgs `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden | Out-Null

  Start-Sleep -Seconds 2
}

npm --prefix $frontendDir run dev -- --host 127.0.0.1 --strictPort
