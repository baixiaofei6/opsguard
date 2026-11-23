<#!
OpsGuard C3 - 隔离夹具备份与回滚 (P0)
仅操作白名单夹具: HKCU:\Software\OpsGuardTest\... 注册表键 + c3/fixtures/ 下临时文件.
绝不触碰真实网卡/DNS/系统服务/系统目录. 生成 JSON manifest (时间戳/受影响项/备份文件/回滚命令).
#>

$script:OG3_C3Root = $PSScriptRoot
$script:OG3_FixtureRoot = Join-Path $script:OG3_C3Root 'fixtures'
$script:OG3_RegRoot = 'HKCU:\Software\OpsGuardTest'

function Test-OG3PathAllowed {
    param([Parameter(Mandatory=$true)][string]$Path)
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
        $root = [System.IO.Path]::GetFullPath($script:OG3_FixtureRoot)
        if ($full -eq $root) { return $false }
        if (-not $full.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
        $rel = $full.Substring($root.Length + 1)
        $segments = $rel -split '[\\/]'
        if ($segments -contains '..') { return $false }
        return $true
    } catch { return $false }
}

function Test-OG3RegAllowed {
    param([Parameter(Mandatory=$true)][string]$Key)
    $norm = $Key -replace '/', '\'
    if ($norm -eq $script:OG3_RegRoot) { return $false }
    if (-not $norm.StartsWith($script:OG3_RegRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
    $segments = $norm -split '\\'
    if ($segments -contains '..') { return $false }
    if ($norm -match '[*?"<>|]') { return $false }
    return $true
}

function New-OG3BackupPath {
    param([Parameter(Mandatory=$true)][ValidateSet('registry','file')][string]$Kind,[string]$Label)
    if (-not (Test-Path -LiteralPath $script:OG3_FixtureRoot)) { New-Item -ItemType Directory -Path $script:OG3_FixtureRoot -Force | Out-Null }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $tag = if ([string]::IsNullOrWhiteSpace($Label)) { 'item' } else { ($Label -replace '[^A-Za-z0-9_-]', '_') }
    $ext = if ($Kind -eq 'registry') { '.reg' } else { '.bak' }
    return (Join-Path $script:OG3_FixtureRoot ($stamp + '_' + $tag + $ext))
}

function Get-OG3TargetSnapshot {
    param([Parameter(Mandatory=$true)][ValidateSet('registry','file')][string]$Kind,[Parameter(Mandatory=$true)][string]$Target)
    if ($Kind -eq 'file') {
        if (-not (Test-OG3PathAllowed -Path $Target)) { throw '文件目标不在 c3/fixtures 白名单内 (fail-closed)' }
    } else {
        if (-not (Test-OG3RegAllowed -Key $Target)) { throw '注册表目标不在 HKCU:\Software\OpsGuardTest 白名单内 (fail-closed)' }
    }
    $exists = Test-Path -LiteralPath $Target
    $content = $null
    if ($exists) {
        if ($Kind -eq 'file') { $content = [System.IO.File]::ReadAllBytes($Target) }
        else {
            $props = (Get-ItemProperty -LiteralPath $Target).PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' }
            $content = @{}
            foreach ($p in $props) { $content[$p.Name] = [string]$p.Value }
        }
    }
    return [pscustomobject]@{ kind=$Kind; target=$Target; exists=$exists; content=$content }
}

function Set-OG3TargetValue {
    param([Parameter(Mandatory=$true)][ValidateSet('registry','file')][string]$Kind,[Parameter(Mandatory=$true)][string]$Target,[hashtable]$Values)
    if ($Kind -eq 'file') {
        if (-not (Test-OG3PathAllowed -Path $Target)) { throw '文件目标不在 c3/fixtures 白名单内 (fail-closed)' }
        $dir = Split-Path -Parent $Target
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$Values['content'])
        [System.IO.File]::WriteAllBytes($Target, $bytes)
    } else {
        if (-not (Test-OG3RegAllowed -Key $Target)) { throw '注册表目标不在 HKCU:\Software\OpsGuardTest 白名单内 (fail-closed)' }
        if (-not (Test-Path -LiteralPath $Target)) { New-Item -Path $Target -Force | Out-Null }
        foreach ($k in $Values.Keys) { New-ItemProperty -Path $Target -Name $k -Value $Values[$k] -PropertyType String -Force | Out-Null }
    }
}

function Backup-OG3Target {
    <#
    .SYNOPSIS
      备份一个隔离夹具目标; 返回 manifest entry (kind/target/exists/backup_path/restore_command/snapshot).
      注册表用 reg export 生成 .reg; 文件用字节副本 .bak; 不存在则记 exists=false 不生成备份文件.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateSet('registry','file')][string]$Kind,
        [Parameter(Mandatory=$true)][string]$Target,
        [string]$Label
    )
    $snap = Get-OG3TargetSnapshot -Kind $Kind -Target $Target
    $backupPath = $null
    $restoreCmd = $null
    if ($Kind -eq 'registry') {
        $regPath = $Target -replace '/', '\'
        if ($snap.exists) {
            $backupPath = New-OG3BackupPath -Kind registry -Label $Label
            $hivePath = 'HKEY_CURRENT_USER' + $regPath.Substring(5)
            $oldEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try { & reg export $hivePath $backupPath /y 2>&1 | Out-Null; $code = $LASTEXITCODE }
            finally { $ErrorActionPreference = $oldEap }
            if ($code -ne 0) { throw ('reg export 失败 (exit=' + $code + ')') }
            $restoreCmd = 'reg import "' + $backupPath + '"'
        } else {
            $restoreCmd = 'Remove-Item -LiteralPath "' + $regPath + '" -Recurse -Force'
        }
    } else {
        if ($snap.exists) {
            $backupPath = New-OG3BackupPath -Kind file -Label $Label
            [System.IO.File]::WriteAllBytes($backupPath, $snap.content)
            $restoreCmd = '[System.IO.File]::WriteAllBytes("' + $Target + '", [System.IO.File]::ReadAllBytes("' + $backupPath + '"))'
        } else {
            $restoreCmd = 'Remove-Item -LiteralPath "' + $Target + '" -Force'
        }
    }
    return [pscustomobject]@{
        kind=$Kind; target=$Target; exists=$snap.exists; backup_path=$backupPath
        restore_command=$restoreCmd; snapshot=$snap.content
    }
}

function Save-OG3Manifest {
    <#
    .SYNOPSIS
      把若干 backup entry 写成 JSON manifest (时间戳/受影响项/备份文件/回滚命令), 放 c3/fixtures.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][object[]]$Entries,[string]$Command,[string]$Verdict)
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $path = Join-Path $script:OG3_FixtureRoot ('manifest_' + $stamp + '.json')
    if (-not (Test-Path -LiteralPath $script:OG3_FixtureRoot)) { New-Item -ItemType Directory -Path $script:OG3_FixtureRoot -Force | Out-Null }
    $entryData = @()
    foreach ($e in $Entries) {
        $entryData += [pscustomobject]@{
            kind=$e.kind; target=$e.target; exists=$e.exists
            backup_path=$e.backup_path; restore_command=$e.restore_command
        }
    }
    $manifest = [pscustomobject]@{
        timestamp_utc=$stamp; command=$Command; ast_verdict=$Verdict
        affected_items=$entryData; manifest_path=$path
    }
    $json = $manifest | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($path, $json, (New-Object System.Text.UTF8Encoding($false)))
    return $manifest
}

function Restore-OG3Target {
    <#
    .SYNOPSIS
      按 manifest entry 逆操作还原隔离夹具目标; 注册表 reg import, 文件字节写回; 不存在则删除.
      仅恢复白名单目标; 任一越界直接 throw(fail-closed), 不触碰真实系统.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)]$Entry)
    $kind = [string]$Entry.kind
    $target = [string]$Entry.target
    if ($kind -eq 'registry') {
        if (-not (Test-OG3RegAllowed -Key $target)) { throw '回滚目标注册表键越界(fail-closed)' }
        if ([bool]$Entry.exists) {
            if (-not $Entry.backup_path -or -not (Test-Path -LiteralPath $Entry.backup_path)) { throw '注册表备份文件缺失' }
            $oldEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try { & reg import $Entry.backup_path 2>&1 | Out-Null; $code = $LASTEXITCODE }
            finally { $ErrorActionPreference = $oldEap }
            if ($code -ne 0) { throw ('reg import 失败 (exit=' + $code + ')') }
        } else {
            Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
        }
    } elseif ($kind -eq 'file') {
        if (-not (Test-OG3PathAllowed -Path $target)) { throw '回滚目标文件越界(fail-closed)' }
        if ([bool]$Entry.exists) {
            if (-not $Entry.backup_path -or -not (Test-Path -LiteralPath $Entry.backup_path)) { throw '文件备份缺失' }
            [System.IO.File]::WriteAllBytes($target, [System.IO.File]::ReadAllBytes($Entry.backup_path))
        } else {
            Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
        }
    } else {
        throw '未知夹具类型(fail-closed)'
    }
    return $true
}

function Get-OG3TargetHash {
    <#
    .SYNOPSIS
      目标快照 SHA256; 注册表按稳定排序的 名称=值 文本, 文件按原始字节. 不存在返回 missing 标记.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][ValidateSet('registry','file')][string]$Kind,[Parameter(Mandatory=$true)][string]$Target)
    $snap = Get-OG3TargetSnapshot -Kind $Kind -Target $Target
    if (-not $snap.exists) { return '<missing>' }
    if ($Kind -eq 'file') {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { $h = $sha.ComputeHash($snap.content) } finally { $sha.Dispose() }
        return ([System.BitConverter]::ToString($h) -replace '-', '').ToLowerInvariant()
    }
    $pairs = @()
    foreach ($k in ($snap.content.Keys | Sort-Object)) { $pairs += ($k + '=' + $snap.content[$k]) }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($pairs -join [Environment]::NewLine))
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $h = $sha.ComputeHash($bytes) } finally { $sha.Dispose() }
    return ([System.BitConverter]::ToString($h) -replace '-', '').ToLowerInvariant()
}

Export-ModuleMember -Function Test-OG3PathAllowed,Test-OG3RegAllowed,New-OG3BackupPath,Get-OG3TargetSnapshot,Set-OG3TargetValue,Backup-OG3Target,Save-OG3Manifest,Restore-OG3Target,Get-OG3TargetHash
