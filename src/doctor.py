"""OpsGuard 正式版 - 环境自检 doctor - Python 3.8+ 纯标准库.

查: Python/PS 版本、Pester 版本、云端 Key 是否配、写权限、有效后端.
只读, 不改系统; Key 只报"已配/未配", 绝不显示值.
本地模型后端已按用户 2026-11-23 决定彻底移除。
"""
import os
import platform
import subprocess
import sys

import config as _config
import keystore as _keystore
import backends.factory as factory

OK = "OK"
WARN = "WARN"
MISS = "MISS"


def _row(name, state, detail=""):
    return {"name": name, "state": state, "detail": detail}


def _run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as e:
        return -1, "", str(e)[:100]


def check(cfg=None):
    cfg = cfg or _config.load()
    rows = []
    # Python
    v = sys.version_info
    rows.append(_row("python", OK if (v.major == 3 and v.minor >= 8) else MISS,
                     "%d.%d.%d" % (v.major, v.minor, v.micro)))
    # PowerShell 5.1
    code, out, err = _run(["powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"])
    rows.append(_row("powershell", OK if code == 0 and out else WARN,
                     out if code == 0 else ("unavailable: " + err[:60])))
    # Pester 3.4 (目标机实测版本)
    code, out, err = _run(["powershell", "-NoProfile", "-Command",
                           "(Get-Module -ListAvailable Pester | Select-Object -First 1).Version.ToString()"])
    rows.append(_row("pester", OK if code == 0 and out else WARN,
                     ("v" + out) if out else "not installed (tests need Pester 3.4)"))
    # 云端 Key（含软件内 keystore; 只报来源/模型, 绝不显示明文）
    resolved = _keystore.resolve(cfg)
    has_key = bool(resolved["key"])
    rows.append(_row("cloud_key", OK if has_key else WARN,
                     ("configured via %s" % resolved["source"]) if has_key
                     else "not set -> cloud mode unavailable (用 key add 添加)"))
    rows.append(_row("cloud_model", OK if has_key else WARN,
                     (resolved["model"] + " @ " + resolved["api_base"]) if has_key
                     else "未选模型 (用 model use 选择)"))
    # 写权限(opsguard 根)
    root = _config.root_dir()
    try:
        probe = os.path.join(root, ".doctor-write-probe")
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        rows.append(_row("write_permission", OK, root))
    except OSError as e:
        rows.append(_row("write_permission", MISS, str(e)[:80]))
    # 有效后端 + 人话解释
    st = factory.status(cfg)
    rows.append(_row("effective_backend", OK, st["effective"]))
    rows.append(_row("backend_detail", OK, st.get("effective_detail", st["effective"])))
    # P2: 证据链自检(从环境自检升级)
    root = _config.root_dir()
    # 脱敏映射表目录可写(用 opsguard 根下临时文件验证)
    try:
        probe = os.path.join(root, ".redact-map-probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("{}")
        os.remove(probe)
        rows.append(_row("redact_map_writable", OK, "mapping stays local (never transmitted)"))
    except OSError as e:
        rows.append(_row("redact_map_writable", MISS, str(e)[:80]))
    # 黄金测试集存在且可跑(检查关键测试文件)
    golden = [
        os.path.join(root, "c1", "test_redact.py"),
        os.path.join(root, "c2", "test_c2.py"),
        os.path.join(root, "c3", "Golden.Tests.ps1"),
        os.path.join(root, "adversarial-verify.py"),
    ]
    present = sum(1 for p in golden if os.path.isfile(p))
    rows.append(_row("golden_tests", OK if present == len(golden) else WARN,
                     "%d/%d suites present; run 'opsguard selftest'" % (present, len(golden))))
    return rows


def render(rows):
    return "\n".join("[%s] %-18s %s" % (r["state"], r["name"], r["detail"]) for r in rows)


if __name__ == "__main__":
    print(render(check()))
