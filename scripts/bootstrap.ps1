# ISV-Release bootstrap: pinned SHA256 download, then invoke the original compiled installer.
param(
    [string]$Action = 'start',
    [string]$InstallDir = '',
    [string]$Port = ''
)
$ErrorActionPreference = 'Stop'
$Project = '@@PROJECT@@'
$Version = '@@VERSION@@'
$Url = '@@WIN_URL@@'
$ExpectedSha = '@@WIN_SHA@@'
$Platform = 'windows-x64'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

$FailureStage = 'cache'
$FailureCode = 'runtime_cache_failed'
function Write-BootstrapFailure([string]$Stage, [string]$Code) {
    # No raw exception text, URL, response, token or filesystem path is persisted.
    try {
        $Dir = Join-Path $env:LOCALAPPDATA ('ISV-Release\' + $Project + '\logs')
        New-Item -ItemType Directory -Force -Path $Dir | Out-Null
        $Record = [ordered]@{
            schema_version = 1
            time = [DateTimeOffset]::UtcNow.ToString('o')
            module = 'bootstrap'
            stage = $Stage
            code = $Code
        }
        $Line = ConvertTo-Json -InputObject $Record -Compress
        [IO.File]::AppendAllText((Join-Path $Dir 'bootstrap.jsonl'),
            $Line + [char]10, (New-Object Text.UTF8Encoding($false)))
    } catch {
        # Diagnostics must never mask the original installer failure.
    }
}
$Base = Join-Path $env:LOCALAPPDATA "ISV-Release\$Project\$Version"
$Cache = Join-Path $Base $ExpectedSha
$Ready = Join-Path $Cache '.ready'
try {
    if (-not (Test-Path -LiteralPath $Ready -PathType Leaf)) {
        New-Item -ItemType Directory -Force -Path $Base | Out-Null
        $Stage = Join-Path $Base ('.install.' + [guid]::NewGuid().ToString('N'))
        try {
            New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'assets'), (Join-Path $Stage 'scripts') | Out-Null
            $Zip = Join-Path $Stage 'runtime.zip'
            $FailureStage = 'download'
            $FailureCode = 'runtime_download_failed'
            Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
            $FailureStage = 'checksum'
            $FailureCode = 'runtime_checksum_mismatch'
            $ActualSha = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($ActualSha -ne $ExpectedSha) { throw 'runtime_checksum_mismatch' }
            $FailureStage = 'unpack'
            $FailureCode = 'runtime_extract_failed'
            $Unpack = Join-Path $Stage 'unpack'
            Expand-Archive -LiteralPath $Zip -DestinationPath $Unpack
            $FailureStage = 'assets'
            $FailureCode = 'runtime_assets_missing'
            $Runtime = Join-Path $Unpack 'runtime'
            $Binary = if ($Project -eq 'product-grabber') { 'product-grabber.exe' } else { 'audience-portrait.exe' }
            if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $Runtime $Platform) $Binary) -PathType Leaf)) {
                throw 'missing_runtime_binary'
            }
            Move-Item -LiteralPath $Runtime -Destination (Join-Path $Stage 'assets\runtime')
            if ($Project -eq 'product-grabber') {
                $Ext = Join-Path $Unpack 'ext'
                if (-not (Test-Path -LiteralPath (Join-Path $Ext 'manifest.json') -PathType Leaf)) {
                    throw 'missing_browser_extension'
                }
                Move-Item -LiteralPath $Ext -Destination (Join-Path $Stage 'assets\ext')
            }
            $FailureStage = 'cache'
            $FailureCode = 'runtime_cache_failed'
            Copy-Item -LiteralPath (Join-Path $Root 'assets\release.json') -Destination (Join-Path $Stage 'assets\release.json')
            Copy-Item -LiteralPath (Join-Path $Root 'scripts\setup-bundled.ps1') -Destination (Join-Path $Stage 'scripts\setup.ps1')
            Copy-Item -LiteralPath (Join-Path $Root 'SKILL.md') -Destination (Join-Path $Stage 'SKILL.md')
            $Lines = @(
                Get-ChildItem -LiteralPath (Join-Path $Stage 'assets') -File -Recurse | ForEach-Object {
                    $Relative = $_.FullName.Substring($Stage.TrimEnd('\').Length + 1).Replace('\', '/')
                    $Digest = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                    "$Digest  $Relative"
                }
            )
            [IO.File]::WriteAllLines((Join-Path $Stage 'assets\MANIFEST.sha256'), $Lines, (New-Object Text.UTF8Encoding($false)))
            Remove-Item -LiteralPath $Unpack, $Zip -Force -Recurse
            [IO.File]::WriteAllText((Join-Path $Stage '.ready'), $ExpectedSha, (New-Object Text.UTF8Encoding($false)))
            if (Test-Path -LiteralPath $Cache) { Remove-Item -LiteralPath $Cache -Recurse -Force }
            Move-Item -LiteralPath $Stage -Destination $Cache
        } finally {
            if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
        }
    }
    $Installer = Join-Path $Cache 'scripts\setup.ps1'
    if ($Project -eq 'product-grabber') {
        $Args = @{ Action = $Action }
        if ($InstallDir) { $Args.InstallDir = $InstallDir }
    } else {
        $Args = @{ Action = $Action }
        if ($InstallDir) { $Args.InstallDir = $InstallDir }
        if ($Port) { $Args.Port = $Port }
    }
    $FailureStage = 'installer'
    $FailureCode = 'installer_failed'
    & $Installer @Args
    if ($LASTEXITCODE -ne 0) {
        $InstallerExit = $LASTEXITCODE
        Write-BootstrapFailure $FailureStage $FailureCode
        exit $InstallerExit
    }
} catch {
    Write-BootstrapFailure $FailureStage $FailureCode
    [Console]::Error.WriteLine('{"ok":false,"error":"bootstrap_failed","code":"' + $FailureCode + '"}')
    exit 1
}
