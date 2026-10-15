param([switch]$UseExistingPackages)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        if ($UseExistingPackages) { python -m venv .venv --system-site-packages }
        else { python -m venv .venv }
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    $requirementsPath = if (Test-Path -LiteralPath 'requirements-lock.txt') { 'requirements-lock.txt' } else { 'requirements.txt' }
    & '.\.venv\Scripts\python.exe' -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & '.\.venv\Scripts\python.exe' -m backend.cli demo
    if ($LASTEXITCODE -ne 0) { throw 'Demo initialization failed.' }
    Write-Host 'Ready. Run .\Start-HarvestShield.ps1'
} finally { Pop-Location }
