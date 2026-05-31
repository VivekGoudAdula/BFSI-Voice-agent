# Start ngrok tunnel for the voice agent backend (port 8000).
# Use this if `ngrok` is not recognized in your terminal yet.

$ngrokDir = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe"
$ngrokPaths = @(
    "$ngrokDir\ngrok.exe",
    "$env:ProgramFiles\ngrok\ngrok.exe",
    "$env:LOCALAPPDATA\ngrok\ngrok.exe"
)

# Make ngrok available for this session (winget PATH may not load in old terminals)
if (Test-Path $ngrokDir) {
    $env:Path = "$ngrokDir;$env:Path"
}

$ngrok = $null
foreach ($path in $ngrokPaths) {
    if (Test-Path $path) {
        $ngrok = $path
        break
    }
}

if (-not $ngrok) {
    $found = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($found) {
        $ngrok = $found.Source
    }
}

if (-not $ngrok) {
    Write-Host "ngrok not found. Install with: winget install Ngrok.Ngrok" -ForegroundColor Red
    Write-Host "Then close and reopen this terminal, or run this script again."
    exit 1
}

Write-Host "Starting ngrok on port 8000..." -ForegroundColor Green
Write-Host "Using: $ngrok"
Write-Host ""

# Reuse existing local tunnel if already running
$existing = Get-Process ngrok -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "ngrok is already running (PID $($existing.Id))." -ForegroundColor Yellow
    Write-Host "Open http://127.0.0.1:4040 to see the active Forwarding URL."
    Write-Host "To restart the tunnel, stop it first: Stop-Process -Name ngrok -Force"
    exit 0
}

Write-Host "Copy the HTTPS Forwarding URL into backend/.env as BASE_URL"
Write-Host "Restart the backend after updating .env"
Write-Host ""

# Ensure ngrok agent meets ngrok.com minimum version requirements
$versionOutput = & $ngrok version 2>&1 | Out-String
if ($versionOutput -match 'ngrok version (\d+\.\d+\.\d+)') {
    $current = [version]$Matches[1]
    if ($current -lt [version]"3.20.0") {
        Write-Host "Updating ngrok (installed version is too old)..." -ForegroundColor Yellow
        & $ngrok update
    }
}

Write-Host ""

& $ngrok http 8000
