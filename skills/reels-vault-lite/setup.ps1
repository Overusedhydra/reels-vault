param(
    [switch]$Install,
    [switch]$WithModel,
    [string]$Model = "nemotron-3.5"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BinDir = Join-Path $env:LOCALAPPDATA "ReelsVault\bin"
$NemoBin = Join-Path $env:LOCALAPPDATA "Programs\NeMoSpeech\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$env:PATH = "$BinDir;$NemoBin;$env:PATH"

function Find-Tool([string]$Name) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }
    return $null
}

$Python = Find-Tool "python"
if (-not $Python) { $Python = Find-Tool "py" }
if (-not $Python) {
    Write-Host "Python 3.9+ is required. Install it from https://www.python.org/downloads/"
    exit 1
}
& $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python 3.9+ is required. Install it from https://www.python.org/downloads/"
    exit 1
}

$FFmpeg = Find-Tool "ffmpeg"
$YtDlp = Find-Tool "yt-dlp"
$Nemo = Find-Tool "nemo-speech"
$Missing = $false

if (-not $FFmpeg) {
    Write-Host "ffmpeg is required. Install it with: winget install Gyan.FFmpeg"
    exit 1
}

if (-not $YtDlp) {
    if ($Install) {
        Write-Host "Installing yt-dlp to $BinDir"
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile (Join-Path $BinDir "yt-dlp.exe")
        $YtDlp = Join-Path $BinDir "yt-dlp.exe"
        if (-not (Test-Path $YtDlp)) {
            Write-Host "yt-dlp install did not produce $YtDlp"
            exit 1
        }
    } else {
        Write-Host "yt-dlp is required. Re-run with -Install."
        $Missing = $true
    }
}

if (-not $Nemo) {
    if ($Install) {
        Write-Host "Installing NVIDIA nemo-speech"
        $Installer = Join-Path $env:TEMP "nemo-speech-install.ps1"
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/NVIDIA/NeMo-Speech.cpp/raw/main/scripts/install.ps1" -OutFile $Installer
            if (-not (Test-Path $Installer)) {
                throw "nemo-speech installer download failed"
            }
            & $Installer -BinaryOnly
        } finally {
            Remove-Item -Force -ErrorAction SilentlyContinue $Installer
        }
        $Nemo = Join-Path $NemoBin "nemo-speech.exe"
        if (-not (Test-Path $Nemo)) {
            Write-Host "nemo-speech install did not produce $Nemo"
            exit 1
        }
    } else {
        Write-Host "nemo-speech is required. Re-run with -Install."
        $Missing = $true
    }
}

if ($Missing) { exit 1 }

if ($WithModel) {
    if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
        Write-Host "curl.exe is required for model downloads. Windows 10/11 normally includes it."
        exit 1
    }
    Write-Host "Downloading NVIDIA $Model (about 708 MB for the default Q8 model)"
    & $Nemo pull $Model
}

& $Python (Join-Path $ScriptDir "scripts\reels_vault_lite.py") status
