<#!
OpsGuard C3 · 三方哈希校验 (P0)
判定式写死: 回滚后哈希 = 操作前哈希 且 操作后哈希 ≠ 操作前哈希; 否则 = 回滚失败.
#>

function Test-OG3RoundTrip {
    <#
    .SYNOPSIS
      给定三组 SHA256 (before/after/restored), 按判定式返回验证对象; 不改任何目标.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$BeforeHash,
        [Parameter(Mandatory=$true)][string]$AfterHash,
        [Parameter(Mandatory=$true)][string]$RestoredHash
    )
    $restoredEqualsBefore = [string]::Equals($BeforeHash, $RestoredHash, [System.StringComparison]::OrdinalIgnoreCase)
    $afterDiffersFromBefore = -not [string]::Equals($BeforeHash, $AfterHash, [System.StringComparison]::OrdinalIgnoreCase)
    $ok = $restoredEqualsBefore -and $afterDiffersFromBefore
    return [pscustomobject]@{
        ok=$ok
        verdict=$(if ($ok) { 'rollback_verified' } else { 'rollback_failed' })
        formula='rollback_after_hash = before_hash AND after_hash != before_hash'
        before=$BeforeHash; after=$AfterHash; restored=$RestoredHash
        reason=$(if ($ok) { '回滚后=操作前 且 操作后≠操作前, 还原已验证' } else { '哈希判定式不成立, 回滚失败, 触发冻结' })
    }
}

Export-ModuleMember -Function Test-OG3RoundTrip
