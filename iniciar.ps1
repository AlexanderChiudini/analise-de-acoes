$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path '.runtime/python.exe') {
    & '.runtime/python.exe' '-I' 'server.py'
} else {
    python server.py
}
