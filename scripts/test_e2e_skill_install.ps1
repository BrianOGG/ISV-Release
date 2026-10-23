# E2E final Skill smoke on native Windows PowerShell 5.1; uses synthetic local browser.
param(
    [Parameter(Mandatory=$true)][string]$SkillZip,
    [Parameter(Mandatory=$true)][string]$RuntimeZip
)
$ErrorActionPreference = 'Stop'
$Root = Join-Path $env:RUNNER_TEMP ("e2e-final-" + [guid]::NewGuid().ToString('N'))
$Skill = Join-Path $Root 'skill'
$Runtime = Join-Path $Root 'runtime'
$Installed = Join-Path $Root 'installed'
$Port = 18787
$env:E2E_DATA_DIR = Join-Path $Root 'userdata'
$env:E2E_CHROME_PATH = Join-Path $Root 'synthetic-chrome.exe'
$env:PYTHONIOENCODING = 'utf-8'
$Started = $false
$Bundled = Join-Path $Skill 'scripts/setup-bundled.ps1'
New-Item -ItemType Directory -Force -Path $Root,$Skill,$Runtime | Out-Null
[IO.File]::WriteAllText($env:E2E_CHROME_PATH, 'offline browser sentinel')
try {
    Expand-Archive -LiteralPath $SkillZip -DestinationPath $Skill
    Expand-Archive -LiteralPath $RuntimeZip -DestinationPath $Runtime
    $Source = Join-Path $Runtime 'runtime/windows-x64'
    if (-not (Test-Path -LiteralPath (Join-Path $Source 'e2e-dmp.exe') -PathType Leaf)) {
        throw 'Compiled E2E binary missing in final runtime'
    }
    foreach ($File in @(Get-ChildItem -LiteralPath $Skill -Filter '*.ps1' -File -Recurse)) {
        [byte[]]$Bytes = [IO.File]::ReadAllBytes($File.FullName)
        if ($Bytes.Length -lt 3 -or $Bytes[0] -ne 239 -or $Bytes[1] -ne 187 -or $Bytes[2] -ne 191) {
            throw ('PowerShell 5.1 script lacks UTF-8 BOM: ' + $File.Name)
        }
        $ParsedErrors = $null
        $Tokens = $null
        [void][System.Management.Automation.Language.Parser]::ParseInput(
            [IO.File]::ReadAllText($File.FullName, [Text.Encoding]::UTF8),
            [ref]$Tokens, [ref]$ParsedErrors)
        if ($ParsedErrors.Count -ne 0) { throw 'PowerShell 5.1 installer has syntax errors' }
    }
    $Destination = Join-Path $Skill 'assets/runtime/windows-x64'
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source '*') -Destination $Destination -Recurse -Force
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action prepare -InstallDir $Installed -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'E2E prepare failed' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action install -InstallDir $Installed -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'E2E install failed' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action start -InstallDir $Installed -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'E2E start failed after install' }
    $Started = $true
    $StatusText = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action status -InstallDir $Installed -Port $Port | Out-String)
    if ($LASTEXITCODE -ne 0 -or -not (($StatusText | ConvertFrom-Json).running)) { throw 'E2E status failed' }
    $Page = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + $Port + "/") -TimeoutSec 15
    if ($Page.StatusCode -ne 200 -or $Page.Content -notmatch '<html') { throw 'E2E homepage missing' }
    $Js = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + $Port + "/static/app.js") -TimeoutSec 15
    if ($Js.StatusCode -ne 200) { throw 'E2E frontend script unavailable' }
    $Brands = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + $Port + "/api/brands") -TimeoutSec 15
    if ($Brands.StatusCode -ne 200 -or $Brands.Headers['Content-Type'] -notlike '*json*') {
        throw 'E2E brands API unavailable'
    }
    Write-Output 'Final E2E Skill: Windows 5.1 prepare/install/start/status/UI/API passed'
} finally {
    if ($Started) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action stop -InstallDir $Installed -Port $Port | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'E2E stop failed after install' }
    }
    Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
}
