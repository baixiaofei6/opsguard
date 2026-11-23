#Requires -Version 5.1
<#
OpsGuard C1 · 脱敏层（P0，出网唯一出口）— PowerShell 5.1，无第三方模块。
规则与 Python 版 redact.py 一致：
- RFC1918（10/8、172.16/12、192.168/16）边界感知 + 八位组 0-255 校验
- MAC：冒号 / 横杠 / Cisco 点分
- 主机名：精确匹配表（禁泛正则），按长度降序
- 确定性映射 [IP_n]/[MAC_n]/[HOST_n]；映射表只留本地；restore 回填
未覆盖：公网 IP、敏感路径、IPv6、无分隔符 MAC（详见 redact.py 文档字符串与 README）。
#>

$script:Octet = '(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)'
$script:Rfc1918 = '(?:10\.' + $script:Octet + '\.' + $script:Octet + '\.' + $script:Octet +
    '|172\.(?:1[6-9]|2[0-9]|3[01])\.' + $script:Octet + '\.' + $script:Octet +
    '|192\.168\.' + $script:Octet + '\.' + $script:Octet + ')'
$script:Options = [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
$script:ReIp = New-Object System.Text.RegularExpressions.Regex(('(?<![0-9.])' + $script:Rfc1918 + '(?![0-9.])'), $script:Options)
$script:ReMac = New-Object System.Text.RegularExpressions.Regex('(?<![0-9A-Fa-f])(?:(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}|(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4})(?![0-9A-Fa-f])', $script:Options)

function New-Placeholder {
    param([hashtable]$Redactor, [string]$Kind, [string]$Value)
    if ($Redactor.Reverse.ContainsKey($Value)) { return [string]$Redactor.Reverse[$Value] }
    $Redactor.Counters[$Kind] = [int]$Redactor.Counters[$Kind] + 1
    $ph = '[' + $Kind + '_' + $Redactor.Counters[$Kind] + ']'
    $Redactor.Reverse[$Value] = $ph
    $Redactor.Map[$ph] = $Value
    return [string]$ph
}

function New-Redactor {
    param([string[]]$Hosts = @())
    $seen = @{}
    $unique = @()
    foreach ($h in $Hosts) { if ($h -and -not $seen.ContainsKey($h)) { $seen[$h] = $true; $unique += $h } }
    $sorted = @($unique | Sort-Object { $_.Length } -Descending)
    return @{
        Map      = @{}
        Reverse  = @{}
        Counters = @{ IP = 0; MAC = 0; HOST = 0 }
        Hosts    = $sorted
    }
}

function Redact-Text {
    param([hashtable]$Redactor, [string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return $Text }

    $macEval = [System.Text.RegularExpressions.MatchEvaluator]{
        param($m)
        New-Placeholder -Redactor $Redactor -Kind 'MAC' -Value $m.Value
    }
    $out = $script:ReMac.Replace($Text, $macEval)

    $ipEval = [System.Text.RegularExpressions.MatchEvaluator]{
        param($m)
        New-Placeholder -Redactor $Redactor -Kind 'IP' -Value $m.Value
    }
    $out = $script:ReIp.Replace($out, $ipEval)

    foreach ($h in $Redactor.Hosts) {
        $rx = New-Object System.Text.RegularExpressions.Regex(('(?<![A-Za-z0-9_-])' + [regex]::Escape($h) + '(?![A-Za-z0-9_-])'), $script:Options)
        $hostEval = [System.Text.RegularExpressions.MatchEvaluator]{
            param($m)
            New-Placeholder -Redactor $Redactor -Kind 'HOST' -Value $h
        }
        $out = $rx.Replace($out, $hostEval)
    }
    return [string]$out
}

function Restore-Text {
    param([hashtable]$Redactor, [string]$Text)
    if ($null -eq $Text) { return $Text }
    $out = [string]$Text
    foreach ($ph in @($Redactor.Map.Keys | Sort-Object { $_.Length } -Descending)) {
        $out = $out.Replace([string]$ph, [string]$Redactor.Map[$ph])
    }
    return $out
}

function Get-RedactionMap {
    param([hashtable]$Redactor)
    $copy = @{}
    foreach ($k in $Redactor.Map.Keys) { $copy[$k] = $Redactor.Map[$k] }
    return $copy
}

function Test-RedactionApplied {
    param([hashtable]$Redactor)
    return ([int]$Redactor.Counters.IP + [int]$Redactor.Counters.MAC + [int]$Redactor.Counters.HOST) -gt 0
}

function Get-RedactionPayload {
    param([string]$Text, [string[]]$Hosts = @())
    $r = New-Redactor -Hosts $Hosts
    $payload = Redact-Text -Redactor $r -Text $Text
    return [pscustomobject]@{ Payload = $payload; Redactor = $r }
}

Export-ModuleMember -Function New-Redactor, Redact-Text, Restore-Text, Get-RedactionMap, Test-RedactionApplied, Get-RedactionPayload
