# yt2y1 installer for Windows
#
# Run this from PowerShell with:
#
#   irm https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-windows.ps1 | iex
#
# It installs Python, Git, ffmpeg and chromaprint if they're missing,
# clones (or updates) yt2y1 into %USERPROFILE%\yt2y1, installs both tools,
# walks you through the free AcoustID key, and finishes with `y1sync doctor`
# so you can see everything is actually ready.
#
# Safe to run more than once -- each step is skipped if it's already done.

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Test-CommandExists($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Update-SessionPath {
    # Installers register PATH changes at the Machine/User level, which an
    # already-open PowerShell window doesn't see until it's reloaded from
    # there -- this pulls the fresh value in without needing a restart.
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

$ErrorActionPreference = "Stop"

Write-Host "yt2y1 installer" -ForegroundColor Green
Write-Host "Downloads music from YouTube and gets it onto an Innioasis Y1 player."
Write-Host ""

# --- 0. winget itself -------------------------------------------------

if (-not (Test-CommandExists "winget")) {
    Write-Host "winget (the Windows Package Manager) was not found." -ForegroundColor Red
    Write-Host "It ships with Windows 11 and recent Windows 10 updates."
    Write-Host "Install 'App Installer' from the Microsoft Store, then run this script again:"
    Write-Host "  https://apps.microsoft.com/detail/9nblggh4nns1"
    exit 1
}

# --- 1-3. Python, Git, ffmpeg via winget -------------------------------

$wingetPackages = @(
    @{ Command = "python"; Id = "Python.Python.3.12"; Name = "Python 3.12" },
    @{ Command = "git";    Id = "Git.Git";             Name = "Git" },
    @{ Command = "ffmpeg"; Id = "Gyan.FFmpeg";          Name = "ffmpeg" }
)

foreach ($pkg in $wingetPackages) {
    if (Test-CommandExists $pkg.Command) {
        Write-Step "$($pkg.Name) already installed, skipping."
        continue
    }
    Write-Step "Installing $($pkg.Name)..."
    winget install --id $pkg.Id -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Installing $($pkg.Name) failed (winget exit code $LASTEXITCODE). " +
              "See the message above for what winget reported."
    }
}

# --- 4. chromaprint (fpcalc) -------------------------------------------
#
# There's no winget package for this, so it's downloaded directly from the
# chromaprint project's own GitHub releases.

if (Test-CommandExists "fpcalc") {
    Write-Step "chromaprint (fpcalc) already installed, skipping."
} else {
    Write-Step "Installing chromaprint (fpcalc)..."
    $binDir = Join-Path $env:USERPROFILE "bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null

    $zipPath = Join-Path $env:TEMP "fpcalc.zip"
    $extractDir = Join-Path $env:TEMP "fpcalc-extract"
    $downloadUrl = "https://github.com/acoustid/chromaprint/releases/download/v1.5.1/chromaprint-fpcalc-1.5.1-windows-x86_64.zip"

    Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $fpcalcExe = Get-ChildItem -Path $extractDir -Filter "fpcalc.exe" -Recurse | Select-Object -First 1
    if (-not $fpcalcExe) {
        throw "fpcalc.exe was not found inside the downloaded archive. " +
              "The chromaprint release layout may have changed -- check " +
              "https://github.com/acoustid/chromaprint/releases"
    }
    Copy-Item $fpcalcExe.FullName -Destination $binDir -Force

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$binDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$binDir", "User")
    }

    Remove-Item $zipPath -ErrorAction SilentlyContinue
    Remove-Item $extractDir -Recurse -ErrorAction SilentlyContinue
}

# --- 5. Confirm everything is actually on PATH now ----------------------

Update-SessionPath

$stillMissing = @("python", "git", "ffmpeg", "fpcalc") | Where-Object { -not (Test-CommandExists $_) }
if ($stillMissing.Count -gt 0) {
    Write-Host ""
    Write-Host "Still not found after install: $($stillMissing -join ', ')" -ForegroundColor Yellow
    Write-Host "This PowerShell window may be holding onto an old PATH. Close it, open a" -ForegroundColor Yellow
    Write-Host "new PowerShell window, and run this script again -- the installs themselves" -ForegroundColor Yellow
    Write-Host "succeeded, so the second run should just pick up from here." -ForegroundColor Yellow
    exit 1
}

# --- 6. Clone or update yt2y1 --------------------------------------------

$repoDir = Join-Path $env:USERPROFILE "yt2y1"
if (Test-Path (Join-Path $repoDir ".git")) {
    Write-Step "yt2y1 already cloned at $repoDir, pulling the latest..."
    Push-Location $repoDir
    git pull
    $gitOk = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $gitOk) { throw "git pull failed in $repoDir." }
} else {
    Write-Step "Cloning yt2y1 into $repoDir..."
    git clone https://github.com/hozemigel/yt2y1 $repoDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed." }
}

# --- 7. Install both tools -----------------------------------------------

Write-Step "Installing yt2mp3 and y1sync..."
Push-Location $repoDir
python -m pip install --upgrade pip
python -m pip install ./yt2mp3
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Installing yt2mp3 failed." }
python -m pip install ./y1sync
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Installing y1sync failed." }
Pop-Location

# --- 8. AcoustID key -------------------------------------------------------

$configDir = Join-Path $env:USERPROFILE ".config\y1sync"
$configFile = Join-Path $configDir "config.toml"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

$hasKey = (Test-Path $configFile) -and
          ((Get-Content $configFile -Raw) -match 'acoustid_key\s*=\s*"[^"]+"')

if ($hasKey) {
    Write-Step "AcoustID key already configured, skipping."
} else {
    Write-Step "Setting up your free AcoustID key..."
    Write-Host "This is what lets y1sync identify tracks accurately instead of guessing"
    Write-Host "from filenames. Opening the signup page in your browser now."
    Write-Host ""
    Write-Host "On that page: log in (a Google or GitHub account works), fill in a Name" -ForegroundColor Yellow
    Write-Host "and Version for the form, submit, then copy the API key it shows you." -ForegroundColor Yellow
    Write-Host ""
    Start-Process "https://acoustid.org/new-application"

    $key = ""
    while ([string]::IsNullOrWhiteSpace($key)) {
        $key = Read-Host "Paste your AcoustID application key here"
    }
    [System.IO.File]::WriteAllText($configFile, "acoustid_key = `"$key`"`n")
    Write-Host "Saved to $configFile"
}

# --- 9. Confirm everything is ready --------------------------------------

Update-SessionPath
Write-Step "Checking everything is ready..."
y1sync doctor

Write-Host ""
Write-Host "All done. Connect your Y1 over USB, then run:" -ForegroundColor Green
Write-Host ""
Write-Host "  y1sync" -ForegroundColor Green
Write-Host ""
