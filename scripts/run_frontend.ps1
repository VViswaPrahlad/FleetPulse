param(
    [ValidateRange(1024,65535)][int]$Port = 5173,
    [ValidateRange(1024,65535)][int]$BackendPort = 8000,
    [switch]$Preview
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'Node.js and npm are required. See docs/day8_report.md.'
}
if (-not (Test-Path -LiteralPath "$taskRoot\dashboard\node_modules")) {
    throw 'Run npm.cmd ci --prefix dashboard from FleetPulse before launching.'
}
$env:FLEETPULSE_API_PORT = "$BackendPort"
$env:npm_config_cache = "$taskRoot\data\tmp\npm-day8"
$taskMode = if ($Preview) { 'preview' } else { 'dev' }
Write-Host "FleetPulse frontend: http://127.0.0.1:$Port (API proxy: $BackendPort)"
& npm.cmd --prefix "$taskRoot\dashboard" run $taskMode -- --port "$Port"
exit $LASTEXITCODE
