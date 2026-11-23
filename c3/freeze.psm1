<#!
OpsGuard C3 - 回滚失败冻结预案
回滚失败 -> 保留备份 -> 设冻结标志 -> 禁止后续一切操作 -> 输出手工恢复步骤.
冻结标志与手工指引只在 c3/fixtures/ 内, 不动系统.
#>

$script:OG3_FreezeDir = Join-Path $PSScriptRoot 'fixtures'
$script:OG3_FreezeFlag = Join-Path $script:OG3_FreezeDir 'FROZEN.flag'
$script:OG3_FreezeGuide = Join-Path $script:OG3_FreezeDir 'MANUAL_RECOVERY.txt'

function Test-OG3Frozen {
    <# .SYNOPSIS 查询冻结标志是否存在. #>
    [CmdletBinding()] param()
    return (Test-Path -LiteralPath $script:OG3_FreezeFlag)
}

function Assert-OG3NotFrozen {
    <# .SYNOPSIS 冻结时 throw(fail-closed); 未冻结返回 true. 执行器每个入口都调用. #>
    [CmdletBinding()] param()
    if (Test-OG3Frozen) {
        $guide = if (Test-Path -LiteralPath $script:OG3_FreezeGuide) { [System.IO.File]::ReadAllText($script:OG3_FreezeGuide) } else { '(无指引文件)' }
        throw ('系统已冻结, 禁止任何进一步操作. 手工恢复指引: ' + $guide)
    }
    return $true
}

function Set-OG3Freeze {
    <#
    .SYNOPSIS
      进入冻结: 保留备份, 写冻结标志 + 手工恢复指引(备份位置 + 逐项恢复指引), 返回指引文本.
    #>
    [CmdletBinding()]
    param(
        [string]$Reason,
        [object[]]$ManifestEntries = @(),
        [string]$ManifestPath
    )
    if (-not (Test-Path -LiteralPath $script:OG3_FreezeDir)) { New-Item -ItemType Directory -Path $script:OG3_FreezeDir -Force | Out-Null }
    $lines = @()
    $lines += 'OPSGUARD FREEZE / 手工恢复指引'
    $lines += '冻结时间(UTC): ' + [DateTime]::UtcNow.ToString('o')
    $lines += '原因: ' + $Reason
    $lines += '重要: 备份文件保留在 c3/fixtures/, 禁止删除; 冻结期间执行器拒绝一切操作.'
    $lines += '清单: ' + $ManifestPath
    $lines += '逐项恢复:'
    foreach ($e in $ManifestEntries) {
        $lines += ('  - [' + $e.kind + '] ' + $e.target + ' -> 备份 ' + $e.backup_path + ' | 命令 ' + $e.restore_command)
    }
    $lines += '恢复完成并人工核验后, 由维护者手动删除 ' + $script:OG3_FreezeFlag + ' 解除冻结.'
    $guide = $lines -join [Environment]::NewLine
    [System.IO.File]::WriteAllText($script:OG3_FreezeGuide, $guide, (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::WriteAllText($script:OG3_FreezeFlag, 'FROZEN ' + [DateTime]::UtcNow.ToString('o'), (New-Object System.Text.UTF8Encoding($false)))
    return $guide
}

function Clear-OG3Freeze {
    <# .SYNOPSIS 仅供测试/人工核验后解除冻结(正常执行路径不调用). #>
    [CmdletBinding()] param()
    Remove-Item -LiteralPath $script:OG3_FreezeFlag -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $script:OG3_FreezeGuide -Force -ErrorAction SilentlyContinue
    return $true
}

Export-ModuleMember -Function Test-OG3Frozen,Assert-OG3NotFrozen,Set-OG3Freeze,Clear-OG3Freeze
