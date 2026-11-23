<#!
OpsGuard C3 · 黄金测试集 (Pester 3.4 管道语法: $x | Should Be; 不使用 Pester5 独有的 Be 参数形式 / Show 参数 / 全局 setup 块)
全部夹具自建自删: HKCU:\Software\OpsGuardTest 临时键 + c3/fixtures 临时文件. 真实系统零改动.
#>

$c3 = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-Module (Join-Path $c3 'executor.psm1') -Force
Import-Module (Join-Path $c3 'verify_hash.psm1') -Force
Import-Module (Join-Path $c3 'audit.psm1') -Force
Import-Module (Join-Path $c3 'freeze.psm1') -Force
Import-OG3Deps | Out-Null
$fixtureDir = Join-Path $c3 'fixtures'
if (-not (Test-Path -LiteralPath $fixtureDir)) { New-Item -ItemType Directory -Path $fixtureDir -Force | Out-Null }

Describe 'OpsGuard C3 安全执行器黄金测试' {

    BeforeEach {
        $script:OG3T_Files = @()
        $script:OG3T_Keys = @()
        Import-Module (Join-Path $c3 'executor.psm1') -Force
    }

    AfterEach {
        foreach ($f in $script:OG3T_Files) { Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue }
        foreach ($k in $script:OG3T_Keys) { Remove-Item -LiteralPath $k -Recurse -Force -ErrorAction SilentlyContinue }
        # 清理由测试触发的冻结, 保证用例间隔离
        Clear-OG3Freeze | Out-Null
        # 清理本测试生成的 manifest / bak (按名字带 OG3T 前缀的备份, 精确匹配)
        Get-ChildItem -LiteralPath $fixtureDir -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '_OG3T' } | Remove-Item -Force -ErrorAction SilentlyContinue
        # 连空父键一起清: 删掉 OG3T_* 子键后会留下空的 OpsGuardTest 父键, 不算真正自删.
        # 仅当父键已空(无子键无值)时才删, 避免误删外部写入的内容.
        $parentKey = 'HKCU:\Software\OpsGuardTest'
        if (Test-Path $parentKey) {
            $pk = Get-Item $parentKey
            if ($pk.SubKeyCount -eq 0 -and $pk.ValueCount -eq 0) {
                Remove-Item -LiteralPath $parentKey -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    function New-OG3TKeyName { return 'HKCU:\Software\OpsGuardTest\OG3T_' + [guid]::NewGuid().ToString('N').Substring(0,10) }
    function New-OG3TFilePath { return Join-Path $fixtureDir ('OG3T_' + [guid]::NewGuid().ToString('N').Substring(0,10) + '.txt') }

    Context '回滚往返三方哈希 (要求: 回滚后=操作前 且 操作后≠操作前, 至少3组)' {

        It '注册表临时键: 变更->回滚->哈希一致' {
            $k = New-OG3TKeyName
            $script:OG3T_Keys += $k
            New-Item -Path $k -Force | Out-Null
            Set-OG3TargetValue -Kind registry -Target $k -Values @{ Dns='1.1.1.1' }
            $r = Invoke-OG3Change -Command 'Set-DnsClientServerAddress -InterfaceIndex 12 -ServerAddresses 8.8.8.8' -Kind registry -Target $k -Values @{ Dns='8.8.8.8' } -ConfirmAnswer 'y' -Label 'OG3T-reg'
            ($r.ok) | Should Be $true
            ($r.after_hash -ne $r.before_hash) | Should Be $true
            $rb = Invoke-OG3Rollback -Manifest $r.manifest
            ($rb.ok) | Should Be $true
            ($rb.verify.restored -eq $rb.verify.before) | Should Be $true
            ($rb.verify.after -ne $rb.verify.before) | Should Be $true
            ($rb.verify.verdict) | Should Be 'rollback_verified'
            ((Get-ItemProperty -Path $k -Name Dns).Dns) | Should Be '1.1.1.1'
        }

        It '夹具临时文件 #1: 变更->回滚->哈希一致' {
            $f = New-OG3TFilePath
            $script:OG3T_Files += $f
            Set-OG3TargetValue -Kind file -Target $f -Values @{ content='ORIGINAL-A' }
            $r = Invoke-OG3Change -Command 'Set-Service -Name Spooler -Status Running' -Kind file -Target $f -Values @{ content='MODIFIED-A' } -ConfirmAnswer 'y' -Label 'OG3T-file1'
            ($r.after_hash -ne $r.before_hash) | Should Be $true
            $rb = Invoke-OG3Rollback -Manifest $r.manifest
            ($rb.verify.ok) | Should Be $true
            ($rb.verify.restored -eq $rb.verify.before) | Should Be $true
            ($rb.verify.after -ne $rb.verify.before) | Should Be $true
            ([System.IO.File]::ReadAllText($f)) | Should Be 'ORIGINAL-A'
        }

        It '夹具临时文件 #2: 变更->回滚->哈希一致' {
            $f = New-OG3TFilePath
            $script:OG3T_Files += $f
            Set-OG3TargetValue -Kind file -Target $f -Values @{ content='ORIGINAL-B' }
            $r = Invoke-OG3Change -Command 'Set-Service -Name Spooler -Status Running' -Kind file -Target $f -Values @{ content='MODIFIED-B' } -ConfirmAnswer 'y' -Label 'OG3T-file2'
            ($r.after_hash -ne $r.before_hash) | Should Be $true
            $rb = Invoke-OG3Rollback -Manifest $r.manifest
            ($rb.verify.ok) | Should Be $true
            ($rb.verify.restored -eq $rb.verify.before) | Should Be $true
            ($rb.verify.after -ne $rb.verify.before) | Should Be $true
            ([System.IO.File]::ReadAllText($f)) | Should Be 'ORIGINAL-B'
        }
    }

    Context '确认门无旁路 (y/N 默认 N, 无跳过/超时)' {

        It 'ConfirmAnswer=n 不执行且目标未变' {
            $f = New-OG3TFilePath
            $script:OG3T_Files += $f
            Set-OG3TargetValue -Kind file -Target $f -Values @{ content='KEEP' }
            $before = Get-OG3TargetHash -Kind file -Target $f
            $r = Invoke-OG3Change -Command 'Set-Service -Name Spooler -Status Running' -Kind file -Target $f -Values @{ content='CHANGED' } -ConfirmAnswer 'n'
            ($r.ok) | Should Be $false
            ($r.stage) | Should Be 'confirm'
            ((Get-OG3TargetHash -Kind file -Target $f) -eq $before) | Should Be $true
        }

        It 'ConfirmAnswer 为空 默认 N 不执行' {
            $g = Assert-OGCommand -Command 'Set-Service -Name Spooler -Status Running'
            $gate = Confirm-OG3Gate -GuardResult $g -ConfirmAnswer ''
            ($gate.ok) | Should Be $false
            ($gate.decision) | Should Be 'confirm_required'
        }

        It 'SkipConfirm 开关不产生旁路' {
            $f = New-OG3TFilePath
            $script:OG3T_Files += $f
            Set-OG3TargetValue -Kind file -Target $f -Values @{ content='KEEP' }
            $r = Invoke-OG3Change -Command 'Set-Service -Name Spooler -Status Running' -Kind file -Target $f -Values @{ content='CHANGED' } -SkipConfirm
            ($r.ok) | Should Be $false
            ([System.IO.File]::ReadAllText($f)) | Should Be 'KEEP'
        }

        It 'allow_readonly 命令不能进入确认门' {
            $g = Assert-OGCommand -Command 'Get-Service -Name Spooler'
            $gate = Confirm-OG3Gate -GuardResult $g -ConfirmAnswer 'y'
            ($gate.ok) | Should Be $false
            ($gate.decision) | Should Be 'deny'
        }
    }

    Context 'dry-run 无落盘副作用' {

        It '文件 dry-run 不创建目标文件' {
            $f = New-OG3TFilePath
            $script:OG3T_Files += $f
            (Test-Path -LiteralPath $f) | Should Be $false
            $d = Invoke-OG3DryRun -Kind file -Target $f -Values @{ content='X' }
            (Test-Path -LiteralPath $f) | Should Be $false
            ($d.dry_run) | Should Be $true
            ($d.is_sandbox) | Should Be $false
            ($d.before_hash) | Should Be '<missing>'
        }

        It '注册表 dry-run 不创建目标键' {
            $k = New-OG3TKeyName
            $script:OG3T_Keys += $k
            (Test-Path -LiteralPath $k) | Should Be $false
            $d = Invoke-OG3DryRun -Kind registry -Target $k -Values @{ Dns='8.8.8.8' }
            (Test-Path -LiteralPath $k) | Should Be $false
            ($d.dry_run) | Should Be $true
        }

        It 'dry-run 明确标注预演非沙箱' {
            $f = New-OG3TFilePath
            $script:OG3T_Files += $f
            Set-OG3TargetValue -Kind file -Target $f -Values @{ content='A' }
            $d = Invoke-OG3DryRun -Kind file -Target $f -Values @{ content='B' }
            ($d.note -match '非沙箱') | Should Be $true
            ($d.diff -match '\+B') | Should Be $true
            ([System.IO.File]::ReadAllText($f)) | Should Be 'A'
        }
    }

    Context '危险命令拦截 (AST 白名单 + 禁止清单, 确认路径也不放行)' {

        It '删服务明文 deny' {
            $g = Assert-OGCommand -Command 'Remove-Service -Name Spooler'
            ($g.verdict) | Should Be 'deny'
            ($g.reason -match '禁止清单') | Should Be $true
        }

        It '混淆变体: 多命令拼接删服务 deny' {
            $g = Assert-OGCommand -Command 'Set-Service -Name Spooler -Status Running; Remove-Service -Name Spooler'
            ($g.verdict) | Should Be 'deny'
        }

        It '混淆变体: EncodedCommand deny' {
            $g = Assert-OGCommand -Command 'Set-Service -Name Spooler -Status Running -enc AAAA'
            ($g.verdict) | Should Be 'deny'
        }

        It '白名单外陌生命令默认 deny' {
            $g = Assert-OGCommand -Command 'Invoke-Expression "Get-Service"'
            ($g.verdict) | Should Be 'deny'
        }

        It '危险命令即使确认也不能进入执行路径' {
            $f = New-OG3TFilePath
            $script:OG3T_Files += $f
            Set-OG3TargetValue -Kind file -Target $f -Values @{ content='SAFE' }
            $r = Invoke-OG3Change -Command 'Remove-Service -Name Spooler' -Kind file -Target $f -Values @{ content='BAD' } -ConfirmAnswer 'y'
            ($r.ok) | Should Be $false
            ($r.stage) | Should Be 'ast'
            ([System.IO.File]::ReadAllText($f)) | Should Be 'SAFE'
        }
    }

    Context '回滚失败冻结路径 (>=1组)' {

        It '哈希判定不成立 -> 冻结 -> 后续操作被拒 -> 输出手工指引' {
            $f = New-OG3TFilePath
            $script:OG3T_Files += $f
            Set-OG3TargetValue -Kind file -Target $f -Values @{ content='ORIGINAL' }
            $fakeManifest = [pscustomobject]@{
                command='fake'; manifest_path=(Join-Path $fixtureDir 'OG3T_fake_manifest.json')
                affected_items=@([pscustomobject]@{ kind='file'; target=$f; exists=$true; backup_path=$null; restore_command='n/a' })
                before_hash='DEADBEEF'; after_hash='CAFEBABE'
            }
            $rb = Invoke-OG3Rollback -Manifest $fakeManifest
            ($rb.ok) | Should Be $false
            ($rb.frozen) | Should Be $true
            (Test-OG3Frozen) | Should Be $true
            ($rb.guide -match '手工恢复指引') | Should Be $true
            ($rb.guide -match '备份') | Should Be $true
            { Assert-OG3NotFrozen } | Should Throw
        }
    }

    Context '审计日志 append-only' {

        It '追加不改写历史行且 seq 递增' {
            $a1 = Add-OG3Audit -InputSummary 'OG3T-1' -AstVerdict 'allow_readonly' -ConfirmResult 'n/a' -ExecutionResult 'n/a' -BackupPath '' -RollbackRecord ''
            $a2 = Add-OG3Audit -InputSummary 'OG3T-2' -AstVerdict 'require_confirm' -ConfirmResult 'confirmed' -ExecutionResult 'n/a' -BackupPath '' -RollbackRecord ''
            ($a2.seq -gt $a1.seq) | Should Be $true
            $r = Test-OG3AuditAppendOnly
            ($r.prefixUnchanged) | Should Be $true
            ($r.afterCount -gt $r.beforeCount) | Should Be $true
        }
    }

    Context '哈希判定式单元' {

        It '回滚后=操作前 且 操作后≠操作前 -> verified' {
            $v = Test-OG3RoundTrip -BeforeHash 'AAA' -AfterHash 'BBB' -RestoredHash 'AAA'
            ($v.ok) | Should Be $true
            ($v.verdict) | Should Be 'rollback_verified'
        }

        It '操作后==操作前 -> failed (证明变更真实生效)' {
            $v = Test-OG3RoundTrip -BeforeHash 'AAA' -AfterHash 'AAA' -RestoredHash 'AAA'
            ($v.ok) | Should Be $false
            ($v.verdict) | Should Be 'rollback_failed'
        }

        It '回滚后≠操作前 -> failed' {
            $v = Test-OG3RoundTrip -BeforeHash 'AAA' -AfterHash 'BBB' -RestoredHash 'CCC'
            ($v.ok) | Should Be $false
        }
    }
}
