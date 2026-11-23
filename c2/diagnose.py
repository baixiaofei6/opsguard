"""OpsGuard C2 - 诊断引擎（三场景共用内核第一步）-- Python 3.8+ 纯标准库.

职责: 证据包(只读采集结果文本 / 粘贴报错文本) + 场景类型 -> 结构化结论 + 风险排序.
不做: 生成命令、判定安全、执行任何命令.
语料: 内置规则表, 关键词/异常类型映射(模拟 WinDeploy-Kit 故障场景 + lan-ops-scan 巡检异常).
"""
import re

SCENARIO_ERROR = "error"            # 报错排障
SCENARIO_INSPECTION = "inspection"  # 巡检报告解读
SCENARIO_FIX = "fix"                # 带回滚修复
VALID_SCENARIOS = (SCENARIO_ERROR, SCENARIO_INSPECTION, SCENARIO_FIX)

RULES = [
    {
        "id": "DNS_UNREACHABLE",
        "title": "DNS 服务器被指向不可达地址",
        "keywords": ["dns", "dns服务器", "dns 服务器", "unreachable", "不可达",
                     "serveraddresses", "名称解析", "name resolution", "169.254"],
        "explanation": "证据显示 DNS 服务器地址无法解析域名, 属于配置错误而非缓存问题, 需修正 DNS 服务器地址.",
        "risk": "high",
        "intent": "mutating",
        "target": {"interface_index": "12", "bad_dns": "203.0.113.254", "good_dns": "192.168.1.1"},
    },
    {
        "id": "SERVICE_STOPPED",
        "title": "关键服务处于停止状态",
        "keywords": ["service", "服务", "stopped", "已停止", "spooler", "not running"],
        "explanation": "证据显示目标服务未运行, 影响依赖该服务的功能, 需将服务状态恢复为 Running.",
        "risk": "medium",
        "intent": "mutating",
        "target": {"service_name": "Spooler"},
    },
    {
        "id": "ADAPTER_DISABLED",
        "title": "网络适配器被禁用或链路断开",
        "keywords": ["adapter", "网卡", "适配器", "disabled", "已禁用", "media disconnected", "媒体已断开"],
        "explanation": "证据显示网络适配器状态异常, 先用只读命令确认适配器状态, 再决定后续动作.",
        "risk": "medium",
        "intent": "readonly",
        "target": {"adapter_name": "Ethernet"},
    },
    {
        "id": "EVENTLOG_ERROR",
        "title": "系统事件日志存在错误事件",
        "keywords": ["event id", "事件 id", "winevent", "错误事件", "error event", "事件日志"],
        "explanation": "证据包含事件日志错误, 用只读命令拉取近期错误事件定位根因.",
        "risk": "low",
        "intent": "readonly",
        "target": {"log_name": "System", "max_events": "20"},
    },
]

_SCENARIO_DEFAULT_INTENT = {
    SCENARIO_ERROR: "readonly",
    SCENARIO_INSPECTION: "readonly",
    SCENARIO_FIX: "mutating",
}

_SAMPLES = {
    SCENARIO_ERROR:
        "PS C:\\> Get-DnsClientServerAddress -InterfaceIndex 12\n"
        "InterfaceIndex  AddressFamily  ServerAddresses\n"
        "12              IPv4           {203.0.113.254}\n"
        "错误: DNS 服务器不可达, 域名解析失败 (name resolution error), 请检查 DNS 配置.",
    SCENARIO_INSPECTION:
        "=== lan-ops-scan 巡检异常 ===\n"
        "网卡 Ethernet 状态: Media disconnected / 媒体已断开\n"
        "服务 Spooler 状态: Stopped / 已停止\n"
        "系统日志发现 Event ID 7000 错误事件.",
    SCENARIO_FIX:
        "=== 故障场景 (WinDeploy-Kit) ===\n"
        "自检采集: DNS 服务器 {203.0.113.254} 不可达 (unreachable)\n"
        "建议修正 InterfaceIndex 12 的 ServerAddresses 为可用地址.",
}

_RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def sample_evidence(scenario):
    return _SAMPLES.get(scenario, _SAMPLES[SCENARIO_ERROR])


def _snippet(evidence, keyword, width=60):
    idx = evidence.lower().find(keyword.lower())
    if idx < 0:
        return evidence[:width]
    start = max(0, idx - 20)
    return evidence[start:start + width].replace("\n", " ").strip()


def diagnose(evidence, scenario=SCENARIO_ERROR):
    """把证据文本归一为结构化结论 + 风险排序. 纯文本匹配, 零副作用."""
    if scenario not in VALID_SCENARIOS:
        scenario = SCENARIO_ERROR
    text = evidence or ""
    lowered = text.lower()
    findings = []
    for rule in RULES:
        hit = None
        for kw in rule["keywords"]:
            if kw.lower() in lowered:
                hit = kw
                break
        if hit is None:
            continue
        findings.append({
            "id": rule["id"],
            "title": rule["title"],
            "explanation": rule["explanation"],
            "risk": rule["risk"],
            "intent": rule["intent"],
            "keywords_hit": hit,
            "evidence_snippet": _snippet(text, hit),
            "target": dict(rule["target"]),
        })
    findings.sort(key=lambda f: _RISK_ORDER.get(f["risk"], 9))
    if findings:
        top = findings[0]
        summary = "识别 %d 项异常; 首要风险: %s(%s)." % (len(findings), top["title"], top["risk"])
    else:
        summary = "证据中未命中已知异常规则, 建议补充只读采集信息."
    return {
        "scenario": scenario,
        "summary": summary,
        "default_intent": _SCENARIO_DEFAULT_INTENT[scenario],
        "findings": findings,
        "risks_sorted": findings,
    }


if __name__ == "__main__":
    import json
    for sc in VALID_SCENARIOS:
        print(json.dumps(diagnose(sample_evidence(sc), sc), ensure_ascii=False, indent=2))
