[CmdletBinding()]
param(
    [Parameter(Position=0)][ValidateSet('doctor','clients','python','ddn','frontend','configure','init','run','verify','network','ci')]
    [string]$Stage = 'doctor',
    [string]$Python = 'python',
    [Parameter(Mandatory=$true)][string]$Evidence
)
$ErrorActionPreference = 'Stop'
$repository = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $repository
try {
    & $Python (Join-Path $PSScriptRoot 'native.py') $Stage --evidence $Evidence
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
