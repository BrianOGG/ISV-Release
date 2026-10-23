# Public PowerShell 5.1 Skill bootstrap for the compiled module runtime.
param(
    [ValidateSet('prepare','install','start','stop','status','setup','doctor','version','idle')]
    [string]$Action = 'prepare',
    [string]$InstallDir = '',
    [int]$Port = 0,
    [string]$Archive = ''
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = ''
$Prefix = @()
if (Get-Command python.exe -ErrorAction SilentlyContinue) {
    & python.exe -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) { $Python = 'python.exe' }
}
if (-not $Python -and (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    $Python = 'py.exe'
    $Prefix = @('-3.12')
}
if (-not $Python) {
    [Console]::Error.WriteLine('Python 3.12 is required. Ask your Agent to install CPython 3.12 first.')
    exit 1
}
$ArgsList = @((Join-Path $Root 'scripts/module_installer.py'), $Action)
if ($InstallDir) { $ArgsList += @('--install-dir', $InstallDir) }
if ($Port -gt 0) { $ArgsList += @('--port', [string]$Port) }
if ($Archive) { $ArgsList += @('--archive', $Archive) }
& $Python @Prefix @ArgsList
exit $LASTEXITCODE
