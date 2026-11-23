"""OpsGuard C2 - AST 安全门 Python 双栈之一（fail-closed 保守结构校验）-- Python 3.8+.

说明: Python 标准库没有 PowerShell AST 解析器; 本模块用保守词法+结构扫描实现与
PowerShell AstGuard.psm1 相同的三态语义, 任何无法证明安全的构造一律 deny(fail-closed).
真正的 AST 判定以 PowerShell 版为准(TASK 5.3 硬要求); Python 版供 CLI demo 与
unittest 链路使用, 白名单/三态语义与 PS 版一致.

白名单(唯一"只读"来源, 禁止正则猜):
  allow_readonly  : Get-NetAdapter / Get-DnsClientServerAddress / Get-Service / Get-WinEvent / ipconfig /all
  require_confirm : Set-Service / Set-DnsClientServerAddress
  deny            : 其余一切 + 危险结构 + 禁止清单(即使确认也拒)
"""
import re

ALLOW_READONLY = "allow_readonly"
REQUIRE_CONFIRM = "require_confirm"
DENY = "deny"

# 白名单: 命令 -> (tier, 允许的完整参数名集合). 仅完整参数名, 缩写一律 deny.
_WHITELIST = {
    "get-netadapter": (ALLOW_READONLY, {"name"}),
    "get-dnsclientserveraddress": (ALLOW_READONLY, {"interfaceindex"}),
    "get-service": (ALLOW_READONLY, {"name"}),
    "get-winevent": (ALLOW_READONLY, {"logname", "maxevents"}),
    "ipconfig": (ALLOW_READONLY, set()),
    "set-service": (REQUIRE_CONFIRM, {"name", "status"}),
    "set-dnsclientserveraddress": (REQUIRE_CONFIRM, {"interfaceindex", "serveraddresses"}),
}

# 禁止清单(删服务/格式化/删用户数据/关安全软件): AST 层硬编码 deny, 确认门不得覆盖.
FORBIDDEN_CMDS = {
    "remove-service", "sc.exe", "sc", "format-volume", "format-disk", "format.com",
    "format", "clear-disk", "remove-partition", "diskpart", "cipher", "bcdedit",
    "remove-item", "del", "rd", "rmdir", "remove-localuser", "remove-aduser",
    "remove-user", "net.exe", "net", "taskkill", "stop-process", "stop-computer",
    "set-mppreference", "disable-defender", "stop-mpservice", "remove-mpthreat",
}

# 危险命令: 动态执行 / 下载执行链 / 启动子进程 / 别名操纵.
DYNAMIC_EXEC_CMDS = {
    "invoke-expression", "iex", "invoke-webrequest", "iwr", "invoke-restmethod",
    "irm", "start-bitstransfer", "bitsadmin", "webclient", "downloadstring",
    "downloadfile", "frombase64string", "start-process", "saps", "set-alias",
    "new-alias", "export-alias", "import-alias", "remove-alias", "set-variable",
    "add-content", "set-content", "out-file",
}
# 常见别名(覆盖 Alias 覆盖/绕过): 白名单外别名命令明确理由 deny.
_KNOWN_ALIASES = {
    "gs", "gwmi", "gci", "ls", "dir", "cat", "gc", "cd", "ps", "kill", "sp",
    "ss", "sas", "ri", "rm", "foreach", "%", "?",
}

# 危险 token: 命中即 deny.
_DANGEROUS_TOKENS = {
    "--%": "停止解析符 `__%",
    "`": "反引号转义",
    "+": "字符串拼接动态命令名",
    "{": "脚本块",
    "}": "脚本块",
    "(": "子表达式/动态命令名",
    ")": "子表达式/动态命令名",
    ";": "多命令分隔",
    "|": "管道(可能接入下载执行链)",
    "&&": "多命令分隔",
    "||": "多命令分隔",
    ">": "输出重定向",
    "<": "输入重定向",
    "#": "注释隐藏",
    "$": "变量动态值",
}

_TOKEN_RE = re.compile(
    r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'|--%|-[\w-]+|&&|\|\||'
    r'[&|;(){}\[\]\x60$+><#]|[^\s&|;(){}\[\]\x60$+><#]+'
)
_BARE_CMD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-]*$")


def _result(verdict, reason, node, command=None):
    return {
        "verdict": verdict,
        "reason": reason,
        "matched_node": node,
        "command_name": command,
    }


def tokenize(command):
    """把命令切成保守 token 列表; 引号不闭合或残留不可解析字符返回 None(fail-closed)."""
    if not isinstance(command, str) or not command.strip():
        return None
    if command.count(chr(34)) % 2 != 0 or command.count(chr(39)) % 2 != 0:
        return None
    tokens = _TOKEN_RE.findall(command)
    if not tokens:
        return None
    reconstructed = "".join(tokens)
    stripped = "".join(command.split())
    if reconstructed != stripped:
        return None
    return tokens


def validate(command):
    """对单条 PowerShell 命令做三态判定. 返回 verdict/reason/matched_node/command_name."""
    tokens = tokenize(command)
    if tokens is None:
        return _result(DENY, "解析失败或语法错误(fail-closed)", command)

    for tok in tokens:
        if tok in _DANGEROUS_TOKENS:
            return _result(DENY, "危险结构: " + _DANGEROUS_TOKENS[tok], tok)
        if "`" in tok:
            return _result(DENY, "危险结构: 反引号转义", tok)
        if tok.startswith("$"):
            return _result(DENY, "危险结构: 变量动态值/动态命令名", tok)
        if tok.startswith("-") and tok.lower() in ("-enc", "-encodedcommand", "-e", "-encodedarguments"):
            return _result(DENY, "危险结构: EncodedCommand 编码命令", tok)
        if tok.startswith("/") and tok.lower() != "/all":
            return _result(DENY, "原生命令参数白名单外: " + tok, tok)

    first = tokens[0]
    if not _BARE_CMD_RE.match(first):
        return _result(DENY, "动态命令名或非静态命令名(fail-closed)", first)
    name = first.lower()

    if name in FORBIDDEN_CMDS:
        return _result(DENY, "禁止清单命令(确认门不得覆盖)", first, first)
    if name in DYNAMIC_EXEC_CMDS:
        return _result(DENY, "危险命令: 动态执行/下载执行链/别名操纵", first, first)
    if name in _KNOWN_ALIASES:
        return _result(DENY, "别名命令(Alias 覆盖风险)", first, first)

    entry = _WHITELIST.get(name)
    if entry is None:
        return _result(DENY, "白名单外命令, 默认拒绝", first, first)
    tier, allowed_params = entry

    # 参数必须带值（fail-closed）：缺值的参数在 PowerShell 里会被解析为 $null，
    # 对修改类命令尤其危险。逐个 -param 检查其后是否紧跟一个值 token。
    tail = tokens[1:]
    i = 0
    while i < len(tail):
        tok = tail[i]
        if tok.startswith("-"):
            pname = tok[1:].lower()
            if pname not in allowed_params:
                return _result(DENY, "参数缩写/白名单外参数: " + tok, tok, first)
            if i + 1 >= len(tail) or tail[i + 1].startswith("-"):
                return _result(DENY, "参数缺少值(fail-closed): " + tok, tok, first)
            i += 2  # 跳过参数及其值
        else:
            i += 1
    return _result(tier, "白名单命中: %s (tier=%s)" % (first, tier), first, first)


if __name__ == "__main__":
    import json
    for c in ["Get-Service -Name Spooler",
              "Set-Service -Name Spooler -Status Running",
              "Set-Service -Name Spooler -Stat Running",
              "& $n -Name Spooler"]:
        print(json.dumps(validate(c), ensure_ascii=False))
