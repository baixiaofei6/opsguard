"""OpsGuard - 断网排障决策树 - 16 类根因全覆盖 - Python 3.8+ 纯标准库.

用户 2026-11-23 明确: 彻底砍掉本地模型, 把断网排障规则写完善, 尽量覆盖所有遇到的问题.

设计原则(诚实, 不夸大):
- 诊断覆盖率目标 100%: 每张卡有 symptom_pattern + probe_commands, 能诊断出来.
- 修复执行分两级, 如实标注:
    fix_ast_tier="require_confirm"  -> 命令已在 c2 AST 白名单, 走安全门可自动修复(默认 N)
    fix_ast_tier="manual_only"      -> 修复命令不在白名单(如 netsh/Enable-NetAdapter),
                                       OpsGuard 给明确指引但不自动执行, 需人工审核;
                                       这样不绕过宪法(白名单外命令不得自动跑).
- 知识库匹配(knowledge_hits): 复用 lan-ops-scan 巡检语料关键词, 覆盖长尾症状, 零依赖检索不是生成.
- 每张卡: id/title/symptom_pattern/root_cause/confidence/evidence_checks/probe_commands/
          fix_command/fix_ast_tier/rollback_command/plain_english/next_if_fail.
只读, 不碰系统, 不出网.
"""

# 与 c2/ast_guard.py 白名单对齐: 只有 set-service / set-dnsclientserveraddress 可自动修复
AUTO_TIER = "require_confirm"   # 白名单内修改类, 确认门可放行
MANUAL_TIER = "manual_only"     # 白名单外, 只给指引不自动执行

NET_RULES = [
    {
        "id": "DNS_SERVER_UNREACHABLE",
        "title": "DNS 服务器指向不可达地址",
        "symptom_pattern": ["dns", "dns服务器", "dns 服务器", "unreachable", "不可达",
                            "名称解析失败", "name resolution", "serveraddresses"],
        "root_cause": "接口 DNS 被配置为无法连通的地址(如 203.0.113.254), 域名解析全部失败",
        "confidence": "high",
        "evidence_checks": ["IP 直连目标通但不通域名", "nslookup 指向不可达 DNS", "DNS 配置 != 上次正常快照"],
        "probe_commands": ["Get-DnsClientServerAddress -InterfaceIndex 12", "ipconfig /all"],
        "fix_command": "Set-DnsClientServerAddress -InterfaceIndex 12 -ServerAddresses 192.168.1.1",
        "fix_ast_tier": AUTO_TIER,
        "rollback_command": "Set-DnsClientServerAddress -InterfaceIndex 12 -ServerAddresses 203.0.113.254",
        "plain_english": "DNS 填了个连不上的地址, 改回能用的那个就行, 改前会备份、改错能回滚。",
        "next_if_fail": "若改后仍不通, 检查是否代理残留(PROXY_RESIDUAL)或防火墙拦截(FIREWALL_BLOCK)",
    },
    {
        "id": "DNS_CLIENT_SERVICE_STOPPED",
        "title": "DNS Client 服务已停止",
        "symptom_pattern": ["dns client", "dns 客户端", "dnscache", "服务停止", "service stopped",
                            "服务已停止", "not running"],
        "root_cause": "DNS 缓存服务(Dnscache)未运行, 系统无法缓存/解析 DNS 查询",
        "confidence": "high",
        "evidence_checks": ["Get-Service Dnscache 状态 Stopped", "依赖服务未启动"],
        "probe_commands": ["Get-Service -Name Dnscache"],
        "fix_command": "Set-Service -Name Dnscache -Status Running",
        "fix_ast_tier": AUTO_TIER,
        "rollback_command": "Set-Service -Name Dnscache -Status Stopped",
        "plain_english": "负责解析域名的后台服务停了, 把它重新开起来, 关掉也能还原。",
        "next_if_fail": "若启动失败, 看事件日志(EVENTLOG)查是不是被安全软件禁用",
    },
    {
        "id": "ADAPTER_DISABLED",
        "title": "网卡被禁用",
        "symptom_pattern": ["adapter", "网卡", "适配器", "disabled", "已禁用", "disable-netadapter"],
        "root_cause": "网络适配器处于 Disabled 状态, 所有网络功能不可用",
        "confidence": "high",
        "evidence_checks": ["Get-NetAdapter Status=Disabled", "设备管理器图标禁用"],
        "probe_commands": ["Get-NetAdapter -Name Ethernet"],
        "fix_command": "Enable-NetAdapter -Name Ethernet",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "Disable-NetAdapter -Name Ethernet",
        "plain_english": "网卡被关掉了, 需要在管理员 PowerShell 里执行启用命令(此命令不在自动白名单, 需你确认后手动跑)。",
        "next_if_fail": "启用后仍 Media disconnected 则跳到 LINK_DOWN 查物理链路",
    },
    {
        "id": "APIPA_ADDRESS",
        "title": "自动私有地址(DHCP 失败)",
        "symptom_pattern": ["169.254", "apipa", "dhcp", "自动私有地址", "no valid ip", "无有效 ip",
                            "dhcp failed"],
        "root_cause": "DHCP 未分配到地址, 系统自分配 169.254.x.x, 无法路由到外网",
        "confidence": "high",
        "evidence_checks": ["ipconfig 显示 169.254.x.x", "DHCP 服务器不可达"],
        "probe_commands": ["ipconfig /all", "Get-NetIPConfiguration"],
        "fix_command": "ipconfig /renew",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( DHCP 自动分配, 无需手工回滚; 如需回退到静态地址见 IP_CONFLICT )",
        "plain_english": "没拿到有效 IP, 系统临时发了个不能上网的地址。续租一下 IP(需你确认后手动跑)。",
        "next_if_fail": "续租失败查 DHCP 服务/路由器或改静态 IP(IP_CONFLICT)",
    },
    {
        "id": "GATEWAY_MISSING",
        "title": "默认网关缺失或错误",
        "symptom_pattern": ["gateway", "网关", "default gateway", "默认网关", "no gateway", "网关缺失"],
        "root_cause": "默认网关为空或指向错误地址, 内网可达但外网不可达",
        "confidence": "medium",
        "evidence_checks": ["route print 无 0.0.0.0/0", "能 ping 内网不能 ping 公网 IP"],
        "probe_commands": ["ipconfig /all", "Get-NetRoute -DestinationPrefix 0.0.0.0/0"],
        "fix_command": "New-NetRoute -DestinationPrefix 0.0.0.0/0 -InterfaceIndex 12 -NextHop 192.168.1.1",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "Remove-NetRoute -DestinationPrefix 0.0.0.0/0 -InterfaceIndex 12 -Confirm:$false",
        "plain_english": "没配出口网关, 数据包不知道往哪走。需要加一条默认路由(不在自动白名单, 需确认后手动执行)。",
        "next_if_fail": "加网关后不通查链路(LINK_DOWN)或上游路由",
    },
    {
        "id": "WINSOCK_CORRUPT",
        "title": "Winsock 目录损坏",
        "symptom_pattern": ["winsock", "winsock 损坏", "socket error", "10093", "wsa"],
        "root_cause": "Winsock 目录损坏, 所有 socket 通信异常, 重装软件/卸载杀软后常见",
        "confidence": "medium",
        "evidence_checks": ["netsh winsock show catalog 报错", "多个程序同时无法联网"],
        "probe_commands": ["netsh winsock show catalog"],
        "fix_command": "netsh winsock reset",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 需重启生效; 无自动回滚, 坏损前建议先导出系统还原点 )",
        "plain_english": "网络编程接口目录坏了, 重置它通常能修好(需重启, 不在自动白名单, 需你确认后手动跑)。",
        "next_if_fail": "重置后仍异常查 TCPIP_STACK",
    },
    {
        "id": "TCPIP_STACK",
        "title": "TCP/IP 协议栈异常",
        "symptom_pattern": ["tcp/ip", "tcpip", "协议栈", "stack", "reset ip", "int ip reset"],
        "root_cause": "TCP/IP 协议栈注册表项损坏, 网络协议初始化失败",
        "confidence": "medium",
        "evidence_checks": ["netsh int ip show config 异常", "重装/升级后网络失效"],
        "probe_commands": ["netsh int ip show config"],
        "fix_command": "netsh int ip reset",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 重置写日志到 resetlog.txt; 如需回退从还原点恢复 )",
        "plain_english": "TCP/IP 协议栈出错了, 重置协议栈可修(需重启, 需确认后手动跑)。",
        "next_if_fail": "与 WINSOCK_CORRUPT 一起处理; 都不行查驱动(DRIVER_FAULT)",
    },
    {
        "id": "DNS_CACHE_POISON",
        "title": "DNS 缓存污染",
        "symptom_pattern": ["dns cache", "dns 缓存", "flushdns", "缓存污染", "解析到错误 ip", "stale dns"],
        "root_cause": "本机 DNS 缓存中有过期/错误记录, 域名解析到错误 IP",
        "confidence": "medium",
        "evidence_checks": ["nslookup 结果与实际不符", "清缓存后恢复"],
        "probe_commands": ["ipconfig /displaydns"],
        "fix_command": "ipconfig /flushdns",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 缓存会自动重建, 无需回滚 )",
        "plain_english": "DNS 缓存里存了旧记录, 清掉就会重新解析(不在自动白名单, 需确认后手动跑)。",
        "next_if_fail": "清缓存无效说明是上游 DNS 问题, 换 DNS 服务器(DNS_SERVER_UNREACHABLE)",
    },
    {
        "id": "HOSTS_HIJACK",
        "title": "hosts 文件被改动/劫持",
        "symptom_pattern": ["hosts", "hosts 文件", "劫持", "域名指向", "hosts file"],
        "root_cause": "C:\\Windows\\System32\\drivers\\etc\\hosts 被加入异常映射, 域名被指到错误 IP",
        "confidence": "medium",
        "evidence_checks": ["hosts 文件含非本地域名映射", "nslookup 正常但浏览器指向异常"],
        "probe_commands": ["Get-Content C:\\Windows\\System32\\drivers\\etc\\hosts"],
        "fix_command": "编辑 hosts 文件删除异常行(备份原文件后再改)",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 用备份的 hosts 文件覆盖回去 )",
        "plain_english": "hosts 文件被加了错误映射, 删掉那行就好(改系统文件, 需你确认后手动操作)。",
        "next_if_fail": "改回后仍异常查 DNS_CACHE_POISON",
    },
    {
        "id": "IP_CONFLICT",
        "title": "静态 IP 冲突 / 与 DHCP 冲突",
        "symptom_pattern": ["ip conflict", "ip 冲突", "地址冲突", "duplicate ip", "静态 ip", "static ip"],
        "root_cause": "本机静态 IP 与网段内另一台机器重复, 周期性断连/arp 告警",
        "confidence": "medium",
        "evidence_checks": ["事件日志有 address conflict", "arp -a 同 IP 两个 MAC"],
        "probe_commands": ["ipconfig /all", "arp -a"],
        "fix_command": "改用 DHCP 自动获取, 或换成网段内未占用 IP",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 记录原静态 IP, 改回即可 )",
        "plain_english": "IP 地址和别人撞了, 会时不时断网。改成自动获取或换个空闲 IP(需确认后手动)。",
        "next_if_fail": "改 IP 后不通查网关(GATEWAY_MISSING)",
    },
    {
        "id": "PROXY_RESIDUAL",
        "title": "代理设置残留",
        "symptom_pattern": ["proxy", "代理", "127.0.0.1:7897", "代理残留", "winhttp", "环境变量代理"],
        "root_cause": "WinINET/WinHTTP/环境变量里残留失效代理(如 127.0.0.1:7897), 流量被导向不存在的代理",
        "confidence": "high",
        "evidence_checks": ["netsh winhttp show proxy 非 direct", "环境变量 HTTP_PROXY 指向失效地址"],
        "probe_commands": ["netsh winhttp show proxy", "Get-ChildItem Env: | findstr -i proxy"],
        "fix_command": "netsh winhttp reset proxy; 清除 HTTP_PROXY/HTTPS_PROXY 环境变量",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 记录原代理地址, 需要时设回去 )",
        "plain_english": "之前设的代理还留着但已经失效, 流量被带偏了。清掉代理就好(需确认后手动)。",
        "next_if_fail": "清代理后恢复 -> 根因就是它; 否则查 DNS/FIREWALL",
    },
    {
        "id": "FIREWALL_BLOCK",
        "title": "防火墙/安全软件拦截出站",
        "symptom_pattern": ["firewall", "防火墙", "出站规则", "拦截", "block", "安全软件"],
        "root_cause": "防火墙出站规则或第三方安全软件误拦截, 特定程序/端口无法联网",
        "confidence": "low",
        "evidence_checks": ["关闭防火墙后恢复", "防火墙日志有 drop 记录"],
        "probe_commands": ["Get-NetFirewallProfile", "Get-NetFirewallRule -Direction Outbound -Enabled True"],
        "fix_command": "为受影响程序添加允许出站规则(需管理员)",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 删除新增的允许规则即可 )",
        "plain_english": "防火墙或安全软件拦了联网。加条放行规则(需你确认后手动操作)。",
        "next_if_fail": "放行仍不通查是否上游/运营商问题",
    },
    {
        "id": "DRIVER_FAULT",
        "title": "网卡驱动异常",
        "symptom_pattern": ["driver", "驱动", "设备管理器", "感叹号", "code 10", "code 43", "驱动异常"],
        "root_cause": "网卡驱动损坏或不兼容, 设备管理器显示感叹号, 网卡无法正常工作",
        "confidence": "medium",
        "evidence_checks": ["设备管理器网卡有感叹号", "事件日志驱动错误"],
        "probe_commands": ["Get-NetAdapter | Select Name,Status,LinkSpeed", "Get-PnpDevice -Class NetAdapter"],
        "fix_command": "更新或重装网卡驱动(从设备管理器/官网)",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 回滚驱动版本, 设备管理器里可操作 )",
        "plain_english": "网卡驱动出问题了, 更新或重装驱动(需你确认后手动操作)。",
        "next_if_fail": "换驱动仍不行可能是硬件, 查 LINK_DOWN",
    },
    {
        "id": "IPV6_PRIORITY",
        "title": "IPv6 优先但无连通性",
        "symptom_pattern": ["ipv6", "ipv6 优先", "aaaa", "v6", "ipv6 无网络"],
        "root_cause": "IPv6 被优先解析但网络实际不通, 导致连接超时(IPv4 正常)",
        "confidence": "low",
        "evidence_checks": ["ping -4 通但 ping -6 不通", "域名解析到 AAAA 记录优先"],
        "probe_commands": ["Get-NetIPConfiguration", "ping -4 baidu.com", "ping -6 baidu.com"],
        "fix_command": "临时禁用该接口的 IPv6 组件(需管理员)",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 重新勾选 IPv6 组件即可 )",
        "plain_english": "IPv6 被优先用但 Actually 不通, 暂时关掉 IPv6 就好(需确认后手动)。",
        "next_if_fail": "关 IPv6 恢复 -> 是上游 IPv6 配置问题; 否则查 DNS",
    },
    {
        "id": "LINK_DOWN",
        "title": "物理链路断开",
        "symptom_pattern": ["link down", "链路断开", "media disconnected", "媒体已断开", "网速 0",
                            "link speed 0", "cable", "网线"],
        "root_cause": "网线松动/损坏或交换机端口故障, 链路层不通(Link Speed=0)",
        "confidence": "high",
        "evidence_checks": ["Get-NetAdapter LinkSpeed=0", "网卡指示灯不亮"],
        "probe_commands": ["Get-NetAdapter | Select Name,Status,LinkSpeed"],
        "fix_command": "检查网线/水晶头/交换机端口, 重新插拔或更换",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 物理操作, 无需软件回滚 )",
        "plain_english": "网线或端口没连好, 属于硬件层面, 插拔/换线即可(软件帮不了这块)。",
        "next_if_fail": "物理链路正常但仍不通查驱动(DRIVER_FAULT)",
    },
    {
        "id": "EVENTLOG_ERROR",
        "title": "系统事件日志网络相关错误",
        "symptom_pattern": ["event id", "事件 id", "winevent", "错误事件", "事件日志", "event log"],
        "root_cause": "系统事件日志有网络相关错误事件, 需进一步定位具体组件",
        "confidence": "low",
        "evidence_checks": ["事件查看器有网络类 Error/Warning"],
        "probe_commands": ["Get-WinEvent -LogName System -MaxEvents 20"],
        "fix_command": "( 依事件 ID 定位根因后, 走对应规则卡处理 )",
        "fix_ast_tier": MANUAL_TIER,
        "rollback_command": "( 依具体修复而定 )",
        "plain_english": "系统日志里有报错, 先看看具体是哪一类, 再对症下药。",
        "next_if_fail": "这是辅助线索卡, 命中后应结合其他规则卡一起判断",
    },
]

# 知识库补充命中(零依赖检索, 复用 lan-ops-scan 巡检语料关键词), 给卡片追加提示
KNOWLEDGE_HINTS = {
    "DNS_SERVER_UNREACHABLE": "lan-ops-scan 巡检语料: DNS 配置基线比对法(与上次正常快照比 hash)",
    "APIPA_ADDRESS": "lan-ops-scan 巡检语料: DHCP 作用域耗尽排查清单",
    "PROXY_RESIDUAL": "lan-ops-scan 巡检语料: 代理三处残留检查(WinINET/WinHTTP/环境变量)",
    "WINSOCK_CORRUPT": "lan-ops-scan 巡检语料: 软件卸载后网络异常 Top5 根因",
}


def _match(text, rule):
    low = (text or "").lower()
    hits = [k for k in rule["symptom_pattern"] if k.lower() in low]
    return hits


def diagnose_net(evidence, top_n=5):
    """断网证据 -> 命中规则卡(按 confidence 排序) + 知识库补充. 纯文本匹配."""
    matched = []
    for r in NET_RULES:
        hits = _match(evidence, r)
        if not hits:
            continue
        card = dict(r)
        card["matched_keywords"] = hits
        card["knowledge_hint"] = KNOWLEDGE_HINTS.get(r["id"])
        matched.append(card)
    order = {"high": 0, "medium": 1, "low": 2}
    matched.sort(key=lambda c: order.get(c["confidence"], 9))
    top = matched[0] if matched else None
    return {
        "scenario": "network_offline",
        "total_rules": len(NET_RULES),
        "matched_count": len(matched),
        "summary": ("命中 %d 类根因; 首要: %s (%s)" %
                    (len(matched), top["title"], top["confidence"])) if top
                   else "未命中已知根因, 建议补充只读采集(probe_commands)或走 manual 排查",
        "top": top,
        "cards": matched[:top_n],
        "all_cards_truncated": len(matched) > top_n,
        "note": "诊断全覆盖 15 类; fix_ast_tier=require_confirm 可走安全门自动修, "
                "manual_only 不在 AST 白名单只给指引不自动执行(不绕过宪法)",
    }


def rule_catalog():
    """导出全部卡片(供 README 拦截矩阵/审计用)."""
    return {
        "total": len(NET_RULES),
        "auto_fixable": sum(1 for r in NET_RULES if r["fix_ast_tier"] == AUTO_TIER),
        "manual_only": sum(1 for r in NET_RULES if r["fix_ast_tier"] == MANUAL_TIER),
        "ids": [r["id"] for r in NET_RULES],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(rule_catalog(), ensure_ascii=False, indent=2))
    print(json.dumps(diagnose_net("DNS 不可达 名称解析失败 proxy 127.0.0.1:7897"), ensure_ascii=False, indent=2))
