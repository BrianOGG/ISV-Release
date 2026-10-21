# Offline developer diagnostics; Windows PowerShell 5.1+, no bundled runtime required.
param(
    [string]$Output = '',
    [ValidateRange(1, 168)][int]$Hours = 24
)
$ErrorActionPreference = 'Stop'
$Project = '@@PROJECT@@'
if ($Project -notin @('product-grabber', 'audience-portrait')) { throw 'invalid project' }

$AllowedModules = @('server','entry','queue','llm','web_app','web_app_memory','run_web')
$AllowedStages = @('startup','http.request','queue.persist','queue.collect','queue.state','queue.pump',
    'analysis.enqueue','analysis.run','analysis.http','scheduler.run','process.uncaught',
    'process.unhandled_rejection','portrait.crawl','task.portrait','task.merge','merge.upload',
    'merge.inspect','merge.prepare')
$BootStages = @('platform','download','checksum','unpack','assets','cache','installer')
$BootCodes = @('unsupported_platform','runtime_download_failed','runtime_checksum_mismatch',
    'runtime_extract_failed','runtime_assets_missing','runtime_cache_failed',
    'installer_failed','bootstrap_failed')
$AllowedCodes = @('EACCES','EPERM','ENOENT','ENOSPC','EIO','EADDRINUSE','ECONNREFUSED',
    'ECONNRESET','ETIMEDOUT','ENOTFOUND','ERR_INVALID_URL','ERR_SQLITE_ERROR',
    'ssr_not_found','ssr_timeout','empty_ssr','result_timeout','inflight_timeout',
    'login_required','detail_images_timeout','open_tab_failed','invalid_ssr','upstream_http',
    'instance_locked','item_missing','images_missing','image_download_failed',
    'EAGAIN','EPIPE','ECONNABORTED','EBUSY','EEXIST','EINVAL')
$Cutoff = [DateTimeOffset]::UtcNow.AddHours(-$Hours)
$Now = [DateTimeOffset]::UtcNow
$UserHome = [Environment]::GetFolderPath('UserProfile')
$DataRoot = if ($Project -eq 'product-grabber') {
    Join-Path $UserHome '.product-grabber\data'
} else {
    Join-Path $env:LOCALAPPDATA 'AudiencePortrait'
}
$BootRoot = Join-Path $env:LOCALAPPDATA ("ISV-Release\" + $Project + '\logs')
$ReleasePath = Join-Path (Split-Path -Parent $PSScriptRoot) 'assets\release.json'
$Version = 'unknown'
if (Test-Path -LiteralPath $ReleasePath -PathType Leaf) {
    try {
        $Manifest = Get-Content -LiteralPath $ReleasePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$Manifest.version -match '^[0-9]+\.[0-9]+\.[0-9]+(-dev\.[0-9]+)?$') {
            $Version = [string]$Manifest.version
        }
    } catch {}
}

function Convert-SafeRecord($InputRecord, [string]$Source) {
    if ($null -eq $InputRecord -or $InputRecord.schema_version -ne 1) { return $null }
    try { $At = [DateTimeOffset]::Parse([string]$InputRecord.time).ToUniversalTime() } catch { return $null }
    if ($At -lt $Cutoff -or $At -gt $Now.AddMinutes(10)) { return $null }
    if ($Source -eq 'bootstrap') {
        if ($InputRecord.module -ne 'bootstrap' -or $InputRecord.stage -cnotin $BootStages -or
            $InputRecord.code -cnotin $BootCodes) { return $null }
        return [ordered]@{
            time = $At.ToString('o'); source = 'bootstrap'; module = 'bootstrap'
            stage = [string]$InputRecord.stage; type = 'BootstrapError'
            code = [string]$InputRecord.code
            message = ('BootstrapError (' + $InputRecord.code + '): details omitted')
        }
    }
    if ($InputRecord.module -cnotin $AllowedModules -or $InputRecord.stage -cnotin $AllowedStages) { return $null }
    $Kind = if ([string]$InputRecord.type -cmatch '^[A-Za-z_][A-Za-z0-9_]{0,63}$') {
        [string]$InputRecord.type
    } else { 'Error' }
    $Code = if ($InputRecord.code -cin $AllowedCodes) { [string]$InputRecord.code } else { $null }
    $Frames = New-Object 'System.Collections.Generic.List[string]'
    foreach ($Line in ([string]$InputRecord.stack -split '\r?\n')) {
        if ($Frames.Count -ge 64) { break }
        if ($Line -cmatch '^[A-Za-z_][A-Za-z0-9_]{0,63}: original details omitted$' -or
            $Line -cmatch '^  File "[A-Za-z_][A-Za-z0-9_.-]{0,79}(\.py)?", line [0-9]{1,8}, in [A-Za-z_<>][A-Za-z0-9_.<>-]{0,95}$' -or
            $Line -cmatch '^    at ([A-Za-z_][A-Za-z0-9_.-]{0,79}|<runtime>):[0-9]{1,8}:[0-9]{1,8}$') {
            $Frames.Add($Line)
        }
    }
    $Item = [ordered]@{
        time = $At.ToString('o'); source = 'runtime'; module = [string]$InputRecord.module
        stage = [string]$InputRecord.stage; type = $Kind; code = $Code
        message = ($Kind + $(if ($Code) { ' (' + $Code + ')' } else { '' }) + ': original details omitted')
        stack = ($Frames -join [char]10)
    }
    if ($InputRecord.platform -cin @('jd','tmall','dmp','databank','yuntu','strategy_center','lingxi')) {
        $Item.platform = [string]$InputRecord.platform
    }
    if ([string]$InputRecord.task_id -cmatch '^[a-f0-9]{32}$') {
        $Item.task_id = [string]$InputRecord.task_id
    }
    if ($null -ne $InputRecord.status -and [string]$InputRecord.status -match '^[0-9]{3}$' -and
        [int]$InputRecord.status -ge 100 -and [int]$InputRecord.status -le 599) {
        $Item.status = [int]$InputRecord.status
    }
    return $Item
}

$Entries = New-Object 'System.Collections.Generic.List[object]'
$Sources = [ordered]@{}
foreach ($Source in @(
    @{ label='runtime'; path=(Join-Path $DataRoot 'logs\diagnostics.jsonl') },
    @{ label='bootstrap'; path=(Join-Path $BootRoot 'bootstrap.jsonl') }
)) {
    $Name = $Source.label
    if (-not (Test-Path -LiteralPath $Source.path -PathType Leaf)) {
        $Sources[$Name] = [ordered]@{ status='missing'; truncated=$false }
        continue
    }
    $Skipped = 0
    $Truncated = $false
    try {
        $Info = Get-Item -LiteralPath $Source.path
        # Tail 5000 avoids reading unbounded append-only source logs.
        $Lines = @(Get-Content -LiteralPath $Source.path -Encoding UTF8 -Tail 5000 -ErrorAction Stop)
        $Truncated = $Info.Length -gt 2400000 -or $Lines.Count -ge 5000
        $UsedBytes = 0
        for ($i = $Lines.Count - 1; $i -ge 0; $i--) {
            $UsedBytes += [Text.Encoding]::UTF8.GetByteCount([string]$Lines[$i]) + 1
            if ($UsedBytes -gt 2400000) {
                $Lines = if ($i -eq $Lines.Count - 1) { @() } else { @($Lines[($i + 1)..($Lines.Count - 1)]) }
                $Truncated = $true
                break
            }
        }
        foreach ($Line in $Lines) {
            if ([string]::IsNullOrWhiteSpace($Line)) { continue }
            try {
                $Record = $Line | ConvertFrom-Json -ErrorAction Stop
                $Safe = Convert-SafeRecord $Record $Name
                if ($null -ne $Safe) { $Entries.Add($Safe) } else { $Skipped++ }
            } catch { $Skipped++ }
        }
        $Sources[$Name] = [ordered]@{ status='ok'; truncated=$Truncated; omitted=$Skipped }
    } catch {
        $Sources[$Name] = [ordered]@{ status='unreadable'; truncated=$false }
    }
}
$Sorted = @($Entries | Sort-Object { $_.time })
$Result = [ordered]@{
    schema_version = 1; project = $Project; version = $Version; platform = 'windows-x64'
    exported_at = $Now.ToString('o'); window_hours = $Hours
    sources = $Sources; entries = $Sorted; truncated = $false
}
$Text = ConvertTo-Json -InputObject $Result -Depth 8
while ([Text.Encoding]::UTF8.GetByteCount($Text) -gt 5000000 -and $Result.entries.Count -gt 0) {
    $Result.entries = @($Result.entries | Select-Object -Skip 1)
    $Result.truncated = $true
    $Text = ConvertTo-Json -InputObject $Result -Depth 8
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path (Get-Location).Path ($Project + '-diagnostics-' + $Now.ToString('yyyyMMddTHHmmssZ') + '.json')
}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output), $Text + [char]10, (New-Object Text.UTF8Encoding($false)))
Write-Output ([IO.Path]::GetFullPath($Output))
