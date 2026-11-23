"""OpsGuard 正式版 - 真实系统适配器 Python 薄封装 - 纯标准库.

调用 src/adapters/system_adapter.psm1 的参数化适配器:
- 生产模式(sandbox=False): 运行时可真改 DNS/服务/注册表/文件(经确认门).
- 沙箱模式(sandbox=True, 默认): 目标重定向到夹具, 构建/测试不碰真系统.

PS runner 可注入(_PS_RUNNER), 便于用 mock 测试而不真的拉起 PowerShell.
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PSM1 = os.path.join(HERE, "system_adapter.psm1")

KINDS = ("dns", "service", "registry", "file")


class AdapterError(Exception):
    pass


def _default_runner(script):
    """默认 PS runner: 起一个 powershell 进程执行 script, 取最后一行 JSON."""
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise AdapterError("PowerShell 启动失败: %s" % e)
    if p.returncode != 0:
        raise AdapterError("PowerShell 失败: %s" % (p.stderr or "")[:200])
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return None
    # 从后往前找第一个可解析 JSON 行
    for ln in reversed(lines):
        try:
            return json.loads(ln)
        except ValueError:
            continue
    raise AdapterError("PowerShell 输出无 JSON: %s" % (p.stdout or "")[:200])


_PS_RUNNER = None


def set_runner(fn):
    """注入 PS runner(测试用). fn(script)->dict 或 None."""
    global _PS_RUNNER
    _PS_RUNNER = fn


def reset_runner():
    global _PS_RUNNER
    _PS_RUNNER = None


def _run(script):
    return (_PS_RUNNER or _default_runner)(script)


def _ps_quote(s):
    """PowerShell 单引号字面量: 内部单引号翻倍."""
    return "'" + str(s).replace("'", "''") + "'"


def _ps_hashtable(values):
    parts = []
    for k, v in values.items():
        parts.append(_ps_quote(k) + "=" + _ps_quote(v))
    return "@{" + ";".join(parts) + "}"


def _load_module():
    return "Import-Module " + _ps_quote(PSM1) + " -Force -Global;"


def change(kind, target, values, confirm_answer=None, sandbox=True,
           sandbox_root=None, label=None, ast_verdict="require_confirm"):
    """执行受控变更. 返回 dict(ok/stage/diff/before_hash/after_hash/manifest).

    生产调用务必: ast_verdict 由 c2.ast_guard 判定后传入; confirm_answer 必须人工显式 y.
    沙箱为默认值, 构建/测试永不碰真系统.
    """
    if kind not in KINDS:
        raise AdapterError("未知目标类型: %s" % kind)
    sb = " -Sandbox" if sandbox else ""
    root = (" -SandboxRoot " + _ps_quote(sandbox_root)) if sandbox_root else ""
    lbl = (" -Label " + _ps_quote(label)) if label else ""
    script = (_load_module() +
              "$r = Invoke-OGChange -Kind %s -Target %s -Values %s -ConfirmAnswer %s%s%s%s -AstVerdict %s;" %
              (_ps_quote(kind), _ps_quote(target), _ps_hashtable(values),
               _ps_quote(confirm_answer or ""), sb, root, lbl, _ps_quote(ast_verdict)) +
              "$r | ConvertTo-Json -Depth 10 -Compress")
    return _run(script)


def rollback(manifest, sandbox=True, sandbox_root=None):
    """按 manifest 回滚 + 三方哈希验证. 失败时 PS 侧自动冻结.

    manifest JSON 用 base64 传入 PS, 避免裸 JSON 的冒号/引号被 PS 当 scriptblock 解析.
    """
    import base64
    sb = " -Sandbox" if sandbox else ""
    root = (" -SandboxRoot " + _ps_quote(sandbox_root)) if sandbox_root else ""
    mjson = json.dumps(manifest, ensure_ascii=False)
    b64 = base64.b64encode(mjson.encode("utf-8")).decode("ascii")
    script = (_load_module() +
              "$j = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'));" % b64 +
              "$m = $j | ConvertFrom-Json;" +
              "$r = Invoke-OGRollback -Manifest $m%s%s;" % (sb, root) +
              "$r | ConvertTo-Json -Depth 10 -Compress")
    return _run(script)


def snapshot(kind, target, sandbox=True, sandbox_root=None):
    sb = " -Sandbox" if sandbox else ""
    root = (" -SandboxRoot " + _ps_quote(sandbox_root)) if sandbox_root else ""
    script = (_load_module() +
              "$s = Get-OGSnapshot -Kind %s -Target %s%s%s;" % (_ps_quote(kind), _ps_quote(target), sb, root) +
              "$h = Get-OGHash -Snap $s;" +
              "[pscustomobject]@{exists=$s.exists; kind=$s.kind; target=$s.target; hash=$h; simulated=$s.mapping.simulated} | ConvertTo-Json -Compress")
    return _run(script)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        print(json.dumps(snapshot(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        print("usage: system.py <kind> <target>")
