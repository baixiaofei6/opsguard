<#!
OpsGuard C3 - 安全执行器 (P0)
流水线(顺序不可跳): AST判定 -> dry-run预演(预演非沙箱) -> diff -> 备份 -> 确认提示(y/N 默认N)
                  -> 人工显式确认 -> 仅在隔离夹具白名单执行 -> 哈希 -> 回滚/冻结 -> 审计.
代码层面无旁路: 修改类执行只在 Invoke-OG3Change 内, 且必须先由 Confirm-OG3Gate 返回 ok=$true;
冻结标志 / AST deny / 确认非 y / SkipConfirm 一律 return 前退出, 不存在跳过确认开关.
修改目标仅限隔离夹具白名单: HKCU:\Software\OpsGuardTest 键 + c3/fixtures 文件, 由 backup_restore 白名单强制.
#>

$script:OG3_C2Dir = Join-Path (Split-Path -Parent $PSScriptRoot) 'c2'

function Import-OG3Deps {
    <# .SYNOPSIS 导入 C2 复用模块 + C3 本地模块(幂等, -Global 保证调用方作用域可见). #>
    [CmdletBinding()] param()
    Import-Module (Join-Path $script:OG3_C2Dir 'AstGuard.psm1') -Force -Global
    Import-Module (Join-Path $script:OG3_C2Dir 'Policy.psm1') -Force -Global
    Import-Module (Join-Path $PSScriptRoot 'backup_restore.psm1') -Force -Global
    Import-Module (Join-Path $PSScriptRoot 'verify_hash.psm1') -Force -Global
    Import-Module (Join-Path $PSScriptRoot 'audit.psm1') -Force -Global
    Import-Module (Join-Path $PSScriptRoot 'freeze.psm1') -Force -Global
    return $true
}

function Invoke-OG3DryRun {
    <#
    .SYNOPSIS
      dry-run 预演: 只读计算 before/expected diff, 不写任何目标, 不生成备份/清单, 零落盘副作用.
      诚实标注: 这是预演(非沙箱), 只展示预期变化, 不代表隔离沙箱执行.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateSet('registry','file')][string]$Kind,
        [Parameter(Mandatory=$true)][string]$Target,
        [hashtable]$Values
    )
    Import-OG3Deps | Out-Null
    Assert-OG3NotFrozen
    $before = Get-OG3TargetSnapshot -Kind $Kind -Target $Target
    $beforeHash = Get-OG3TargetHash -Kind $Kind -Target $Target
    $lines = @()
    if ($Kind -eq 'registry') {
        foreach ($k in ($Values.Keys | Sort-Object)) {
            $old = if ($before.exists -and $before.content.ContainsKey($k)) { $before.content[$k] } else { '<unset>' }
            $lines += ('-' + $k + ': ' + $old)
            $lines += ('+' + $k + ': ' + $Values[$k])
        }
        $plain = '将把夹具键 ' + $Target + ' 的 ' + (($Values.Keys | Sort-Object) -join ',') + ' 改为预期值(仅预演, 未落盘)'
    } else {
        $oldText = if ($before.exists) { [System.Text.Encoding]::UTF8.GetString($before.content) } else { '<missing>' }
        $lines += ('-' + $oldText)
        $lines += ('+' + [string]$Values['content'])
        $plain = '将把夹具文件 ' + $Target + ' 改为预期内容(仅预演, 未落盘)'
    }
    return [pscustomobject]@{
        dry_run=$true; is_sandbox=$false; note='预演(非沙箱): 只展示预期 diff, 无任何落盘副作用'
        before_hash=$beforeHash; diff=($lines -join [Environment]::NewLine); plain=$plain
    }
}

function Confirm-OG3Gate {
    <#
    .SYNOPSIS
      确认门: y/N 默认 N; ConfirmAnswer='y'/'yes' 且 ConfirmSource='explicit' 才返回 ok=$true.
      冻结 / AST deny / 非 require_confirm / 非显式来源 一律 false(fail-closed).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]$GuardResult,
        [string]$ConfirmAnswer,
        [string]$ConfirmSource = 'explicit'
    )
    Import-OG3Deps | Out-Null
    Assert-OG3NotFrozen
    if ($GuardResult.verdict -ne 'require_confirm') {
        return [pscustomobject]@{ ok=$false; decision='deny'; reason='仅 require_confirm 命令可进入确认门' }
    }
    $policy = Get-OGPolicyDecision -GuardResult $GuardResult -ConfirmAnswer $ConfirmAnswer
    if ($policy.decision -eq 'confirmed' -and $ConfirmSource -eq 'explicit') {
        return [pscustomobject]@{ ok=$true; decision='confirmed'; reason='人工显式确认 y; 默认 N, 无跳过/超时' }
    }
    return [pscustomobject]@{ ok=$false; decision='confirm_required'; reason='未确认(N/空/非显式来源), 不进入执行' }
}

function Invoke-OG3Change {
    <#
    .SYNOPSIS
      修改类命令唯一执行入口(仅隔离夹具). 强制: 冻结检查 -> AST -> 确认门 -> 备份 -> 执行 -> 哈希.
      不存在不经确认的执行路径: ConfirmAnswer 未显式传 y 时 Confirm-OG3Gate 返回 false, 直接 return.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Command,
        [Parameter(Mandatory=$true)][ValidateSet('registry','file')][string]$Kind,
        [Parameter(Mandatory=$true)][string]$Target,
        [Parameter(Mandatory=$true)][hashtable]$Values,
        [string]$ConfirmAnswer,
        [switch]$SkipConfirm,
        [string]$Label
    )
    Import-OG3Deps | Out-Null
    Assert-OG3NotFrozen
    if ($SkipConfirm) {
        Add-OG3Audit -InputSummary $Command -AstVerdict 'n/a' -ConfirmResult 'skip_attempt_rejected' -ExecutionResult 'none' -BackupPath '' -RollbackRecord '' | Out-Null
        return [pscustomobject]@{ ok=$false; stage='confirm'; reason='禁止跳过确认: SkipConfirm 不产生旁路, 默认 N' }
    }
    $guard = Assert-OGCommand -Command $Command
    if ($guard.verdict -eq 'deny') {
        Add-OG3Audit -InputSummary $Command -AstVerdict 'deny' -AstReason $guard.reason -ConfirmResult 'not_reached' -ExecutionResult 'blocked' -BackupPath '' -RollbackRecord '' | Out-Null
        return [pscustomobject]@{ ok=$false; stage='ast'; reason=$guard.reason; guard=$guard }
    }
    if ($guard.verdict -ne 'require_confirm') {
        Add-OG3Audit -InputSummary $Command -AstVerdict $guard.verdict -AstReason $guard.reason -ConfirmResult 'not_required' -ExecutionResult 'blocked' -BackupPath '' -RollbackRecord '' | Out-Null
        return [pscustomobject]@{ ok=$false; stage='ast'; reason='非 require_confirm 修改命令不进入执行路径' }
    }
    $dry = Invoke-OG3DryRun -Kind $Kind -Target $Target -Values $Values
    $gate = Confirm-OG3Gate -GuardResult $guard -ConfirmAnswer $ConfirmAnswer
    if (-not $gate.ok) {
        Add-OG3Audit -InputSummary $Command -AstVerdict $guard.verdict -AstReason $guard.reason -ConfirmResult $gate.decision -ExecutionResult 'not_executed' -BackupPath '' -RollbackRecord '' | Out-Null
        return [pscustomobject]@{ ok=$false; stage='confirm'; reason=$gate.reason; dry=$dry }
    }
    # 确认后才备份+执行: 确认前无备份/清单落盘.
    $beforeHash = Get-OG3TargetHash -Kind $Kind -Target $Target
    $backup = Backup-OG3Target -Kind $Kind -Target $Target -Label $Label
    $manifest = Save-OG3Manifest -Entries @($backup) -Command $Command -Verdict $guard.verdict
    $manifest | Add-Member -NotePropertyName before_hash -NotePropertyValue $beforeHash -Force
    $manifest | Add-Member -NotePropertyName after_hash -NotePropertyValue $null -Force
    Set-OG3TargetValue -Kind $Kind -Target $Target -Values $Values
    $afterHash = Get-OG3TargetHash -Kind $Kind -Target $Target
    $manifest.after_hash = $afterHash
    $result = [pscustomobject]@{
        ok=$true; stage='executed'; guard=$guard; dry=$dry; manifest=$manifest
        before_hash=$beforeHash; after_hash=$afterHash
    }
    Add-OG3Audit -InputSummary $Command -AstVerdict $guard.verdict -AstReason $guard.reason -ConfirmResult 'confirmed' -ExecutionResult 'executed' -BackupPath $manifest.manifest_path -RollbackRecord '' | Out-Null
    return $result
}

function Invoke-OG3Rollback {
    <#
    .SYNOPSIS
      按 manifest 回滚 + 三方哈希验证; 失败即冻结(保留备份)并输出手工步骤.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)]$Manifest)
    Import-OG3Deps | Out-Null
    Assert-OG3NotFrozen
    $restoreFail = $null
    foreach ($entry in $Manifest.affected_items) {
        try { Restore-OG3Target -Entry $entry | Out-Null }
        catch { $restoreFail = $_.Exception.Message; break }
    }
    $first = $Manifest.affected_items[0]
    $restoredHash = Get-OG3TargetHash -Kind $first.kind -Target $first.target
    $verify = $null
    if ($Manifest.PSObject.Properties.Name -contains 'before_hash' -and $Manifest.before_hash) {
        $verify = Test-OG3RoundTrip -BeforeHash $Manifest.before_hash -AfterHash $Manifest.after_hash -RestoredHash $restoredHash
    }
    if ($restoreFail -or ($null -ne $verify -and -not $verify.ok)) {
        $reason = if ($restoreFail) { $restoreFail } else { $verify.reason }
        $guide = Set-OG3Freeze -Reason $reason -ManifestEntries $Manifest.affected_items -ManifestPath $Manifest.manifest_path
        Add-OG3Audit -InputSummary ('rollback:' + $Manifest.command) -AstVerdict 'n/a' -ConfirmResult 'n/a' -ExecutionResult 'rollback_failed' -BackupPath $Manifest.manifest_path -RollbackRecord $reason | Out-Null
        return [pscustomobject]@{ ok=$false; stage='rollback'; frozen=$true; reason=$reason; guide=$guide }
    }
    Add-OG3Audit -InputSummary ('rollback:' + $Manifest.command) -AstVerdict 'n/a' -ConfirmResult 'n/a' -ExecutionResult 'rollback_ok' -BackupPath $Manifest.manifest_path -RollbackRecord $verify.reason | Out-Null
    return [pscustomobject]@{ ok=$true; stage='rollback'; frozen=$false; verify=$verify; restored_hash=$restoredHash }
}

Export-ModuleMember -Function Import-OG3Deps,Invoke-OG3DryRun,Confirm-OG3Gate,Invoke-OG3Change,Invoke-OG3Rollback
