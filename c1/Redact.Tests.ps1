#Requires -Version 5.1
# OpsGuard C1 · Redact.psm1 黄金测试（Pester 3.4 管道语法，零新增依赖）
# 运行：Invoke-Pester -Script C:\Users\Administrator\.dsh\im\opsguard\c1\Redact.Tests.ps1 -PassThru
Import-Module Pester -MinimumVersion 3.4 -ErrorAction Stop
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-Module (Join-Path $root 'Redact.psm1') -Force -DisableNameChecking

Describe 'OpsGuard C1 Redact.psm1' {

  Context 'RFC1918 边界与八位组' {
    It '命中三段内网地址' {
      $r = New-Redactor
      $out = Redact-Text -Redactor $r -Text '10.0.0.1 172.16.0.1 172.31.255.254 192.168.0.1 192.168.255.255'
      $out.Contains('10.0.0.1') | Should Be $false
      $out.Contains('172.16.0.1') | Should Be $false
      $out.Contains('192.168.255.255') | Should Be $false
      (Get-RedactionMap -Redactor $r).Count | Should Be 5
    }
    It '不误伤公网/越界/边界子串' {
      $r = New-Redactor
      $text = '8.8.8.8 172.15.0.1 172.32.0.1 192.169.0.1 192.168.256.1 110.0.0.1'
      $out = Redact-Text -Redactor $r -Text $text
      $out | Should Be $text
    }
    It '八位组 0-255 校验' {
      $r = New-Redactor
      (Redact-Text -Redactor $r -Text '192.168.1.256').Contains('[IP_1]') | Should Be $false
      (Redact-Text -Redactor $r -Text '192.168.1.255').Contains('[IP_1]') | Should Be $true
    }
  }

  Context 'MAC 变体' {
    It '冒号/横杠/Cisco 点分全部脱敏' {
      $r = New-Redactor
      $out = Redact-Text -Redactor $r -Text 'AA:BB:CC:DD:EE:FF 00-1a-2b-3c-4d-5e AABB.CCDD.EEFF'
      $out.Contains('AA:BB:CC:DD:EE:FF') | Should Be $false
      $out.Contains('00-1a-2b-3c-4d-5e') | Should Be $false
      $out.Contains('AABB.CCDD.EEFF') | Should Be $false
      $macCount = 0
      foreach ($k in (Get-RedactionMap -Redactor $r).Keys) { if ($k.StartsWith('[MAC_')) { $macCount++ } }
      $macCount | Should Be 3
    }
    It '版本号不被误伤' {
      $r = New-Redactor
      Redact-Text -Redactor $r -Text 'version 1.2.3.4.5.6 build' | Should Be 'version 1.2.3.4.5.6 build'
    }
  }

  Context '主机名精确匹配' {
    It '精确表 + 长度降序，不误伤子串' {
      $r = New-Redactor -Hosts @('WIN-CLIENT-17', 'win-client-17.office.local')
      $out = Redact-Text -Redactor $r -Text 'WIN-CLIENT-17 win-client-17.office.local WIN-CLIENT-17X not-win-client-17'
      $out.Contains('[HOST_1]') | Should Be $true
      $out.Contains('[HOST_2]') | Should Be $true
      $out.Contains('WIN-CLIENT-17X') | Should Be $true
      $out.Contains('not-win-client-17') | Should Be $true
    }
    It '空精确表不误伤未知主机名' {
      $r = New-Redactor
      Redact-Text -Redactor $r -Text 'SERVER-UNKNOWN' | Should Be 'SERVER-UNKNOWN'
    }
  }

  Context '替换↔回填往返（≥5 组）' {
    It '五组混合文本往返一致' {
      $cases = @(
        @{ H=@('HOST-A'); T='server HOST-A at 10.1.2.3' },
        @{ H=@(); T='10.0.0.5 -> dns, 10.0.0.5 -> gateway, again 10.0.0.5' },
        @{ H=@('WIN-OPS-01'); T='host WIN-OPS-01 10.0.0.5 mac AA-BB-CC-DD-EE-FF' },
        @{ H=@(); T='aa:bb:cc:dd:ee:ff and 00-11-22-33-44-55 and AAAA.BBBB.CCCC' },
        @{ H=@(); T='a=172.16.5.4 b=192.168.10.1 c=10.9.8.7' },
        @{ H=@(); T='纯文本 normal text 12345' }
      )
      foreach ($c in $cases) {
        $r = New-Redactor -Hosts $c.H
        $red = Redact-Text -Redactor $r -Text $c.T
        Restore-Text -Redactor $r -Text $red | Should Be $c.T
      }
    }
    It '确定性映射：同值同占位符' {
      $r = New-Redactor -Hosts @('H')
      $out = Redact-Text -Redactor $r -Text '10.2.3.4 H 10.2.3.4 AA-BB-CC-DD-EE-FF H 10.2.3.4'
      ([regex]::Matches($out, [regex]::Escape('[IP_1]'))).Count | Should Be 3
      ([regex]::Matches($out, [regex]::Escape('[HOST_1]'))).Count | Should Be 2
      ([regex]::Matches($out, [regex]::Escape('[MAC_1]'))).Count | Should Be 1
      $r.Map['[IP_1]'] | Should Be '10.2.3.4'
      Redact-Text -Redactor $r -Text 'again 10.2.3.4' | Should Be 'again [IP_1]'
    }
  }

  Context '出网唯一出口' {
    It '出网 payload 不含原始 IP/MAC/主机名且映射只留本地' {
      $p = Get-RedactionPayload -Text 'host WIN-SECRET ip 10.77.88.99 mac DE:AD:BE:EF:00:01 also 10.77.88.99' -Hosts @('WIN-SECRET')
      $p.Payload.Contains('WIN-SECRET') | Should Be $false
      $p.Payload.Contains('10.77.88.99') | Should Be $false
      $p.Payload.Contains('DE:AD:BE:EF:00:01') | Should Be $false
      $p.Payload.Contains('[IP_1]') | Should Be $true
      $p.Payload.Contains('[MAC_1]') | Should Be $true
      $p.Payload.Contains('[HOST_1]') | Should Be $true
      $map = Get-RedactionMap -Redactor $p.Redactor
      $map.Keys.Count | Should Be 3
      (Test-RedactionApplied -Redactor $p.Redactor) | Should Be $true
      (Restore-Text -Redactor $p.Redactor -Text $p.Payload).Contains('10.77.88.99') | Should Be $true
    }
  }
}
