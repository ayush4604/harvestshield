$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pidPath = Join-Path $projectRoot 'work\services.json'
if (-not (Test-Path -LiteralPath $pidPath)) { Write-Host 'No project-owned service record.'; return }
$parsedRecords = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
$records = @($parsedRecords)
foreach ($record in $records) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.id)" -ErrorAction SilentlyContinue
    $expected = if ($record.role -eq 'backend') { 'backend.api:app' } else { 'streamlit' }
    # Windows venv redirectors may spawn a child interpreter; verify both identities.
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($record.id)" -ErrorAction SilentlyContinue)
    foreach ($candidate in @($children) + @($process)) {
        if (-not $candidate) { continue }
        if ($candidate.CommandLine -like "*$projectRoot*" -and $candidate.CommandLine -like "*$expected*") {
            Stop-Process -Id $candidate.ProcessId -ErrorAction SilentlyContinue
            Write-Host "Stopped project-owned $($record.role) process $($candidate.ProcessId)."
        } elseif ($candidate.ProcessId -eq $record.id) {
            Write-Warning "Did not stop PID $($candidate.ProcessId): identity does not match this project."
        } else {
            Write-Verbose "Skipped non-interpreter child PID $($candidate.ProcessId)."
        }
    }
}
Remove-Item -LiteralPath $pidPath
