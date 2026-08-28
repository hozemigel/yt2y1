# yt2y1 installer for Windows
#
# Run this from PowerShell with:
#
#   irm https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-windows.ps1 | iex
#
# It installs winget itself if missing, then Python, Git, ffmpeg,
# chromaprint and deno (a JS runtime yt-dlp uses for reliable YouTube
# downloads), clones (or updates) yt2y1 into %USERPROFILE%\yt2y1, installs
# both tools, and finishes with `y1sync doctor` so you can see everything
# is actually ready. Audio fingerprinting needs no key or signup: y1sync
# ships with its own AcoustID lookup key. ffmpeg falls back to a direct
# download if winget's own package doesn't take.
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

function Add-ToUserPath($dir) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$dir*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$dir", "User")
    }
}

function Install-WingetBootstrap {
    # winget ships built-in on current Windows 11 and recent Windows 10, but
    # an older or locked-down machine can be missing it entirely. Rather
    # than sending someone to the Microsoft Store and hoping they find their
    # way back, this installs it the same way Microsoft's own CI images do:
    # winget-cli's GitHub release ships the app itself plus a dependencies
    # bundle (VCLibs / WindowsAppRuntime), sideloaded with Add-AppxPackage.
    Write-Step "winget not found -- installing it first..."

    $depsZip = Join-Path $env:TEMP "winget-deps.zip"
    $depsDir = Join-Path $env:TEMP "winget-deps"
    $bundlePath = Join-Path $env:TEMP "winget.msixbundle"

    try {
        Invoke-WebRequest -Uri "https://github.com/microsoft/winget-cli/releases/latest/download/DesktopAppInstaller_Dependencies.zip" -OutFile $depsZip
        Expand-Archive -Path $depsZip -DestinationPath $depsDir -Force

        $arch = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
        $depFiles = Get-ChildItem -Path (Join-Path $depsDir $arch) -Filter "*.appx"
        foreach ($dep in $depFiles) {
            try {
                Add-AppxPackage -Path $dep.FullName -ErrorAction Stop
            } catch {
                # A dependency already present at an equal or newer version
                # makes Add-AppxPackage complain even though nothing is
                # actually wrong -- what matters is whether the main
                # bundle installs, checked after this loop.
                Write-Host "  (skipping $($dep.Name): $_)" -ForegroundColor DarkGray
            }
        }

        Invoke-WebRequest -Uri "https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle" -OutFile $bundlePath
        Add-AppxPackage -Path $bundlePath -ErrorAction Stop
    } catch {
        Write-Host "Automatic winget install didn't work: $_" -ForegroundColor Yellow
        return $false
    } finally {
        Remove-Item $depsZip, $bundlePath -ErrorAction SilentlyContinue
        Remove-Item $depsDir -Recurse -ErrorAction SilentlyContinue
    }

    Update-SessionPath
    return (Test-CommandExists "winget")
}

function Install-FfmpegDirect {
    # Fallback used when winget itself never became available, or its
    # ffmpeg package didn't take -- downloads the same static build the
    # winget package wraps, directly from its publisher, and drops it
    # alongside fpcalc rather than depending on winget at all.
    Write-Step "Installing ffmpeg directly (without winget)..."
    $binDir = Join-Path $env:USERPROFILE "bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null

    $zipPath = Join-Path $env:TEMP "ffmpeg.zip"
    $extractDir = Join-Path $env:TEMP "ffmpeg-extract"

    try {
        Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

        $ffmpegExe = Get-ChildItem -Path $extractDir -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
        if (-not $ffmpegExe) {
            throw "ffmpeg.exe was not found inside the downloaded archive. " +
                  "The build layout may have changed -- check https://www.gyan.dev/ffmpeg/builds/"
        }
        Copy-Item $ffmpegExe.FullName -Destination $binDir -Force

        $ffprobeExe = Get-ChildItem -Path $extractDir -Filter "ffprobe.exe" -Recurse | Select-Object -First 1
        if ($ffprobeExe) {
            Copy-Item $ffprobeExe.FullName -Destination $binDir -Force
        }
        Add-ToUserPath $binDir
    } finally {
        Remove-Item $zipPath -ErrorAction SilentlyContinue
        Remove-Item $extractDir -Recurse -ErrorAction SilentlyContinue
    }
}

$ErrorActionPreference = "Stop"

Write-Host "yt2y1 installer" -ForegroundColor Green
Write-Host "Downloads music from YouTube and gets it onto an Innioasis Y1 player."
Write-Host ""

# --- 0. winget itself -------------------------------------------------

$wingetAvailable = Test-CommandExists "winget"
if (-not $wingetAvailable) {
    $wingetAvailable = Install-WingetBootstrap
}
if (-not $wingetAvailable) {
    Write-Host "winget (the Windows Package Manager) still isn't available." -ForegroundColor Red
    Write-Host "Python and Git need it. Install 'App Installer' from the Microsoft Store" -ForegroundColor Red
    Write-Host "yourself, then run this script again:"
    Write-Host "  https://apps.microsoft.com/detail/9nblggh4nns1"
    # Not exit: this script runs via "irm ... | iex", which executes in the
    # *current* PowerShell session -- exit would close that whole window
    # before the message above could be read, rather than just stopping
    # the script. throw only unwinds this script.
    throw "winget is not available."
}

# --- 1-2. Python, Git via winget ----------------------------------------

$wingetPackages = @(
    @{ Command = "python"; Id = "Python.Python.3.12"; Name = "Python 3.12" },
    @{ Command = "git";    Id = "Git.Git";             Name = "Git" }
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

# --- 3. ffmpeg -------------------------------------------------------
#
# Tried via winget first, since that's the verified path; if winget's
# ffmpeg package doesn't take for some reason, Install-FfmpegDirect below
# gets it the same way chromaprint is fetched -- straight from the
# publisher, no winget involved.

if (Test-CommandExists "ffmpeg") {
    Write-Step "ffmpeg already installed, skipping."
} else {
    Write-Step "Installing ffmpeg..."
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    Update-SessionPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-CommandExists "ffmpeg")) {
        Write-Host "winget's ffmpeg package didn't take -- falling back to a direct download." -ForegroundColor Yellow
        Install-FfmpegDirect
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
    Add-ToUserPath $binDir

    Remove-Item $zipPath -ErrorAction SilentlyContinue
    Remove-Item $extractDir -Recurse -ErrorAction SilentlyContinue
}

# --- 4b. deno (JS runtime for reliable YouTube downloads) ---------------
#
# Not required the way Python/Git/ffmpeg/chromaprint above are -- the
# "still missing" check below and y1sync's own readiness check don't
# depend on it, and yt2mp3 still works without it. But yt-dlp's YouTube
# extraction is markedly less reliable without a JS runtime present
# (more timeouts, occasional failed downloads). Best-effort: caught and
# reported rather than aborting the whole install the way a failed
# ffmpeg or chromaprint step does.

if (Test-CommandExists "deno") {
    Write-Step "deno already installed, skipping."
} else {
    Write-Step "Installing deno..."
    try {
        winget install --id DenoLand.Deno -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "winget exit code $LASTEXITCODE" }
        Update-SessionPath
    } catch {
        Write-Host "Could not install deno automatically: $_" -ForegroundColor Yellow
        Write-Host "YouTube downloads will still work, just less reliably. See" -ForegroundColor Yellow
        Write-Host "https://docs.deno.com/runtime/getting_started/installation/" -ForegroundColor Yellow
    }
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
    # See the winget check above: throw, not exit, so this window stays
    # open long enough for the message to actually be read.
    throw "PATH did not pick up: $($stillMissing -join ', ')"
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

# pip installs console scripts (y1sync.exe, yt2mp3.exe, ...) into a
# per-user Scripts folder when it can't write to Python's own
# site-packages -- which is the common case for a non-admin winget
# install. That folder isn't necessarily on PATH at all (not even after
# Update-SessionPath), unlike the installer-managed tools above: pip
# itself warns "not on PATH" right in its own output when this happens.
# Asking Python for its actual user-site path (rather than guessing the
# "Roaming\Python\Python3XX\Scripts" pattern) keeps this correct across
# Python versions.
$userSiteOutput = python -m site --user-site 2>$null
$userSite = if ($userSiteOutput) { ($userSiteOutput | Select-Object -Last 1).Trim() } else { $null }
if ($userSite) {
    $scriptsDir = Join-Path (Split-Path $userSite -Parent) "Scripts"
    if (Test-Path $scriptsDir) {
        Add-ToUserPath $scriptsDir
        Update-SessionPath
    }
}

# --- 8. Confirm everything is ready --------------------------------------

Update-SessionPath
Write-Step "Checking everything is ready..."
y1sync doctor

Write-Host ""
Write-Host "All done. Connect your Y1 over USB, then run:" -ForegroundColor Green
Write-Host ""
Write-Host "  y1sync" -ForegroundColor Green
Write-Host ""
