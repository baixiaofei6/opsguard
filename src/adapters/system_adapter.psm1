<#!
OpsGuard official - parameterized system adapter (PowerShell 5.1, ASCII-only on purpose).
Production mode: can really change DNS / service / registry / file targets.
Sandbox mode (-Sandbox): redirects every target to fixtures (HKCU:\Software\OpsGuardTest
  + a temp file root), so build/test never touches the real system.
Pipeline: snapshot -> hash -> AST -> dry-run -> confirm(y/N default N) -> backup
  -> set -> after hash; rollback is a separate function with 3-way hash verify.
No bypass: SkipConfirm is always rejected; AST deny blocks; frozen state blocks.
ASCII-only so BOM-less PS5.1 parsing is safe; all Chinese UI lives in the Python CLI.
#>

$script:OG_TEST_REG_ROOT = 'HKCU:\Software\OpsGuardTest'
$script:OG_FREEZE_FLAG = $null

function Get-OGRootDir {
    return (Split-Path -Parent $PSScriptRoot)
}

function New-OGSandboxFileRoot {
    param([string]$Root)
    if ($Root) { $r = $Root }
    else { $r = Join-Path (Get-OGRootDir) 'sandbox' }
    if (-not (Test-Path -LiteralPath $r)) { New-Item -ItemType Directory -Path $r -Force | Out-Null }
    return $r
}

function Resolve-OGTarget {
    <#! Maps a (Kind, Target) to a concrete (actualKind, actualTarget) based on Sandbox.
         dns/service in sandbox are simulated via a registry key under the fixture root. #>
    param(
        [Parameter(Mandatory=$true)][ValidateSet('dns','service','registry','file')][string]$Kind,
        [Parameter(Mandatory=$true)][string]$Target,
        [switch]$Sandbox,
        [string]$SandboxRoot
    )
    if (-not $Sandbox) {
        $ak = if ($Kind -eq 'dns' -or $Kind -eq 'service') { 'registry' } else { $Kind }
        # dns  -> HKLM system interface key (read); service -> HKLM service key
        if ($Kind -eq 'dns') { $at = $Target }          # caller passes full registry-ish target for production
        elseif ($Kind -eq 'service') { $at = $Target }
        else { $at = $Target }
        return [pscustomobject]@{ actual_kind=$ak; actual_target=$at; simulated=$false; original_kind=$Kind; original_target=$Target }
    }
    $tag = ($Kind + '_' + ($Target -replace '[^A-Za-z0-9_-]','_'))
    if ($tag.Length -gt 90) { $tag = $tag.Substring(0,90) }
    if ($Kind -eq 'file') {
        $root = New-OGSandboxFileRoot -Root $SandboxRoot
        $leaf = Split-Path -Leaf $Target
        $at = Join-Path $root ('SANDBOX_' + $leaf)
        return [pscustomobject]@{ actual_kind='file'; actual_target=$at; simulated=$true; original_kind=$Kind; original_target=$Target }
    }
    $at = $script:OG_TEST_REG_ROOT + '\' + $tag
    return [pscustomobject]@{ actual_kind='registry'; actual_target=$at; simulated=$true; original_kind=$Kind; original_target=$Target }
}

function Test-OGPathAllowed {
    param([Parameter(Mandatory=$true)][string]$Path,[string]$Root)
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
        $r = [System.IO.Path]::GetFullPath($Root)
        if (-not $full.StartsWith($r + [System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) { return $false }
        return $true
    } catch { return $false }
}

function Test-OGRegAllowed {
    param([Parameter(Mandatory=$true)][string]$Key,[switch]$Sandbox)
    $norm = $Key -replace '/','\'
    if ($Sandbox) {
        if (-not $norm.StartsWith($script:OG_TEST_REG_ROOT + '\',[System.StringComparison]::OrdinalIgnoreCase)) { return $false }
    } else {
        $allowed = 'HKCU:\','HKLM:\SYSTEM\CurrentControlSet\Services\','HKLM:\SYSTEM\CurrentControlSet\Control\Network\'
        $ok = $false
        foreach ($a in $allowed) { if ($norm.StartsWith($a,[System.StringComparison]::OrdinalIgnoreCase)) { $ok = $true; break } }
        if (-not $ok) { return $false }
    }
    if ($norm -match '[*?"<>|]') { return $false }
    if (($norm -split '\\') -contains '..') { return $false }
    return $true
}

function Get-OGSnapshot {
    param([Parameter(Mandatory=$true)][string]$Kind,[Parameter(Mandatory=$true)][string]$Target,[switch]$Sandbox,[string]$SandboxRoot)
    $mapped = Resolve-OGTarget -Kind $Kind -Target $Target -Sandbox:$Sandbox -SandboxRoot $SandboxRoot
    $ak = [string]$mapped.actual_kind
    $at = [string]$mapped.actual_target
    if ($ak -eq 'file') {
        if ($Sandbox) {
            $root = New-OGSandboxFileRoot -Root $SandboxRoot
            if (-not (Test-OGPathAllowed -Path $at -Root $root)) { throw 'file target outside sandbox root (fail-closed)' }
        }
        $exists = Test-Path -LiteralPath $at
        $content = $null
        if ($exists) { $content = [System.IO.File]::ReadAllBytes($at) }
    } else {
        if (-not (Test-OGRegAllowed -Key $at -Sandbox:$Sandbox)) { throw 'registry target not allowed (fail-closed)' }
        $exists = Test-Path -LiteralPath $at
        $content = @{}
        if ($exists) {
            $props = (Get-ItemProperty -LiteralPath $at).PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' }
            foreach ($p in $props) { $content[[string]$p.Name] = [string]$p.Value }
        }
    }
    return [pscustomobject]@{ kind=$ak; target=$at; exists=$exists; content=$content; mapping=$mapped }
}

function Get-OGHash {
    param([Parameter(Mandatory=$true)]$Snap)
    if (-not $Snap.exists) { return '<missing>' }
    $bytes = $null
    if ($Snap.kind -eq 'file') {
        $bytes = $Snap.content
    } else {
        $pairs = @()
        foreach ($k in ($Snap.content.Keys | Sort-Object)) { $pairs += ($k + '=' + $Snap.content[$k]) }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes(($pairs -join [Environment]::NewLine))
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $h = $sha.ComputeHash($bytes) } finally { $sha.Dispose() }
    return ([System.BitConverter]::ToString($h) -replace '-','').ToLowerInvariant()
}

function Backup-OGTarget {
    param([Parameter(Mandatory=$true)]$Snap,[string]$Label)
    $backupRoot = Join-Path (Get-OGRootDir) 'backups'
    if (-not (Test-Path -LiteralPath $backupRoot)) { New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $tag = if ($Label) { ($Label -replace '[^A-Za-z0-9_-]','_') } else { 'item' }
    $backupPath = $null
    $restoreCmd = $null
    if ($Snap.kind -eq 'file') {
        if ($Snap.exists) {
            $backupPath = Join-Path $backupRoot ($stamp + '_' + $tag + '.bak')
            [System.IO.File]::WriteAllBytes($backupPath, $Snap.content)
            $restoreCmd = 'FILE_RESTORE_FROM:' + $backupPath
        } else { $restoreCmd = 'FILE_REMOVE:' + $Snap.target }
    } else {
        if ($Snap.exists) {
            $backupPath = Join-Path $backupRoot ($stamp + '_' + $tag + '.reg.json')
            $json = $Snap.content | ConvertTo-Json -Depth 6 -Compress
            [System.IO.File]::WriteAllText($backupPath, $json, (New-Object System.Text.UTF8Encoding($false)))
            $restoreCmd = 'REG_RESTORE_FROM:' + $backupPath
        } else { $restoreCmd = 'REG_REMOVE:' + $Snap.target }
    }
    return [pscustomobject]@{
        kind=$Snap.kind; target=$Snap.target; exists=$Snap.exists
        backup_path=$backupPath; restore_command=$restoreCmd
        original_kind=$Snap.mapping.original_kind; original_target=$Snap.mapping.original_target
        simulated=$Snap.mapping.simulated
    }
}

function Set-OGValue {
    param([Parameter(Mandatory=$true)]$Snap,[hashtable]$Values,[switch]$Sandbox,[string]$SandboxRoot)
    if ($Snap.kind -eq 'file') {
        if ($Sandbox) {
            $root = New-OGSandboxFileRoot -Root $SandboxRoot
            if (-not (Test-OGPathAllowed -Path $Snap.target -Root $root)) { throw 'file target outside sandbox (fail-closed)' }
        }
        $dir = Split-Path -Parent $Snap.target
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        [System.IO.File]::WriteAllBytes($Snap.target, [System.Text.Encoding]::UTF8.GetBytes([string]$Values['content']))
    } else {
        if (-not (Test-OGRegAllowed -Key $Snap.target -Sandbox:$Sandbox)) { throw 'registry target not allowed (fail-closed)' }
        if (-not (Test-Path -LiteralPath $Snap.target)) { New-Item -Path $Snap.target -Force | Out-Null }
        foreach ($k in $Values.Keys) { New-ItemProperty -Path $Snap.target -Name $k -Value $Values[$k] -PropertyType String -Force | Out-Null }
    }
    return $true
}

function Restore-OGTarget {
    param([Parameter(Mandatory=$true)]$Entry,[switch]$Sandbox,[string]$SandboxRoot)
    $kind = [string]$Entry.kind
    $target = [string]$Entry.target
    if ($kind -eq 'file') {
        if ($Sandbox) {
            $root = New-OGSandboxFileRoot -Root $SandboxRoot
            if (-not (Test-OGPathAllowed -Path $target -Root $root)) { throw 'file target outside sandbox (fail-closed)' }
        }
        if ([bool]$Entry.exists) {
            if (-not $Entry.backup_path -or -not (Test-Path -LiteralPath $Entry.backup_path)) { throw 'file backup missing' }
            [System.IO.File]::WriteAllBytes($target, [System.IO.File]::ReadAllBytes($Entry.backup_path))
        } else {
            Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
        }
    } elseif ($kind -eq 'registry') {
        if (-not (Test-OGRegAllowed -Key $target -Sandbox:$Sandbox)) { throw 'registry target not allowed (fail-closed)' }
        if ([bool]$Entry.exists) {
            if (-not $Entry.backup_path -or -not (Test-Path -LiteralPath $Entry.backup_path)) { throw 'registry backup missing' }
            $json = [System.IO.File]::ReadAllText($Entry.backup_path)
            $props = $json | ConvertFrom-Json
            if (-not (Test-Path -LiteralPath $target)) { New-Item -Path $target -Force | Out-Null }
            foreach ($p in $props.PSObject.Properties) { New-ItemProperty -Path $target -Name $p.Name -Value $p.Value -PropertyType String -Force | Out-Null }
        } else {
            Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
        }
    } else { throw 'unknown kind (fail-closed)' }
    return $true
}

function Save-OGManifest {
    param([Parameter(Mandatory=$true)]$Entry,[string]$Command,[string]$BeforeHash,[string]$AfterHash,[string]$AstVerdict)
    $dir = Join-Path (Get-OGRootDir) 'backups'
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $path = Join-Path $dir ('manifest_' + $stamp + '.json')
    $m = [pscustomobject]@{
        id=$stamp; timestamp_utc=$stamp; command=$Command; ast_verdict=$AstVerdict
        before_hash=$BeforeHash; after_hash=$AfterHash
        affected_items=@($Entry); manifest_path=$path
    }
    [System.IO.File]::WriteAllText($path, ($m | ConvertTo-Json -Depth 8), (New-Object System.Text.UTF8Encoding($false)))
    return $m
}

function Test-OGRoundTrip {
    param([string]$BeforeHash,[string]$AfterHash,[string]$RestoredHash)
    $r = [string]::Equals($BeforeHash,$RestoredHash,[System.StringComparison]::OrdinalIgnoreCase)
    $a = -not [string]::Equals($BeforeHash,$AfterHash,[System.StringComparison]::OrdinalIgnoreCase)
    return [pscustomobject]@{ ok=($r -and $a); restored_equals_before=$r; after_differs=$a }
}

function Invoke-OGChange {
    <#! Full guarded change pipeline. ConfirmAnswer must be exactly y/yes; no skip, no timeout. #>
    param(
        [Parameter(Mandatory=$true)][ValidateSet('dns','service','registry','file')][string]$Kind,
        [Parameter(Mandatory=$true)][string]$Target,
        [Parameter(Mandatory=$true)][hashtable]$Values,
        [string]$ConfirmAnswer,
        [switch]$Sandbox,
        [string]$SandboxRoot,
        [string]$Label,
        [string]$AstVerdict = 'require_confirm'
    )
    if ($script:OG_FREEZE_FLAG) { return [pscustomobject]@{ ok=$false; stage='frozen'; reason=$script:OG_FREEZE_FLAG } }
    if ($AstVerdict -ne 'require_confirm') {
        return [pscustomobject]@{ ok=$false; stage='ast'; reason='non require_confirm verdict; blocked' }
    }
    $ans = if ($ConfirmAnswer) { $ConfirmAnswer.Trim().ToLowerInvariant() } else { '' }
    if ($ans -notin @('y','yes')) {
        return [pscustomobject]@{ ok=$false; stage='confirm'; reason='default N; not confirmed' }
    }
    $snap = Get-OGSnapshot -Kind $Kind -Target $Target -Sandbox:$Sandbox -SandboxRoot $SandboxRoot
    $beforeHash = Get-OGHash -Snap $snap
    $diffLines = @()
    if ($snap.kind -eq 'file') {
        $old = if ($snap.exists) { [System.Text.Encoding]::UTF8.GetString($snap.content) } else { '<missing>' }
        $diffLines += ('-' + $old); $diffLines += ('+' + [string]$Values['content'])
    } else {
        foreach ($k in ($Values.Keys | Sort-Object)) {
            $old = if ($snap.exists -and $snap.content.ContainsKey($k)) { $snap.content[$k] } else { '<unset>' }
            $diffLines += ('-' + $k + ': ' + $old); $diffLines += ('+' + $k + ': ' + $Values[$k])
        }
    }
    $entry = Backup-OGTarget -Snap $snap -Label $Label
    Set-OGValue -Snap $snap -Values $Values -Sandbox:$Sandbox -SandboxRoot $SandboxRoot | Out-Null
    $afterSnap = Get-OGSnapshot -Kind $Kind -Target $Target -Sandbox:$Sandbox -SandboxRoot $SandboxRoot
    $afterHash = Get-OGHash -Snap $afterSnap
    $manifest = Save-OGManifest -Entry $entry -Command $Kind -BeforeHash $beforeHash -AfterHash $afterHash -AstVerdict $AstVerdict
    return [pscustomobject]@{
        ok=$true; stage='executed'; diff=($diffLines -join [Environment]::NewLine)
        before_hash=$beforeHash; after_hash=$afterHash; manifest=$manifest
        is_sandbox=[bool]$Sandbox
    }
}

function Invoke-OGRollback {
    param([Parameter(Mandatory=$true)]$Manifest,[switch]$Sandbox,[string]$SandboxRoot)
    if ($script:OG_FREEZE_FLAG) { return [pscustomobject]@{ ok=$false; stage='frozen'; reason=$script:OG_FREEZE_FLAG } }
    $entry = $Manifest.affected_items[0]
    Restore-OGTarget -Entry $entry -Sandbox:$Sandbox -SandboxRoot $SandboxRoot | Out-Null
    $snap = Get-OGSnapshot -Kind $entry.kind -Target $entry.target -Sandbox:$Sandbox -SandboxRoot $SandboxRoot
    $restoredHash = Get-OGHash -Snap $snap
    $v = Test-OGRoundTrip -BeforeHash $Manifest.before_hash -AfterHash $Manifest.after_hash -RestoredHash $restoredHash
    if (-not $v.ok) {
        $script:OG_FREEZE_FLAG = '3-way hash verify failed; manual recovery required; manifest=' + $Manifest.manifest_path
        return [pscustomobject]@{ ok=$false; stage='rollback'; frozen=$true; verify=$v; restored_hash=$restoredHash }
    }
    return [pscustomobject]@{ ok=$true; stage='rollback'; frozen=$false; verify=$v; restored_hash=$restoredHash }
}

function Reset-OGFreeze { $script:OG_FREEZE_FLAG = $null; return $true }

Export-ModuleMember -Function Get-OGRootDir,Resolve-OGTarget,Get-OGSnapshot,Get-OGHash,Backup-OGTarget,Set-OGValue,Restore-OGTarget,Save-OGManifest,Test-OGRoundTrip,Invoke-OGChange,Invoke-OGRollback,Reset-OGFreeze,Test-OGRegAllowed,Test-OGPathAllowed
