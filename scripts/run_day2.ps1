param(
    [Parameter(Mandatory=$true)][string]$Script,
    [string]$JavaHome = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$ScriptArgs
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath "$JavaHome\bin\java.exe")) {
    throw "JDK not found at $JavaHome"
}
$env:JAVA_HOME = $JavaHome
$env:Path = "$JavaHome\bin;$env:Path"
$env:PYSPARK_PYTHON = "$projectRoot\.venv\Scripts\python.exe"
$env:PYSPARK_DRIVER_PYTHON = $env:PYSPARK_PYTHON
$env:SPARK_LOCAL_IP = '127.0.0.1'
$taskTemp = "$projectRoot\data\tmp"
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$env:SPARK_LOCAL_DIRS = "$taskTemp\spark"
$env:JAVA_TOOL_OPTIONS = "-Djava.io.tmpdir=$taskTemp"
$env:PYTHONPATH = $projectRoot
Set-Location -LiteralPath $projectRoot
& $env:PYSPARK_PYTHON $Script @ScriptArgs
exit $LASTEXITCODE
