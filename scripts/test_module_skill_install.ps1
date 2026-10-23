# Exercise *final* compiled-module Skill with Windows PowerShell 5.1, without live accounts.
param(
    [Parameter(Mandatory=$true)][ValidateSet('kol-selection','e2e')][string]$Project,
    [Parameter(Mandatory=$true)][string]$SkillZip,
    [Parameter(Mandatory=$true)][string]$RuntimeZip
)
$ErrorActionPreference = 'Stop'
$Root = Join-Path $env:RUNNER_TEMP ("module-skill-final-" + [guid]::NewGuid().ToString('N'))
$Skill = Join-Path $Root 'skill'
$Installed = Join-Path $Root 'installed'
$Port = if ($Project -eq 'kol-selection') { 18788 } else { 18787 }
$env:PYTHONIOENCODING = 'utf-8'
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = '1'
$env:KOL_DATA_DIR = Join-Path $Root 'kol-data'
$env:E2E_DATA_DIR = Join-Path $Root 'e2e-data'
$env:KOL_BROWSER_EXECUTABLE = Join-Path $Root 'synthetic-chrome.exe'
$env:E2E_CHROME_PATH = $env:KOL_BROWSER_EXECUTABLE
$Started = $false
New-Item -ItemType Directory -Force -Path $Root, $Skill | Out-Null
[IO.File]::WriteAllText($env:KOL_BROWSER_EXECUTABLE, 'offline synthetic browser')
try {
    Expand-Archive -LiteralPath $SkillZip -DestinationPath $Skill
    $Bootstrap = Join-Path $Skill 'scripts/setup.ps1'
    [byte[]]$Bytes = [IO.File]::ReadAllBytes($Bootstrap)
    if ($Bytes.Length -lt 3 -or $Bytes[0] -ne 239 -or $Bytes[1] -ne 187 -or $Bytes[2] -ne 191) {
        throw 'PowerShell UTF-8 BOM missing'
    }
    $Tokens = $null
    $Errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput(
        [IO.File]::ReadAllText($Bootstrap, [Text.Encoding]::UTF8),
        [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count -gt 0) { throw 'PowerShell 5.1 syntax error' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bootstrap -Action prepare -InstallDir $Installed
    if ($LASTEXITCODE -ne 0) { throw 'Final Skill prepare failed' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bootstrap -Action install -InstallDir $Installed -Archive $RuntimeZip
    if ($LASTEXITCODE -ne 0) { throw 'Final Skill offline verified install failed' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bootstrap -Action start -InstallDir $Installed -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Final Skill start failed' }
    $Started = $true
    $Status = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bootstrap -Action status -InstallDir $Installed -Port $Port | Out-String)
    if ($LASTEXITCODE -ne 0 -or -not (($Status | ConvertFrom-Json).running)) {
        throw 'Final Skill status failed'
    }
    $HomePage = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + $Port + "/") -TimeoutSec 15
    if ($HomePage.StatusCode -ne 200 -or $HomePage.Content -notmatch '<html') {
        throw 'Final Skill HTML workbench unavailable'
    }
    Write-Output 'Compiled-module final Skill: prepare/install/start/status/html passed'
} finally {
    if ($Started) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bootstrap -Action stop -InstallDir $Installed -Port $Port | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Final Skill stop failed' }
    }
    Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
}
