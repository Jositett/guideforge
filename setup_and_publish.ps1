<#
.SYNOPSIS
    End-to-end PowerShell setup, installation, verification, and GitHub publishing script for GuideForge.

.DESCRIPTION
    Automates the complete GuideForge setup workflow on Windows / PowerShell 7+:
      1. Extracts `guideforge-uv-project.zip` (from current folder, ~/Downloads, or custom -ZipPath).
      2. Verifies or installs `uv`, `git`, `gh` (GitHub CLI), and `ffmpeg` (via winget / official installer).
      3. Installs Python 3.11 and syncs all open-source packages + extras (`tts`, `agent` for browser-use/Ollama, `ui` for NiceGUI, and `dev`).
      4. Installs the open-source Playwright Chromium browser binary.
      5. Runs Ruff linting, Pytest unit/polyglot tests, open-source license audit, and sample config validation.
      6. Initializes Git, authenticates with GitHub (`gh`), creates the remote repository, and pushes `main`.
      7. Optionally launches the NiceGUI Web Studio & `/api/v1/*` Agent Control Plane (`-LaunchUI`).

.PARAMETER ZipPath
    Path to `guideforge-uv-project.zip`. Automatically searches current directory and ~/Downloads if not specified.

.PARAMETER TargetDir
    Directory where the project should be extracted (default: current directory).

.PARAMETER RepoName
    GitHub repository name to create via `gh repo create` (default: "guideforge").

.PARAMETER Visibility
    GitHub repository visibility: "public" or "private" (default: "public").

.PARAMETER SkipGitHubPush
    If set, sets up and verifies the local `uv` project without pushing to GitHub.

.PARAMETER LaunchUI
    If set, launches the NiceGUI Web Studio (`http://127.0.0.1:8080`) after setup completes.

.EXAMPLE
    .\setup_and_publish.ps1 -RepoName "guideforge" -Visibility "public"

.EXAMPLE
    .\setup_and_publish.ps1 -ZipPath "$HOME\Downloads\guideforge-uv-project.zip" -Visibility "private" -LaunchUI
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ZipPath = "",

    [Parameter(Mandatory = $false)]
    [string]$TargetDir = (Get-Location).Path,

    [Parameter(Mandatory = $false)]
    [string]$RepoName = "guideforge",

    [Parameter(Mandatory = $false)]
    [ValidateSet("public", "private", "internal")]
    [string]$Visibility = "public",

    [Parameter(Mandatory = $false)]
    [switch]$SkipGitHubPush,

    [Parameter(Mandatory = $false)]
    [switch]$LaunchUI
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n================================================================================" -ForegroundColor DarkCyan
    Write-Host "==> $Message" -ForegroundColor Cyan
    Write-Host "================================================================================" -ForegroundColor DarkCyan
}

function Test-CommandExists {
    param([string]$CommandName)
    return $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Refresh-SessionPath {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $uvBin = Join-Path $HOME ".local\bin"
    $cargoBin = Join-Path $HOME ".cargo\bin"
    $env:Path = "$userPath;$machinePath;$uvBin;$cargoBin"
}

# ==============================================================================
# STEP 1: Locate & Extract `guideforge-uv-project.zip` (If Not Already Extracted)
# ==============================================================================
Write-Step "1/6 Locating and Extracting GuideForge Project Files"

$projectRoot = $null

# If already running inside the extracted guideforge directory (where pyproject.toml exists)
if (Test-Path (Join-Path (Get-Location).Path "pyproject.toml")) {
    $projectRoot = (Get-Location).Path
    Write-Host "Detected existing GuideForge project in current directory: $projectRoot" -ForegroundColor Green
} else {
    if ([string]::IsNullOrWhiteSpace($ZipPath)) {
        $candidates = @(
            (Join-Path (Get-Location).Path "guideforge-uv-project.zip"),
            (Join-Path $HOME "Downloads\guideforge-uv-project.zip")
        )
        foreach ($cand in $candidates) {
            if (Test-Path $cand) {
                $ZipPath = $cand
                break
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($ZipPath) -and (Test-Path $ZipPath)) {
        Write-Host "Extracting '$ZipPath' to '$TargetDir'..." -ForegroundColor Yellow
        if (-not (Test-Path $TargetDir)) {
            New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
        }
        Expand-Archive -Path $ZipPath -DestinationPath $TargetDir -Force

        $extractedSubdir = Join-Path $TargetDir "guideforge"
        if (Test-Path (Join-Path $extractedSubdir "pyproject.toml")) {
            $projectRoot = $extractedSubdir
        } elseif (Test-Path (Join-Path $TargetDir "pyproject.toml")) {
            $projectRoot = $TargetDir
        } else {
            throw "Extracted archive, but could not find pyproject.toml inside '$TargetDir'."
        }
        Write-Host "Extracted project to: $projectRoot" -ForegroundColor Green
    } else {
        throw "Could not find 'guideforge-uv-project.zip' in current folder or ~/Downloads. Pass -ZipPath '<path-to-zip>' or run this script inside the project folder."
    }
}

Set-Location $projectRoot

# ==============================================================================
# STEP 2: Verify / Install System Prerequisites (`uv`, `git`, `gh`, `ffmpeg`)
# ==============================================================================
Write-Step "2/6 Checking System Prerequisites (uv, git, gh, ffmpeg)"

Refresh-SessionPath

# 2a. Install `uv` if missing
if (-not (Test-CommandExists "uv")) {
    Write-Host "'uv' not found on PATH. Installing uv via official Astral installer..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    Refresh-SessionPath
    if (-not (Test-CommandExists "uv")) {
        throw "Failed to locate 'uv' after installation. Restart PowerShell and re-run."
    }
}
Write-Host "uv version: $(uv --version)" -ForegroundColor Green

# 2b. Check / install git, gh, and ffmpeg via winget on Windows if missing
$wingetAvailable = Test-CommandExists "winget"

foreach ($tool in @(
    @{ Cmd = "git"; WingetId = "Git.Git"; Name = "Git" },
    @{ Cmd = "gh"; WingetId = "GitHub.cli"; Name = "GitHub CLI (gh)" },
    @{ Cmd = "ffmpeg"; WingetId = "Gyan.FFmpeg"; Name = "FFmpeg" }
)) {
    if (-not (Test-CommandExists $tool.Cmd)) {
        if ($wingetAvailable) {
            Write-Host "Installing $($tool.Name) ($($tool.WingetId)) via winget..." -ForegroundColor Yellow
            winget install --id $tool.WingetId -e --source winget --accept-package-agreements --accept-source-agreements
            Refresh-SessionPath
        } else {
            Write-Warning "$($tool.Name) ('$($tool.Cmd)') is not installed and winget is unavailable. Please install $($tool.Name) manually."
        }
    } else {
        Write-Host "Found $($tool.Name): $((Get-Command $tool.Cmd).Source)" -ForegroundColor Green
    }
}

# ==============================================================================
# STEP 3: Install Python 3.11 & Sync All Open-Source Packages via `uv`
# ==============================================================================
Write-Step "3/6 Installing Python 3.11 & Syncing All Project Dependencies (Core + UI + Agent + TTS + Dev)"

uv python install 3.11

# Sync core + dev dependencies first, then attempt all optional extras (ui, agent, tts)
Write-Host "Syncing uv virtual environment with all extras..." -ForegroundColor Yellow
uv sync --all-groups --all-extras
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Some optional OS-specific TTS wheels could not be installed; syncing core + dev + ui + agent groups..."
    uv sync --all-groups --extra ui --extra agent
}

# ==============================================================================
# STEP 4: Install Open-Source Playwright Chromium Browser
# ==============================================================================
Write-Step "4/6 Installing Open-Source Playwright Chromium Browser Binary"

uv run playwright install chromium

# ==============================================================================
# STEP 5: Run Automated Linter, Unit Tests, License Audit & Agent Schema Check
# ==============================================================================
Write-Step "5/6 Verifying Codebase (Ruff, Pytest, Open-Source Licenses & CLI Validation)"

Write-Host "Running Ruff linter..." -ForegroundColor Yellow
uv run ruff check src tests

Write-Host "Running Pytest test suite..." -ForegroundColor Yellow
$env:GUIDEFORGE_OFFLINE = "1"
uv run pytest
Remove-Item Env:\GUIDEFORGE_OFFLINE -ErrorAction SilentlyContinue

Write-Host "Auditing 100% Open-Source License Manifest..." -ForegroundColor Yellow
uv run guideforge licenses

Write-Host "Validating sample client + developer guide.yaml..." -ForegroundColor Yellow
uv run guideforge validate examples/guide.yaml --json

# ==============================================================================
# STEP 6: Initialize Git & Publish to GitHub via `gh` CLI
# ==============================================================================
if (-not $SkipGitHubPush) {
    Write-Step "6/6 Initializing Git Repository & Publishing to GitHub via gh CLI"

    if (-not (Test-CommandExists "gh")) {
        throw "GitHub CLI ('gh') is not installed. Install it via 'winget install GitHub.cli' and re-run."
    }

    # Check if authenticated with gh; if not, start interactive login
    gh auth status 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "You are not logged into GitHub CLI yet. Launching 'gh auth login'..." -ForegroundColor Yellow
        gh auth login
    }

    if (-not (Test-Path (Join-Path $projectRoot ".git"))) {
        git init -b main
    }

    git add -A
    $gitStatus = git status --porcelain
    if (-not [string]::IsNullOrWhiteSpace($gitStatus)) {
        git commit -m "feat: initial 100% open-source GuideForge uv project with NiceGUI, browser-use & polyglot runner"
    }

    # Check if remote 'origin' already exists
    $remotes = git remote
    if ($remotes -contains "origin") {
        Write-Host "Remote 'origin' already exists. Pushing 'main' branch to origin..." -ForegroundColor Yellow
        git push -u origin main
    } else {
        Write-Host "Creating GitHub repository '$RepoName' (--$Visibility) and pushing..." -ForegroundColor Yellow
        gh repo create $RepoName "--$Visibility" `
            --source=. `
            --remote=origin `
            --description "100% Open-Source Client & Developer Manual Generator with NiceGUI, browser-use, and Polyglot Runner (Node, Python, Go, Rust)" `
            --push
    }

    Write-Host "`nSuccessfully published GuideForge to GitHub!" -ForegroundColor Green
    gh repo view --web 2>$null
} else {
    Write-Step "6/6 Skipped GitHub Push (-SkipGitHubPush specified)"
}

Write-Host "`n================================================================================" -ForegroundColor Green
Write-Host "GuideForge Setup Complete!" -ForegroundColor Green
Write-Host "  Project Root : $projectRoot"
Write-Host "  Run CLI      : uv run guideforge --help"
Write-Host "  Agent Schema : uv run guideforge agent-manifest --json"
Write-Host "  Start Studio : uv run guideforge ui --port 8080 --open"
Write-Host "================================================================================`n" -ForegroundColor Green

if ($LaunchUI) {
    Write-Host "Launching GuideForge NiceGUI Studio at http://127.0.0.1:8080 ..." -ForegroundColor Cyan
    uv run guideforge ui --config examples/guide.yaml --port 8080 --open
}
