<#!
OpsGuard C2 - 权限分级 + 确认门(模拟) PowerShell 栈.
消费 AST 三态: allow_readonly -> allow; require_confirm -> confirm_required(y/N 默认N);
deny -> deny(硬拒, 确认门不得覆盖). C2 确认门只展示方案, 不执行任何命令.
#>

function Get-OGPolicyDecision {
    <#
    .SYNOPSIS
      根据 AST 三态判定返回权限决策; 不执行任何命令.
    .PARAMETER GuardResult
      Assert-OGCommand 返回的对象(含 verdict/reason).
    .PARAMETER ConfirmAnswer
      模拟确认答案; 仅 require_confirm 时生效, 严格 y/yes 才算确认, 其余默认 N.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]$GuardResult,
        [string]$ConfirmAnswer
    )
    $verdict = $GuardResult.verdict
    $reason = [string]$GuardResult.reason

    if ($verdict -eq 'deny') {
        return [pscustomobject]@{ decision='deny'; reason=('AST 判定 deny, 硬拒: ' + $reason); ast_verdict=$verdict; executed=$false }
    }
    if ($verdict -eq 'allow_readonly') {
        return [pscustomobject]@{ decision='allow'; reason=('白名单只读, 放行展示(C2 不执行): ' + $reason); ast_verdict=$verdict; executed=$false }
    }
    if ($verdict -eq 'require_confirm') {
        $ans = if ($null -eq $ConfirmAnswer) { '' } else { $ConfirmAnswer.Trim().ToLowerInvariant() }
        if ($ans -eq 'y' -or $ans -eq 'yes') {
            return [pscustomobject]@{ decision='confirmed'; reason='模拟确认 = y; 仅授权展示, 执行留待 C3'; ast_verdict=$verdict; executed=$false }
        }
        return [pscustomobject]@{ decision='confirm_required'; reason='需人工确认, 默认 N; 未确认不进入执行(无跳过/无超时自动执行)'; ast_verdict=$verdict; executed=$false }
    }
    return [pscustomobject]@{ decision='deny'; reason='未知 AST 三态, fail-closed 硬拒'; ast_verdict=$verdict; executed=$false }
}

Export-ModuleMember -Function Get-OGPolicyDecision
