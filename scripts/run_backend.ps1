param(
    [ValidateRange(1024,65535)][int]$Port = 8000,
    [switch]$Reload
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create the project virtual environment first.' }
$taskTemp = Join-Path $projectRoot 'data\tmp\api'
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$env:PYTHONPATH = $projectRoot
Set-Location -LiteralPath $projectRoot
$taskArguments = @('-m','uvicorn','src.api.main:app','--host','127.0.0.1','--port',"$Port",'--workers','1','--limit-concurrency','32','--timeout-keep-alive','5')
if ($Reload) { $taskArguments += @('--reload','--reload-dir',(Join-Path $projectRoot 'src\api')) }
& $taskPython @taskArguments
exit $LASTEXITCODE
