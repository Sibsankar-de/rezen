$ErrorActionPreference = "Stop"

# Rezen Installer for Windows - Remote Device & Screen Control CLI
# Usage:
#   powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/Sibsankar-de/rezen/main/install.ps1 | iex"

function Write-Info($msg)    { Write-Host "[rezen] $msg" -ForegroundColor Cyan }
function Write-Success($msg) { Write-Host "[rezen] $msg" -ForegroundColor Green }
function Write-Warn($msg)    { Write-Host "[rezen] WARN: $msg" -ForegroundColor Yellow }
function Write-Err($msg)     { Write-Host "[rezen] ERROR: $msg" -ForegroundColor Red }

function Test-CommandExists($cmd) {
    return [bool](Get-Command -Name $cmd -ErrorAction SilentlyContinue)
}

function Show-Banner {
    Write-Host "  ____                              " -ForegroundColor Cyan
    Write-Host " |  _ \    ___   ____   ___   _ __  " -ForegroundColor Cyan
    Write-Host " | |_) |  / _ \ |_  /  / _ \ | '_ \ " -ForegroundColor Cyan
    Write-Host " |  _ <  |  __/  / /  |  __/ | | | |" -ForegroundColor Cyan
    Write-Host " |_| \_\  \___| /___|  \___| |_| |_|" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Remote Device & Screen Control CLI (Windows)" -ForegroundColor DarkGray
    Write-Host ""
}

# ── 1. OS check ───────────────────────────────────────────────────────────────
function Check-OS {
    if ($env:OS -notlike "*Windows*") {
        Write-Err "This installer is intended for Windows. For Linux, use install.sh."
        exit 1
    }
    Write-Info "Platform: Windows [OK]"
}

# ── 2. Configure execution policy ─────────────────────────────────────────────
function Configure-ExecutionPolicy {
    $allowed = @("Unrestricted", "RemoteSigned", "Bypass")
    $current = (Get-ExecutionPolicy).ToString()
    if ($current -notin $allowed) {
        Write-Info "Adjusting PowerShell ExecutionPolicy for CurrentUser to RemoteSigned..."
        try {
            Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction SilentlyContinue
        } catch {}
        try {
            Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}

# ── 3. Git check ──────────────────────────────────────────────────────────────
function Check-Git {
    if (-not (Test-CommandExists "git")) {
        Write-Warn "git not found."
        if (Test-CommandExists "winget") {
            Write-Info "Attempting to install Git via winget..."
            try {
                winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
                $env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            } catch {
                Write-Warn "winget installation encountered an issue."
            }
        }
        if (-not (Test-CommandExists "git")) {
            Write-Err "Git is required. Please install Git from https://git-scm.com/download/win and rerun."
            exit 1
        }
    }
    $gitVer = git --version
    Write-Info "Git: $gitVer [OK]"
}

# ── 4. Python check ───────────────────────────────────────────────────────────
function Check-Python {
    $foundPython = $false
    foreach ($bin in @("python", "py", "python3")) {
        if (Test-CommandExists $bin) {
            try {
                $check = & $bin -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) {
                    $ver = (& $bin --version) 2>&1
                    Write-Info "Python: $ver [OK]"
                    $foundPython = $true
                    break
                }
            } catch {}
        }
    }

    if (-not $foundPython) {
        Write-Warn "Python 3.12+ not detected."
        if (Test-CommandExists "winget") {
            Write-Info "Attempting to install Python 3.12 via winget..."
            try {
                winget install --id Python.Python.3.12 -e --source winget --accept-source-agreements --accept-package-agreements
                $env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            } catch {
                Write-Warn "Automatic Python installation through winget failed."
            }
        } else {
            Write-Warn "winget not found. uv will automatically manage Python runtimes if needed."
        }
    }
}

# ── 5. uv package manager check ───────────────────────────────────────────────
function Check-Uv {
    if (-not (Test-CommandExists "uv")) {
        Write-Info "uv not found. Installing uv (Python package manager)..."
        
        $installed = $false
        # Method 1: Official Astral installer executed with Bypass execution policy
        try {
            powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
            if ($LASTEXITCODE -eq 0) {
                $installed = $true
            }
        } catch {
            Write-Warn "Astral web installer encountered an issue: $_"
        }

        # Method 2: Fallback to winget if needed
        if (-not $installed -and (Test-CommandExists "winget")) {
            Write-Info "Attempting uv installation via winget..."
            try {
                winget install --id astral-sh.uv -e --source winget --accept-source-agreements --accept-package-agreements
            } catch {
                Write-Warn "winget installation for uv failed."
            }
        }

        # Refresh PATH for current session
        $localBin = Join-Path $env:USERPROFILE ".local\bin"
        $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
        if (Test-Path $localBin) { $env:PATH = "$localBin;$env:PATH" }
        if (Test-Path $cargoBin) { $env:PATH = "$cargoBin;$env:PATH" }

        if (-not (Test-CommandExists "uv")) {
            Write-Err "uv command still not accessible. Please install uv manually from https://docs.astral.sh/uv/ and rerun."
            exit 1
        }
    }
    $uvVer = uv --version
    Write-Info "uv: $uvVer [OK]"
}

# ── 6. Fetch or update repo ───────────────────────────────────────────────────
$global:IsUpdate = $false

function Fetch-Rezen($installDir, $repoUrl) {
    if (Test-Path (Join-Path $installDir ".git")) {
        $global:IsUpdate = $true
        Write-Info "Existing installation found at $installDir - updating to latest version..."
        try {
            git -C "$installDir" fetch --depth 1 origin main
            git -C "$installDir" reset --hard origin/main
        } catch {
            git -C "$installDir" pull --ff-only
        }
    } else {
        Write-Info "Cloning Rezen into $installDir..."
        if (-not (Test-Path $installDir)) {
            New-Item -ItemType Directory -Path $installDir -Force | Out-Null
        }
        git clone --depth 1 $repoUrl "$installDir"
    }
}

# ── 7. Install dependencies ───────────────────────────────────────────────────
function Install-Deps($installDir) {
    Write-Info "Installing Python dependencies (this may take a moment)..."
    Push-Location "$installDir"
    try {
        & uv sync --no-dev
        if ($LASTEXITCODE -ne 0) {
            Write-Err "uv sync failed. Check terminal output for details."
            exit 1
        }
        Write-Success "Dependencies successfully installed."
    } finally {
        Pop-Location
    }
}

# ── 8. Install launchers ──────────────────────────────────────────────────────
function Install-Launchers($installDir, $binDir) {
    if (-not (Test-Path $binDir)) {
        New-Item -ItemType Directory -Path $binDir -Force | Out-Null
    }

    # 1. Windows Command Prompt Batch Script (.cmd)
    $cmdPath = Join-Path $binDir "rezen.cmd"
    $cmdContent = "@echo off`r`nuv run --project `"$installDir`" rezen %*`r`n"
    [System.IO.File]::WriteAllText($cmdPath, $cmdContent, [System.Text.Encoding]::ASCII)

    # 2. PowerShell Script (.ps1)
    $ps1Path = Join-Path $binDir "rezen.ps1"
    $ps1Content = "& uv run --project `"$installDir`" rezen @args`r`n"
    [System.IO.File]::WriteAllText($ps1Path, $ps1Content, [System.Text.Encoding]::UTF8)

    Write-Success "Launchers installed at: $binDir\rezen"
}

# ── 9. Configure PATH ─────────────────────────────────────────────────────────
function Configure-Path($binDir) {
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $paths = if ($userPath) { $userPath -split ";" } else { @() }
    
    $normalizedBin = (Resolve-Path $binDir -ErrorAction SilentlyContinue).Path
    $alreadyInPath = $false
    foreach ($p in $paths) {
        if ($p -and (Resolve-Path $p -ErrorAction SilentlyContinue).Path -eq $normalizedBin) {
            $alreadyInPath = $true
            break
        }
    }

    if (-not $alreadyInPath) {
        $newPath = if ($userPath) { "$userPath;$binDir" } else { $binDir }
        [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        $env:PATH = "$binDir;$env:PATH"
        Write-Warn "Added $binDir to your User PATH."
    }
}

# ── 10. Verify ────────────────────────────────────────────────────────────────
function Verify-Install($installDir) {
    try {
        & uv run --project "$installDir" rezen --help > $null 2>&1
        Write-Success "Verification passed - rezen is ready!"
    } catch {
        Write-Warn "Verification check could not run automatically. Try typing 'rezen' in a new terminal."
    }
}

# ═════════════════════════════════════════════════════════════════════════════
# Main Execution
# ═════════════════════════════════════════════════════════════════════════════
function Main {
    Show-Banner
    Write-Info "Starting Rezen installation on Windows..."
    Write-Host ""

    $RepoUrl = "https://github.com/Sibsankar-de/rezen.git"
    $InstallDir = if ($env:REZEN_INSTALL_DIR) { $env:REZEN_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "rezen" }
    $BinDir = if ($env:REZEN_BIN_DIR) { $env:REZEN_BIN_DIR } else { Join-Path $env:USERPROFILE ".local\bin" }

    Check-OS
    Configure-ExecutionPolicy
    Check-Git
    Check-Python
    Check-Uv
    Fetch-Rezen -installDir $InstallDir -repoUrl $RepoUrl
    Install-Deps -installDir $InstallDir
    Install-Launchers -installDir $InstallDir -binDir $BinDir
    Configure-Path -binDir $BinDir
    Verify-Install -installDir $InstallDir

    Write-Host ""
    Write-Success "==========================================="
    if ($global:IsUpdate) {
        Write-Success "  Rezen updated successfully!              "
    } else {
        Write-Success "  Rezen installed successfully!            "
    }
    Write-Success "==========================================="
    Write-Host ""
    Write-Info "Run it with:  rezen"
    Write-Info "If 'rezen' is not recognized, restart your terminal to reload PATH."
    Write-Info "Tip: Run terminal as Administrator if you need to control elevated windows."
    Write-Host ""
}

Main
