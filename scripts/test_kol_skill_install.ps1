# Real Windows PowerShell 5.1 smoke for the assembled KOL Skill and compiled runtime.
# Uses a synthetic browser sentinel; never authenticates or makes platform requests.
param(
    [Parameter(Mandatory=$true)][string]$SkillZip,
    [Parameter(Mandatory=$true)][string]$RuntimeZip
)
$ErrorActionPreference = 'Stop'
$TestRoot = Join-Path $env:RUNNER_TEMP ("kol-final-skill-" + [guid]::NewGuid().ToString('N'))
$SkillRoot = Join-Path $TestRoot 'skill'
$RuntimeRoot = Join-Path $TestRoot 'runtime'
$InstallDir = Join-Path $TestRoot 'installed'
$Port = 18789
$env:KOL_DATA_DIR = Join-Path $TestRoot 'data'
$env:KOL_BROWSER_EXECUTABLE = Join-Path $TestRoot 'synthetic-chrome.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = '1'
$Started = $false

function Assert-PowerShellScripts {
    param([string]$Root)
    $Scripts = @(Get-ChildItem -LiteralPath $Root -Filter '*.ps1' -File -Recurse)
    if ($Scripts.Count -lt 3) { throw 'Missing PowerShell Skill scripts' }
    foreach ($File in $Scripts) {
        [byte[]]$Bytes = [IO.File]::ReadAllBytes($File.FullName)
        if ($Bytes.Length -lt 3 -or $Bytes[0] -ne 239 -or $Bytes[1] -ne 187 -or $Bytes[2] -ne 191) {
            throw ("Windows PowerShell UTF-8 BOM missing: " + $File.Name)
        }
        $ParsedErrors = $null
        $Tokens = $null
        [void][System.Management.Automation.Language.Parser]::ParseInput(
            [IO.File]::ReadAllText($File.FullName, [Text.Encoding]::UTF8),
            [ref]$Tokens, [ref]$ParsedErrors)
        if ($ParsedErrors.Count -gt 0) { throw ("Skill PowerShell syntax invalid: " + $File.Name) }
    }
}

function Api-Json([string]$Path) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + $Port + $Path) -TimeoutSec 30
    if ($response.StatusCode -ne 200 -or $response.Headers['Content-Type'] -notlike '*json*') {
        throw ('Workbench API is not JSON: ' + $Path)
    }
    return ($response.Content | ConvertFrom-Json)
}

New-Item -ItemType Directory -Force -Path $TestRoot, $SkillRoot, $RuntimeRoot | Out-Null
# A configured browser path verifies the installer without downloading Chromium in CI.
[IO.File]::WriteAllText($env:KOL_BROWSER_EXECUTABLE, 'synthetic-browser-sentinel')
try {
    Expand-Archive -LiteralPath $SkillZip -DestinationPath $SkillRoot -ErrorAction Stop
    Expand-Archive -LiteralPath $RuntimeZip -DestinationPath $RuntimeRoot -ErrorAction Stop
    Assert-PowerShellScripts -Root $SkillRoot
    $PlatformRuntime = Join-Path $RuntimeRoot 'runtime/windows-x64'
    if (-not (Test-Path -LiteralPath (Join-Path $PlatformRuntime 'kol-selection.exe') -PathType Leaf)) {
        throw 'Final runtime archive does not contain Windows KOL executable'
    }
    $Payload = Join-Path $SkillRoot 'assets/runtime/windows-x64'
    New-Item -ItemType Directory -Force -Path $Payload | Out-Null
    Copy-Item -Path (Join-Path $PlatformRuntime '*') -Destination $Payload -Recurse -Force

    $Bundled = Join-Path $SkillRoot 'scripts/setup-bundled.ps1'
    $CacheCopy = Join-Path $TestRoot 'cached-setup.ps1'
    Copy-Item -LiteralPath $Bundled -Destination $CacheCopy
    if ([IO.File]::ReadAllBytes($CacheCopy)[0] -ne 239) {
        throw 'PowerShell BOM was not preserved in the simulated installer cache'
    }

    # Execute user-facing bundled installer with Windows PowerShell 5.1.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action prepare -InstallDir $InstallDir -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Bundled installer prepare failed' }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action install -InstallDir $InstallDir -Port $Port
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $InstallDir 'kol-selection.exe'))) {
        throw 'Bundled compiled runtime install failed'
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action start -InstallDir $InstallDir -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Installed Windows Skill start failed' }
    $Started = $true

    $Status = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action status -InstallDir $InstallDir -Port $Port | Out-String
    if ($LASTEXITCODE -ne 0 -or -not (($Status | ConvertFrom-Json).running)) {
        throw 'Installed Windows Skill status failed'
    }
    $Health = Api-Json '/api/health'
    if ($Health.status -ne 'ok') { throw 'Workbench health failed after install' }
    $Tasks = @(Api-Json '/api/workflows')
    $Demo = @($Tasks | Where-Object { $_.archived_demo -eq $true } | Select-Object -First 1)
    if ($Demo.Count -ne 1 -or $Demo[0].config.targets.Count -ne 23) {
        throw 'Offline 23-KOL demo failed to initialize after final Skill install'
    }
    $Detailed = Api-Json ('/api/workflows/' + $Demo[0].id)
    if ($Detailed.modules.screening.status -ne 'COMPLETED') {
        throw 'Offline KOL demo screening report is incomplete'
    }
    $Report = Invoke-WebRequest -UseBasicParsing -Uri (
        'http://127.0.0.1:' + $Port + '/api/workflows/' + $Demo[0].id +
        '/modules/screening/download/report.html') -TimeoutSec 30
    if ($Report.StatusCode -ne 200 -or $Report.Content -notmatch '<html') {
        throw 'Offline KOL HTML report missing from installed Skill'
    }
    Write-Output 'Packaged KOL Skill: Windows 5.1 prepare/install/start/status/demo/report passed'
} finally {
    if ($Started) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Bundled -Action stop -InstallDir $InstallDir -Port $Port | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Installed Windows Skill stop failed' }
    }
    Remove-Item -LiteralPath $TestRoot -Recurse -Force -ErrorAction SilentlyContinue
}
