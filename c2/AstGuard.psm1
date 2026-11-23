<#!
OpsGuard C2 - AST 安全门 PowerShell 栈 (TASK 5.3 硬要求: 真 AST, 零第三方依赖)
用 System.Management.Automation.Language.Parser.ParseInput + Ast.FindAll 做静态校验.
三态语义与 Python 版一致: allow_readonly / require_confirm / deny (fail-closed).
仅做判定, 绝不执行任何命令.
#>

$script:OG_AllowReadOnly = @(
    'Get-NetAdapter', 'Get-DnsClientServerAddress', 'Get-Service', 'Get-WinEvent'
)
$script:OG_RequireConfirm = @(
    'Set-Service', 'Set-DnsClientServerAddress'
)
# 禁止清单: 删服务/格式化/删用户数据/关安全软件 -> AST 层 deny, 确认门不得覆盖.
$script:OG_Forbidden = @(
    'Remove-Service','sc','sc.exe','Format-Volume','Format-Disk','Format-Com','Format',
    'Clear-Disk','Remove-Partition','diskpart','cipher','bcdedit','Remove-Item','del','rd',
    'rmdir','Remove-LocalUser','Remove-ADUser','Remove-User','net','net.exe','taskkill',
    'Stop-Process','Stop-Computer','Set-MpPreference','Stop-MpService','Remove-MpThreat'
)
# 动态执行/下载执行链/别名操纵 -> deny.
$script:OG_Dynamic = @(
    'Invoke-Expression','iex','Invoke-WebRequest','iwr','Invoke-RestMethod','irm',
    'Start-BitsTransfer','bitsadmin','Start-Process','saps','Set-Alias','New-Alias',
    'Export-Alias','Import-Alias','Remove-Alias','Set-Variable','Add-Content','Set-Content','Out-File'
)
$script:OG_Aliases = @(
    'gs','gwmi','gci','ls','dir','cat','gc','cd','ps','kill','sp','ss','sas','ri','rm','foreach','%','?'
)
# 白名单命令 -> 允许的完整参数名 (只允许完整名; 缩写 -Stat 走 StaticParameterBinder 解析后必须唯一命中).
$script:OG_AllowedParams = @{
    'Get-NetAdapter'              = @('Name')
    'Get-DnsClientServerAddress'  = @('InterfaceIndex')
    'Get-Service'                 = @('Name')
    'Get-WinEvent'                = @('LogName','MaxEvents')
    'ipconfig'                    = @()
    'Set-Service'                 = @('Name','Status')
    'Set-DnsClientServerAddress'  = @('InterfaceIndex','ServerAddresses')
}

function New-OGResult {
    param([string]$Verdict, [string]$Reason, [string]$Node, [string]$CommandName)
    [pscustomobject]@{
        verdict       = $Verdict
        reason        = $Reason
        matched_node  = $Node
        command_name  = $CommandName
    }
}

function Assert-OGCommand {
    <#
    .SYNOPSIS
      对单条 PowerShell 命令做 AST 三态判定; 返回 pscustomobject(verdict/reason/matched_node/command_name).
    .DESCRIPTION
      ParseInput 解析失败/语法错误 -> deny. 递归遍历所有 CommandAst(含脚本块/子表达式/管道内命令).
      命令名必须静态可解析(StringConstantExpressionAst); 变量/字符串拼接/成员调用/别名/未知 cmdlet -> deny.
      危险结构(--%/反引号/动态执行/下载执行链/EncodedCommand 等)命中即 deny.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Command)

    if ([string]::IsNullOrWhiteSpace($Command)) {
        return New-OGResult 'deny' '空命令(fail-closed)' '<empty>' $null
    }

    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($Command, [ref]$tokens, [ref]$errors)
    if ($null -eq $ast -or $errors.Count -gt 0) {
        $firstErr = if ($errors.Count -gt 0) { $errors[0].Message } else { '<parse-error>' }
        return New-OGResult 'deny' '解析失败/语法错误(fail-closed)' $firstErr $null
    }

    # stop-parsing 符 --% : AST 会把它后的内容当 opaque string; MVP 一律 deny.
    foreach ($t in $tokens) {
        if ($t.Text -eq '--%') {
            return New-OGResult 'deny' '危险结构: 停止解析符 --%' $t.Text $null
        }
        # 反引号转义 (Backtick 字符 char 96)
        if ($t.Text -and $t.Text.Contains([string][char]96)) {
            return New-OGResult 'deny' '危险结构: 反引号转义' $t.Text $null
        }
    }

    # 递归遍历所有 CommandAst (FindAll 覆盖脚本块/子表达式/管道内命令).
    $commands = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.CommandAst] }, $true)
    if ($null -eq $commands -or $commands.Count -eq 0) {
        return New-OGResult 'deny' '未找到可判定命令(fail-closed)' '<none>' $null
    }

    $allTiers = @()
    foreach ($cmd in $commands) {
        $nameAst = $cmd.CommandElements[0]
        # 静态命令名必须是字面量字符串; 变量/表达式/脚本块动态名 -> deny.
        if ($null -eq $nameAst -or $nameAst -isnot [System.Management.Automation.Language.StringConstantExpressionAst]) {
            $nodeText = if ($cmd.CommandElements.Count -gt 0) { $cmd.CommandElements[0].Extent.Text } else { $cmd.Extent.Text }
            return New-OGResult 'deny' '动态命令名/非静态命令名(fail-closed)' $nodeText $null
        }
        $name = $nameAst.Value
        if ([string]::IsNullOrWhiteSpace($name)) {
            return New-OGResult 'deny' '空命令名(fail-closed)' $cmd.Extent.Text $null
        }
        $lower = $name.ToLowerInvariant()

        # 禁止清单 + 危险命令 + 别名 -> deny.
        if ($script:OG_Forbidden -contains $lower) {
            return New-OGResult 'deny' '禁止清单命令(确认门不得覆盖)' $cmd.Extent.Text $name
        }
        if ($script:OG_Dynamic -contains $lower) {
            return New-OGResult 'deny' '危险命令: 动态执行/下载执行链/别名操纵' $cmd.Extent.Text $name
        }
        if ($script:OG_Aliases -contains $lower) {
            return New-OGResult 'deny' '别名命令(Alias 覆盖风险)' $cmd.Extent.Text $name
        }
        # EncodedCommand/-enc 出现在任意命令的参数里 -> deny.
        foreach ($el in $cmd.CommandElements) {
            $txt = $el.Extent.Text
            if ($txt -match '(?i)^-(enc|encodedcommand|e|encodedarguments)(\s|$)') {
                return New-OGResult 'deny' '危险结构: EncodedCommand' $txt $name
            }
        }

        $tier = $null
        if ($script:OG_AllowReadOnly -contains $name -or $script:OG_AllowReadOnly -contains $lower) { $tier = 'allow_readonly' }
        if ($script:OG_RequireConfirm -contains $name -or $script:OG_RequireConfirm -contains $lower) { $tier = 'require_confirm' }
        if ($lower -eq 'ipconfig') { $tier = 'allow_readonly' }
        if ($null -eq $tier) {
            return New-OGResult 'deny' '白名单外命令, 默认拒绝' $cmd.Extent.Text $name
        }

        # ipconfig: 只允许 /all (原生 exe 不接受 opaque tail, --% 已 deny).
        if ($lower -eq 'ipconfig') {
            foreach ($el in $cmd.CommandElements[1..($cmd.CommandElements.Count-1)]) {
                $txt = $el.Extent.Text
                if ($txt -ne '/all') {
                    return New-OGResult ('deny') ('原生命令参数白名单外: ' + $txt) $txt $name
                }
            }
            $allTiers += 'allow_readonly'
            continue
        }

        # cmdlet 参数: 用元数据把缩写(-Stat)解析为规范参数名, 二义性/未知 -> deny.
        $allowed = $script:OG_AllowedParams[$name]
        if ($null -eq $allowed) {
            if ($script:OG_AllowedParams.ContainsKey($lower)) { $allowed = $script:OG_AllowedParams[$lower] }
        }
        if ($null -eq $allowed) {
            return New-OGResult 'deny' '白名单元数据缺失(fail-closed)' $cmd.Extent.Text $name
        }
        $cmdInfo = $null
        try { $cmdInfo = Get-Command -Name $name -ErrorAction Stop } catch { $cmdInfo = $null }

        # 参数必须有值且参数名完整（fail-closed）。
        # 注意：PowerShell 5.1 的 ParseInput 不会把值绑到 CommandParameterAst.Argument
        # （其 Argument 恒为 null），值在 CommandElements 数组里是独立的后续元素。
        # 因此按数组索引判断：每个参数后必须紧跟一个"非参数"元素作为值；
        # 只认完整参数名，缩写（-Stat）一律 deny，禁止靠元数据猜"只读"。
        $els = @($cmd.CommandElements)
        for ($i = 1; $i -lt $els.Count; $i++) {
            $el = $els[$i]
            if ($el -is [System.Management.Automation.Language.CommandParameterAst]) {
                $pn = $el.ParameterName.ToLowerInvariant()
                if ($allowed -notcontains $pn) {
                    return New-OGResult 'deny' ('参数缩写/白名单外参数(fail-closed): -' + $el.ParameterName) $el.Extent.Text $name
                }
                $nextIsValue = ($i + 1 -lt $els.Count) -and
                    ($els[$i + 1] -isnot [System.Management.Automation.Language.CommandParameterAst])
                if (-not $nextIsValue) {
                    return New-OGResult 'deny' ('参数缺少值(fail-closed): -' + $el.ParameterName) $el.Extent.Text $name
                }
            }
        }
        $allTiers += $tier
    }

    # 多命令混合时取最严格（require_confirm 优先于 allow_readonly）。
    # 绝不能只看第一条：否则 "Get-Service ...; Set-Service ..." 会把修改命令放行(权限提升)。
    $finalTier = 'allow_readonly'
    if ($allTiers -contains 'require_confirm') { $finalTier = 'require_confirm' }
    return New-OGResult $finalTier ('白名单命中(共 ' + $allTiers.Count + ' 条, tier=' + $finalTier + ')') ($commands[0].Extent.Text) $null
}

Export-ModuleMember -Function Assert-OGCommand
