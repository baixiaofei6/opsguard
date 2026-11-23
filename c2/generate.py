"""OpsGuard C2 - 命令生成（三场景共用内核第二步）-- Python 3.8+ 纯标准库.

职责: 诊断结论 + 意图(readonly/mutating) -> 候选命令文本 + 预期效果 + 一句人话 + diff.
不做: 判定安全(交给 AST 校验器)、不执行(命令仅作为字符串与 AST 分析输入).
生成的每条命令都使用白名单中的完整参数名, 保证能被白名单完整解析.
"""
import diagnose as diag

_TEMPLATES = {
    "DNS_UNREACHABLE": {
        "readonly": "Get-DnsClientServerAddress -InterfaceIndex {interface_index}",
        "mutating": "Set-DnsClientServerAddress -InterfaceIndex {interface_index} -ServerAddresses {good_dns}",
    },
    "SERVICE_STOPPED": {
        "readonly": "Get-Service -Name {service_name}",
        "mutating": "Set-Service -Name {service_name} -Status Running",
    },
    "ADAPTER_DISABLED": {
        "readonly": "Get-NetAdapter -Name {adapter_name}",
        "mutating": "Get-NetAdapter -Name {adapter_name}",
    },
    "EVENTLOG_ERROR": {
        "readonly": "Get-WinEvent -LogName {log_name} -MaxEvents {max_events}",
        "mutating": "Get-WinEvent -LogName {log_name} -MaxEvents {max_events}",
    },
}

_PLAIN = {
    ("DNS_UNREACHABLE", "readonly"): "只读查看接口 {interface_index} 当前 DNS 配置.",
    ("DNS_UNREACHABLE", "mutating"): "将把接口 {interface_index} 的 DNS 从 {bad_dns} 改为 {good_dns}.",
    ("SERVICE_STOPPED", "readonly"): "只读确认服务 {service_name} 的当前状态.",
    ("SERVICE_STOPPED", "mutating"): "将把服务 {service_name} 从 Stopped 恢复为 Running.",
    ("ADAPTER_DISABLED", "readonly"): "只读查看网卡 {adapter_name} 的状态.",
    ("EVENTLOG_ERROR", "readonly"): "只读拉取 {log_name} 日志最近 {max_events} 条错误事件.",
}

_EXPECT = {
    "readonly": "只读采集当前态, 不修改系统状态; 输出用于 diff 的 before 快照.",
    "mutating": "修改目标项状态; 需经 AST require_confirm + 人工确认 + 备份后才可在 C3 执行.",
}


def _fill(fmt, target):
    try:
        return fmt.format(**target)
    except (KeyError, ValueError):
        return fmt


def _diff(finding, intent, target):
    fid = finding["id"]
    if fid == "DNS_UNREACHABLE" and intent == "mutating":
        before = "DNS Servers: %s (不可达)" % target.get("bad_dns", "?")
        after = "DNS Servers: %s (可用)" % target.get("good_dns", "?")
    elif fid == "SERVICE_STOPPED" and intent == "mutating":
        before = "Service %s: Stopped" % target.get("service_name", "?")
        after = "Service %s: Running" % target.get("service_name", "?")
    else:
        before = "(当前态由只读采集填充, C3 执行前生成)"
        after = "(无预期变更; 只读)"
    unified = "--- 当前\n+++ 预期\n-%s\n+%s" % (before, after)
    return {"before": before, "after": after, "unified": unified}


def generate(diagnosis, intent_override=None):
    """依据诊断结论生成候选命令方案列表(不执行)."""
    proposals = []
    for finding in diagnosis.get("findings", []):
        fid = finding["id"]
        intent = intent_override or diagnosis.get("default_intent") or finding.get("intent", "readonly")
        tpl = _TEMPLATES.get(fid, {}).get(intent) or _TEMPLATES.get(fid, {}).get("readonly")
        if tpl is None:
            continue
        target = dict(finding.get("target", {}))
        command = _fill(tpl, target)
        plain = _PLAIN.get((fid, intent), "将执行: %s" % command)
        plain = _fill(plain, target)
        proposals.append({
            "finding_id": fid,
            "title": finding["title"],
            "risk": finding["risk"],
            "intent": intent,
            "command": command,
            "expected_effect": _EXPECT.get(intent, _EXPECT["readonly"]),
            "plain_english": plain,
            "diff": _diff(finding, intent, target),
            "backup_hint": "[备份] C3 执行前将备份受影响项; C2 仅展示方案, 不备份不执行.",
        })
    return proposals


if __name__ == "__main__":
    import json
    for sc in diag.VALID_SCENARIOS:
        d = diag.diagnose(diag.sample_evidence(sc), sc)
        print(json.dumps(generate(d), ensure_ascii=False, indent=2))
