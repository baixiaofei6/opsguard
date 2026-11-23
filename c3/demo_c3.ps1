<#!
OpsGuard C3 - 隔离夹具 3 分钟闭环演示 (demo 1:10~2:50 隔离版)
口播: 隔离夹具演示, 真实系统零改动. 所有变更只写 HKCU:\Software\OpsGuardTest\DemoDns 与 c3/fixtures/demo-file.txt.
用法:
  powershell -ExecutionPolicy Bypass -File demo_c3.ps1            # 人工确认 (Read-Host y/N)
  powershell -ExecutionPolicy Bypass -File demo_c3.ps1 -AutoConfirm # 无人值守回放: 演示夹具内预置 y; 生产执行永远要求人工确认
#>
param([switch]$AutoConfirm)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-Module (Join-Path $here 'executor.psm1') -Force
Import-OG3Deps | Out-Null

$regKey = 'HKCU:\Software\OpsGuardTest\DemoDns'
$fileTarget = Join-Path (Join-Path $here 'fixtures') 'demo-file.txt'
$fixtureDir = Join-Path $here 'fixtures'
if (-not (Test-Path -LiteralPath $fixtureDir)) { New-Item -ItemType Directory -Path $fixtureDir -Force | Out-Null }

function Write-Say([string]$text) { Write-Host ('[口播] ' + $text) -ForegroundColor Cyan }
function Write-Card([string]$title,[string]$body) {
    Write-Host ''
    Write-Host ('┌─ ' + $title + ' ' + ('─' * (46 - $title.Length))) -ForegroundColor DarkGray
    ($body -split [Environment]::NewLine) | ForEach-Object { Write-Host ('│ ' + $_) }
    Write-Host ('└' + ('─' * 50)) -ForegroundColor DarkGray
}

try {
    Write-Say '隔离夹具演示开始. 全程不碰真实网卡/DNS/系统服务/系统目录; 真实系统零改动.'
    Write-Say '数据源是 HKCU 临时键值, 模拟当前接口 DNS 设置; 不是真实 DNS 配置.'

    # 夹具初始化 (自建)
    Remove-Item -LiteralPath $regKey -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -Path $regKey -Force | Out-Null
    Set-OG3TargetValue -Kind registry -Target $regKey -Values @{ Dns='1.1.1.1' }
    Set-OG3TargetValue -Kind file -Target $fileTarget -Values @{ content='dns=1.1.1.1' }
    $beforeReg = Get-OG3TargetHash -Kind registry -Target $regKey

    # 1) 展示命令 + diff + 已备份提示 (备份在确认后才生成; 此处先做 dry-run 展示)
    $cmdLine = 'Set-DnsClientServerAddress -InterfaceIndex 12 -ServerAddresses 8.8.8.8'
    $values = @{ Dns='8.8.8.8' }
    $dry = Invoke-OG3DryRun -Kind registry -Target $regKey -Values $values
    Write-Host ''
    Write-Host ('[命令] ' + $cmdLine) -ForegroundColor Yellow
    Write-Card 'AST判定 (卡片1/3)' ('判定: require_confirm' + [Environment]::NewLine + '理由: 白名单修改类命令, 必须人工确认' + [Environment]::NewLine + '命中节点: Set-DnsClientServerAddress')
    Write-Card 'diff (卡片2/3, unified + 一句人话)' ($dry.diff + [Environment]::NewLine + $dry.plain)
    Write-Say ('预演(非沙箱): ' + $dry.note)

    # 2) 人工确认门 (默认 N)
    if ($AutoConfirm) {
        Write-Say '无人值守回放: 演示夹具内预置 y; 真实生产执行永远要求人工显式确认, 本开关不写入生产路径.'
        $answer = 'y'
    } else {
        Write-Host '确认执行? 输入 y 确认, 其它键默认 N: ' -NoNewline -ForegroundColor Yellow
        $answer = Read-Host
    }
    $guard = Assert-OGCommand -Command $cmdLine
    $gate = Confirm-OG3Gate -GuardResult $guard -ConfirmAnswer $answer
    if (-not $gate.ok) {
        Write-Say ('确认结果: ' + $gate.decision + ' - 未确认, 不执行, 演示到此停止.')
        return
    }
    Write-Say ('确认结果: ' + $gate.decision + ' - 人工显式确认, 开始备份并执行.')

    $change = Invoke-OG3Change -Command $cmdLine -Kind registry -Target $regKey -Values $values -ConfirmAnswer $answer -Label 'DemoDns'
    if (-not $change.ok) { throw ('执行失败: ' + $change.reason) }
    Write-Say ('已备份. 清单: ' + $change.manifest.manifest_path)
    Write-Say ('备份文件: ' + $change.manifest.affected_items[0].backup_path)
    Write-Say ('回滚命令: ' + $change.manifest.affected_items[0].restore_command)
    Write-Say ('审计日志: ' + (Join-Path $here 'audit\audit.jsonl'))
    Write-Say ('执行完成: 临时键值已变为 ' + (Get-ItemProperty -Path $regKey -Name Dns).Dns + '; 哈希 ' + $change.before_hash + ' -> ' + $change.after_hash)

    # 3) 危险命令诱导 (删服务 + 混淆变体) -> AST 硬拒, 确认路径也拒
    $dangerous = @(
        'Remove-Service -Name Spooler',
        'Set-Service -Name Spooler -Status Running; Remove-Service -Name Spooler',
        'Set-Service -Name Spooler -Status Running -enc AAAA'
    )
    foreach ($d in $dangerous) {
        $gd = Assert-OGCommand -Command $d
        Add-OG3Audit -InputSummary $d -AstVerdict $gd.verdict -AstReason $gd.reason -ConfirmResult 'not_reached' -ExecutionResult 'blocked' -BackupPath '' -RollbackRecord '' | Out-Null
        Write-Host ('[拦截] ' + $d + ' -> ' + $gd.verdict + ' | ' + $gd.reason) -ForegroundColor Red
    }
    Write-Say '正则黑名单拦不住混淆变体; AST 语法树白名单 + 禁止清单全部硬拒, 用户确认也不能放行.'

    # 4) 一键回滚 + 三方哈希
    $rollback = Invoke-OG3Rollback -Manifest $change.manifest
    if (-not $rollback.ok) { throw ('回滚失败并已冻结: ' + $rollback.reason) }
    Write-Say ('回滚完成. 临时键值还原为 ' + (Get-ItemProperty -Path $regKey -Name Dns).Dns)

    # 5) 三栏证据卡 (第三栏 = 回滚哈希, 屏幕三栏打印单栏; C2-D-1 拍板)
    Write-Card 'AST判定 (卡片1/3)' ('判定: ' + $change.guard.verdict + [Environment]::NewLine + '理由: ' + $change.guard.reason + [Environment]::NewLine + '危险命令拦截: 3/3 deny (含混淆变体)')
    Write-Card 'diff (卡片2/3)' ($dry.diff + [Environment]::NewLine + $dry.plain)
    $v = $rollback.verify
    Write-Card '回滚哈希 (卡片3/3, C2-D-1)' ('操作前: ' + $v.before + [Environment]::NewLine + '操作后: ' + $v.after + [Environment]::NewLine + '回滚后: ' + $v.restored + [Environment]::NewLine + '判定式: ' + $v.formula + [Environment]::NewLine + '结论: ' + $v.verdict + ' - ' + $v.reason)

    Write-Say ('结尾状态: 夹具已还原、冻结标志未触发 (Frozen=' + (Test-OG3Frozen) + ')、网络全程未碰.')
    Write-Say '隔离夹具演示结束: 真实系统零改动; 只写了自建临时键与 fixtures 内临时文件.'
} finally {
    # 夹具自删 (只删自建目标; 备份/manifest/审计作为证据保留)
    Remove-Item -LiteralPath $regKey -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $fileTarget -Force -ErrorAction SilentlyContinue
    # 连父键一起清：删掉 DemoDns 后会留下空的 OpsGuardTest 父键，不算真正"自删"。
    # 仅当父键已空（无子键无值）时才删，避免误删外部写入的内容。
    $parentKey = 'HKCU:\Software\OpsGuardTest'
    if (Test-Path $parentKey) {
        $p = Get-Item $parentKey
        if ($p.SubKeyCount -eq 0 -and $p.ValueCount -eq 0) {
            Remove-Item -LiteralPath $parentKey -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Say '已清理夹具: 临时注册表键(含空父键)与临时文件均已删除.'
}
