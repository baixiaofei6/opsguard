<#!
OpsGuard C3 - append-only 审计日志
日志只在 c3/audit/ 内, 每行 JSON (时间/输入摘要/AST判定/确认结果/执行结果/备份路径/回滚记录).
append-only 不变量: 写入只用 StreamWriter Append; 读取忽略坏行, 不改写历史.
#>

$script:OG3_AuditDir = Join-Path $PSScriptRoot 'audit'
$script:OG3_AuditLog = Join-Path $script:OG3_AuditDir 'audit.jsonl'

function Add-OG3Audit {
    <#
    .SYNOPSIS
      追加一条审计记录 (JSON Lines); 返回写入对象, 含 seq 与时间戳.
    #>
    [CmdletBinding()]
    param(
        [string]$InputSummary,
        [string]$AstVerdict,
        [string]$AstReason,
        [string]$ConfirmResult,
        [string]$ExecutionResult,
        [string]$BackupPath,
        [string]$RollbackRecord
    )
    if (-not (Test-Path -LiteralPath $script:OG3_AuditDir)) { New-Item -ItemType Directory -Path $script:OG3_AuditDir -Force | Out-Null }
    $seq = 1
    if (Test-Path -LiteralPath $script:OG3_AuditLog) {
        $lines = @(Get-Content -LiteralPath $script:OG3_AuditLog)
        foreach ($ln in $lines) {
            if ([string]::IsNullOrWhiteSpace($ln)) { continue }
            try {
                $obj = $ln | ConvertFrom-Json
                if ($null -ne $obj -and $obj.seq -ge $seq) { $seq = [int]$obj.seq + 1 }
            } catch { continue }
        }
    }
    $record = [pscustomobject]@{
        seq=$seq
        timestamp_utc=[DateTime]::UtcNow.ToString('o')
        input_summary=$InputSummary
        ast_verdict=$AstVerdict
        ast_reason=$AstReason
        confirm_result=$ConfirmResult
        execution_result=$ExecutionResult
        backup_path=$BackupPath
        rollback_record=$RollbackRecord
    }
    $line = $record | ConvertTo-Json -Compress -Depth 6
    $sw = New-Object System.IO.StreamWriter($script:OG3_AuditLog, $true, (New-Object System.Text.UTF8Encoding($false)))
    try { $sw.WriteLine($line) } finally { $sw.Dispose() }
    return $record
}

function Get-OG3AuditEntries {
    <# .SYNOPSIS 读取全部审计记录(只读, 跳过坏行). #>
    [CmdletBinding()]
    param()
    if (-not (Test-Path -LiteralPath $script:OG3_AuditLog)) { return @() }
    return @(Get-Content -LiteralPath $script:OG3_AuditLog | Where-Object { $_.Trim() } | ForEach-Object {
        try { $_ | ConvertFrom-Json } catch { $null }
    } | Where-Object { $null -ne $_ })
}

function Test-OG3AuditAppendOnly {
    <#
    .SYNOPSIS
      append-only 不变量: 取当前行快照, 追加一条探针, 断言旧行逐字未变且新行在末尾.
      只追加, 不删除; 返回 beforeCount/afterCount/prefixUnchanged.
    #>
    [CmdletBinding()]
    param()
    if (-not (Test-Path -LiteralPath $script:OG3_AuditLog)) { New-Item -ItemType File -Path $script:OG3_AuditLog -Force | Out-Null }
    $before = @(Get-Content -LiteralPath $script:OG3_AuditLog)
    Add-OG3Audit -InputSummary '__appendonly_probe__' -AstVerdict 'n/a' -ConfirmResult 'n/a' -ExecutionResult 'n/a' -BackupPath '' -RollbackRecord '' | Out-Null
    $after = @(Get-Content -LiteralPath $script:OG3_AuditLog)
    $prefixUnchanged = $true
    if ($before.Count -gt 0) {
        for ($i = 0; $i -lt $before.Count; $i++) {
            if (-not [string]::Equals($before[$i], $after[$i], [System.StringComparison]::Ordinal)) { $prefixUnchanged = $false; break }
        }
    }
    return [pscustomobject]@{ beforeCount=$before.Count; afterCount=$after.Count; prefixUnchanged=$prefixUnchanged }
}

Export-ModuleMember -Function Add-OG3Audit,Get-OG3AuditEntries,Test-OG3AuditAppendOnly
