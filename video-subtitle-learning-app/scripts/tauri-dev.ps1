$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $projectRoot "frontend"

npm --prefix $frontendDir run dev -- --host 127.0.0.1 --strictPort
