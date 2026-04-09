param(
    [string]$OutputRoot = "",
    [string]$PackageName = "VideoSubtitleLearning",
    [switch]$SkipFrontendBuild,
    [switch]$SkipTauriBuild,
    [switch]$SkipVenvCopy,
    [switch]$SkipModelCopy,
    [switch]$SkipFFmpegCopy,
    [switch]$PreserveRuntimeData,
    [switch]$CleanOutput
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-ToolPath {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction Stop
    return $command.Source
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )

    Push-Location $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Copy-Tree {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExcludeDirectories = @(),
        [string[]]$ExcludeFiles = @()
    )

    if (-not (Test-Path $Source)) {
        return $false
    }

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null

    $robocopyArgs = @(
        $Source,
        $Destination,
        "/E",
        "/R:1",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP"
    )

    if ($ExcludeDirectories.Count -gt 0) {
        $robocopyArgs += "/XD"
        $robocopyArgs += $ExcludeDirectories
    }

    if ($ExcludeFiles.Count -gt 0) {
        $robocopyArgs += "/XF"
        $robocopyArgs += $ExcludeFiles
    }

    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE while copying $Source"
    }

    return $true
}

function Resolve-ProjectPath {
    param([string]$ProjectRoot, [string]$RelativePath)
    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $RelativePath))
}

function Get-VenvBasePythonHome {
    param([string]$VenvDir)

    $cfgPath = Join-Path $VenvDir "pyvenv.cfg"
    if (-not (Test-Path $cfgPath)) {
        return $null
    }

    $homeLine = Get-Content $cfgPath | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
    if (-not $homeLine) {
        return $null
    }

    $homeValue = ($homeLine -split '=', 2)[1].Trim()
    if ([string]::IsNullOrWhiteSpace($homeValue)) {
        return $null
    }

    if (Test-Path $homeValue) {
        return [System.IO.Path]::GetFullPath($homeValue)
    }

    return $null
}

function Copy-PortablePythonRuntime {
    param(
        [string]$VenvDir,
        [string]$Destination
    )

    if (-not (Test-Path $VenvDir)) {
        return $false
    }

    $baseHome = Get-VenvBasePythonHome -VenvDir $VenvDir
    if (-not $baseHome) {
        return $false
    }

    Write-Step "Copying embedded Python base runtime"
    [void](Copy-Tree -Source $baseHome -Destination $Destination)

    $venvSitePackages = Join-Path $VenvDir "Lib\site-packages"
    $runtimeSitePackages = Join-Path $Destination "Lib\site-packages"
    if (Test-Path $venvSitePackages) {
        Write-Step "Copying Python dependencies into embedded runtime"
        New-Item -ItemType Directory -Force -Path $runtimeSitePackages | Out-Null
        [void](Copy-Tree -Source $venvSitePackages -Destination $runtimeSitePackages)
    }

    return $true
}

function Reset-Directory {
    param([string]$Path)

    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Resolve-FFmpegSourceDir {
    param([string]$ProjectRoot)

    $projectDir = Join-Path $ProjectRoot "ffmpeg"
    if (Test-Path (Join-Path $projectDir "ffmpeg.exe")) {
        return $projectDir
    }

    $ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($ffmpegCommand) {
        return Split-Path -Parent $ffmpegCommand.Source
    }

    return $null
}

function Resolve-WebView2Loader {
    param([string]$SrcTauriDir)

    $searchRoots = @(
        (Join-Path $SrcTauriDir "target\release"),
        (Join-Path $SrcTauriDir "target\debug")
    )

    foreach ($root in $searchRoots) {
        if (-not (Test-Path $root)) {
            continue
        }

        $match = Get-ChildItem -Path $root -Filter "WebView2Loader.dll" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($match) {
            return $match.FullName
        }
    }

    return $null
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Resolve-ProjectPath $projectRoot "frontend"
$srcTauriDir = Resolve-ProjectPath $projectRoot "src-tauri"
$backendDir = Resolve-ProjectPath $projectRoot "backend"
$venvDir = Resolve-ProjectPath $projectRoot ".venv"
$runtimePythonDir = Resolve-ProjectPath $projectRoot "runtime\python"
$modelsDir = Resolve-ProjectPath $projectRoot "models"
$readmePath = Resolve-ProjectPath $projectRoot "README.md"
$desktopDocPath = Resolve-ProjectPath $projectRoot "docs\desktop-packaging-and-deployment.md"
$portableDocPath = Resolve-ProjectPath $projectRoot "docs\portable-build-guide.md"

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Resolve-ProjectPath $projectRoot "dist-portable"
}
else {
    $OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
}

$packageRoot = Join-Path $OutputRoot $PackageName
$portableExePath = Join-Path $packageRoot "$PackageName.exe"

if ($CleanOutput -and (Test-Path $packageRoot)) {
    $resolvedPackageRoot = [System.IO.Path]::GetFullPath($packageRoot)
    $resolvedOutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
    if (-not $resolvedPackageRoot.StartsWith($resolvedOutputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean output outside the expected output root: $resolvedPackageRoot"
    }

    Write-Step "Cleaning old portable output"
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

$npmPath = Get-ToolPath "npm"

if (-not $SkipFrontendBuild) {
    Write-Step "Building frontend"
    Invoke-External -FilePath $npmPath -ArgumentList @("--prefix", $frontendDir, "run", "build") -WorkingDirectory $projectRoot
}

if (-not $SkipTauriBuild) {
    Write-Step "Building Tauri desktop binary (production no-bundle)"
    Invoke-External -FilePath $npmPath -ArgumentList @("run", "tauri", "--", "build", "--no-bundle") -WorkingDirectory $projectRoot
}

$tauriExeSource = Join-Path $srcTauriDir "target\release\video_subtitle_learning_app.exe"
if (-not (Test-Path $tauriExeSource)) {
    throw "Tauri release executable not found: $tauriExeSource"
}

Write-Step "Copying desktop executable"
Copy-Item -LiteralPath $tauriExeSource -Destination $portableExePath -Force

$webview2Loader = Resolve-WebView2Loader -SrcTauriDir $srcTauriDir
if ($webview2Loader) {
    Write-Step "Copying WebView2Loader.dll"
    Copy-Item -LiteralPath $webview2Loader -Destination (Join-Path $packageRoot "WebView2Loader.dll") -Force
}

Write-Step "Copying backend"
[void](Copy-Tree -Source $backendDir -Destination (Join-Path $packageRoot "backend") -ExcludeDirectories @("__pycache__", ".pytest_cache", ".mypy_cache") -ExcludeFiles @("*.pyc", "*.pyo"))

if (-not $SkipVenvCopy) {
    $embeddedPythonDestination = Join-Path $packageRoot "runtime\python"
    $embeddedCopied = Copy-PortablePythonRuntime -VenvDir $venvDir -Destination $embeddedPythonDestination
    if (-not $embeddedCopied -and (Test-Path $runtimePythonDir)) {
        Write-Step "Copying existing runtime/python"
        [void](Copy-Tree -Source $runtimePythonDir -Destination $embeddedPythonDestination)
        $embeddedCopied = $true
    }

    if (-not $embeddedCopied -and (Test-Path $venvDir)) {
        Write-Step "Embedded runtime unavailable, falling back to copying .venv"
        [void](Copy-Tree -Source $venvDir -Destination (Join-Path $packageRoot ".venv"))
    }
}

if (-not $SkipModelCopy -and (Test-Path $modelsDir)) {
    Write-Step "Copying local models"
    [void](Copy-Tree -Source $modelsDir -Destination (Join-Path $packageRoot "models"))
}
else {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "models") | Out-Null
}

$ffmpegSourceDir = $null
if (-not $SkipFFmpegCopy) {
    $ffmpegSourceDir = Resolve-FFmpegSourceDir -ProjectRoot $projectRoot
}

if ($ffmpegSourceDir) {
    Write-Step "Copying FFmpeg binaries"
    [void](Copy-Tree -Source $ffmpegSourceDir -Destination (Join-Path $packageRoot "ffmpeg"))
}
else {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "ffmpeg") | Out-Null
}

if (-not $PreserveRuntimeData) {
    Write-Step "Resetting runtime data directories for a clean package"
    foreach ($relativeDir in @("data", "outputs", "temp")) {
        Reset-Directory -Path (Join-Path $packageRoot $relativeDir)
    }
}

Write-Step "Creating portable runtime directories"
$directories = @(
    "data",
    "data\logs",
    "data\videos",
    "data\huggingface",
    "outputs",
    "outputs\analysis",
    "outputs\exports",
    "outputs\transcripts",
    "outputs\translations",
    "temp",
    "runtime",
    "runtime\python"
)

foreach ($relativeDir in $directories) {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot $relativeDir) | Out-Null
}

if (Test-Path $readmePath) {
    Copy-Item -LiteralPath $readmePath -Destination (Join-Path $packageRoot "README.md") -Force
}

if (Test-Path $desktopDocPath) {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "docs") | Out-Null
    Copy-Item -LiteralPath $desktopDocPath -Destination (Join-Path $packageRoot "docs\desktop-packaging-and-deployment.md") -Force
}

if (Test-Path $portableDocPath) {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "docs") | Out-Null
    Copy-Item -LiteralPath $portableDocPath -Destination (Join-Path $packageRoot "docs\portable-build-guide.md") -Force
}

$portableReadme = @"
# Portable package notes

This build is prepared for same-directory portable deployment.

Expected layout:
- $PackageName.exe
- backend\
- runtime\python\
- ffmpeg\
- models\
- data\
- outputs\
- temp\

Notes:
- The desktop app will use its own folder as APP_ROOT.
- If ffmpeg.exe and ffprobe.exe are present in .\ffmpeg\, the backend will use them first.
- If local Whisper models are present in .\models\, the backend will load them from there first.
- Runtime status inside Settings can verify FFmpeg, model availability, GPU, CUDA and cuDNN.
- The portable build prefers an embedded Python runtime under .\runtime\python\ and falls back to .\.venv\ only if needed.
"@
Set-Content -LiteralPath (Join-Path $packageRoot "PORTABLE-NOTES.txt") -Value $portableReadme -Encoding UTF8

Write-Step "Portable package ready"
Write-Host ""
Write-Host "Output: $packageRoot" -ForegroundColor Green
Write-Host "Executable: $portableExePath" -ForegroundColor Green
