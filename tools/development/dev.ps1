[CmdletBinding(PositionalBinding=$false)]
param(
    [Parameter(Mandatory=$true)][string]$Repository,
    [string]$Distribution = 'Ubuntu-24.04',
    [Parameter(Position=0, ValueFromRemainingArguments=$true)][string[]]$DevArguments
)
# Repository is an absolute Linux path inside this WSL distribution.
$ErrorActionPreference = 'Stop'
if (-not $Repository.StartsWith('/')) { throw 'Repository must be an absolute WSL Linux path.' }
if (-not $DevArguments) { $DevArguments = @('doctor') }
& wsl.exe --distribution $Distribution --cd $Repository --exec bash tools/development/dev.sh @DevArguments
exit $LASTEXITCODE
