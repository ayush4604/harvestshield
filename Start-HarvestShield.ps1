param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 8501,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Run Setup-HarvestShield.ps1 first to create the project environment.'
}
if ($BackendPort -eq $FrontendPort -or $BackendPort -lt 1024 -or $FrontendPort -lt 1024 -or $BackendPort -gt 65535 -or $FrontendPort -gt 65535) {
    throw 'Use distinct ports between 1024 and 65535.'
}
$runtimeRoot = Join-Path $projectRoot 'work'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$env:HARVESTSHIELD_API_URL = "http://127.0.0.1:$BackendPort"
$env:PYTHONUTF8 = '1'
$backendUrl = "$env:HARVESTSHIELD_API_URL/health"
$backendRunning = $false
try {
    $health = Invoke-RestMethod -Uri $backendUrl -TimeoutSec 2
    if ($health.service -ne 'harvestshield') { throw 'The backend port belongs to another application.' }
    $backendRunning = $true
} catch {
    $occupied = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue
    if ($occupied) { throw "Port $BackendPort is occupied. Select another BackendPort." }
}
$frontendOccupied = Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction SilentlyContinue
if ($frontendOccupied) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($frontendOccupied[0].OwningProcess)"
    if ($process.CommandLine -notlike "*$projectRoot*" -or $process.CommandLine -notlike '*streamlit*') {
        throw "Frontend port $FrontendPort is occupied. Select another FrontendPort."
    }
}
$owned = @()
if (-not $backendRunning) {
    $quotedRoot = '"' + $projectRoot + '"'
    $backend = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','backend.api:app','--app-dir',$quotedRoot,'--host','127.0.0.1','--port',"$BackendPort") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'backend.stdout.log') -RedirectStandardError (Join-Path $runtimeRoot 'backend.stderr.log') -PassThru
    $owned += [pscustomobject]@{ id = $backend.Id; role = 'backend'; executable = $pythonPath }
}
if ($frontendOccupied) {
    Write-Host 'Existing project frontend retained. Its backend configuration must match your selected BackendPort.'
} else {
    $frontendPath = '"' + (Join-Path $projectRoot 'frontend\app.py') + '"'
    $frontend = Start-Process -FilePath $pythonPath -ArgumentList @('-m','streamlit','run',$frontendPath,'--server.address','127.0.0.1','--server.port',"$FrontendPort",'--server.headless','true') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend.stdout.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend.stderr.log') -PassThru
    $owned += [pscustomobject]@{ id = $frontend.Id; role = 'frontend'; executable = $pythonPath }
}
if ($owned.Count -gt 0) {
    $pidPath = Join-Path $runtimeRoot 'services.json'
    $previous = @()
    if (Test-Path -LiteralPath $pidPath) {
        $parsedPrevious = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
        $previous = @($parsedPrevious)
    }
    ConvertTo-Json -InputObject @($previous + $owned) -Depth 4 | Set-Content -LiteralPath $pidPath -Encoding utf8
}
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri $backendUrl -TimeoutSec 2
        $ui = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/_stcore/health" -TimeoutSec 2 -UseBasicParsing
        if ($health.service -eq 'harvestshield' -and $ui.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw 'Services did not become ready. Inspect work/*.stderr.log; stop using Stop-HarvestShield.ps1.' }
Write-Host "HarvestShield: http://127.0.0.1:$FrontendPort"
if ($env:HARVESTSHIELD_ENV -eq 'production') {
    Write-Host 'Production mode: interactive API documentation is disabled.'
} else {
    Write-Host "FastAPI docs: http://127.0.0.1:$BackendPort/docs"
}
Write-Host 'Stop with .\Stop-HarvestShield.ps1'
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$FrontendPort" }
