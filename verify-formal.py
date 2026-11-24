# -*- coding: utf-8 -*-
"""OpsGuard 正式版 full acceptance runner.

每轮跑: C1/C2 unittest + 正式版 src/tests(38) + C1/C2/C3 Pester + 2组AST对抗
+ CLI冒烟(doctor/backend/fix未确认/安装器status) + 夹具键 + 真实DNS + 护栏ZERO.
全部用 subprocess 列表传参(shell=False), 避免 bash 展开 $_ 导致 PS ParserError.
用法: python verify-formal.py <轮数> <起始轮号>
"""
import subprocess
import sys
import json
import hashlib
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PS = "powershell"


def run(cmd, cwd=None, timeout=180):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"


def lastline(out):
    ls = [l for l in out.splitlines() if l.strip()]
    return ls[-1].strip() if ls else ""


def check(results, name, ok, detail=""):
    results.append((name, bool(ok), detail))


def pester(script):
    """Pester 3.4: 用 -Quiet + -PassThru 取 PassedCount(不用 -Show, 3.4 不支持)."""
    cmd = [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
           "$r = Invoke-Pester -Script '%s' -PassThru -Quiet; "
           "Write-Output ('PR Passed=' + $r.PassedCount + ' Failed=' + $r.FailedCount + ' Total=' + $r.TotalCount)" % script]
    rc, out = run(cmd)
    m = [l for l in out.splitlines() if "PR " in l]
    return rc, (m[-1] if m else lastline(out))


def one_round(rnd):
    r = []
    # ---- Python unittest: 继承 ----
    rc, out = run([PY, "-m", "unittest", "discover", "-s", os.path.join(BASE, "c1"),
                   "-p", "test_*.py", "-q"])
    check(r, "C1 unittest 14", rc == 0 and "OK" in out, lastline(out))
    rc, out = run([PY, "-m", "unittest", "test_c2", "-q"], cwd=os.path.join(BASE, "c2"))
    check(r, "C2 unittest 15", rc == 0 and "OK" in out, lastline(out))
    # ---- Python unittest: 正式版 src/tests (202 = 195 + 无Key提示 test_ai_chat 4 + CLI 2 + /do 1) ----
    rc, out = run([PY, "-m", "unittest", "discover", "-s", os.path.join(BASE, "src", "tests"),
                   "-p", "test_*.py", "-q"])
    check(r, "Formal unittest 202", rc == 0 and "OK" in out, lastline(out))

    # ---- AI 排障对话：确认模式决策边界（纯内存，不出网不碰系统） ----
    rc, out = run([PY, "-c",
        "import sys;sys.path.insert(0,r'%s');"
        "import ai_chat as a;"
        "p={'executable':True,'ast_verdict':a._ast.REQUIRE_CONFIRM};"
        "assert not a.decision_for(p,'manual',None)['execute'];"
        "assert a.decision_for(p,'manual','y')['execute'];"
        "assert a.decision_for(p,'auto')['execute'];"
        "assert not a.decision_for({'executable':False,'ast_verdict':a._ast.DENY},'auto','y')['execute'];"
        "print('ai decision ok')" % os.path.join(BASE, "src")])
    check(r, "AI confirm mode boundary", rc == 0 and "ai decision ok" in out, lastline(out))

    # ---- Minecraft 联想引擎冒烟（ghost text + 回车采纳，纯内存） ----
    rc, out = run([PY, "-c",
        "import sys;sys.path.insert(0,r'%s');import suggest;"
        "assert suggest.suggest('d')=='iagnose';"
        "assert suggest.suggest('fix')=='';"
        "assert suggest.suggest('/ver')=='bose';"
        "print('suggest ok')" % os.path.join(BASE, "src")])
    check(r, "CLI autosuggest engine", rc == 0 and "suggest ok" in out, lastline(out))

    # ---- /do 核心功能菜单冒烟（方向键菜单 + 12 项核心能力，隔离 keystore） ----
    import tempfile as _tf
    _dd = _tf.mkdtemp(prefix="og-verify-do-")
    _dp = os.path.join(_dd, "keys.json")
    _denv = dict(os.environ)
    _denv["OPSGUARD_KEYSTORE"] = _dp
    _denv["OPSGUARD_API_KEY"] = ""
    _denv["PYTHONIOENCODING"] = "utf-8"
    _cli_do = os.path.join(BASE, "src", "opsguard.py")
    try:
        # 首项现在是 ★AI 排障对话(@ai), 第2项才是 diagnose 样例 → 输 2 验证功能菜单真跑。
        _dp_run = subprocess.run([PY, _cli_do, "--tui"], input="/do\n2\n/exit\n",
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=40, env=_denv)
        _do_out = (_dp_run.stdout or "") + (_dp_run.stderr or "")
        check(r, "CLI /do function menu",
              _dp_run.returncode == 0 and "OpsGuard 能做什么" in _do_out
              and "[OK]" in _do_out and "Traceback" not in _do_out,
              "exit=%d" % _dp_run.returncode)
    except Exception as _e:
        check(r, "CLI /do function menu", False, str(_e)[:80])
    finally:
        try:
            if os.path.isfile(_dp):
                os.remove(_dp)
            os.rmdir(_dd)
        except OSError:
            pass

    # ---- Pester: 继承 ----
    for name, script, exp in [
        ("C1 Pester 10", "c1/Redact.Tests.ps1", 10),
        ("C2 Pester 32", "c2/C2.Tests.ps1", 32),
        ("C3 Pester 20", "c3/Golden.Tests.ps1", 20),
    ]:
        rc, got = pester(os.path.join(BASE, script))
        ok = rc == 0 and "Failed=0" in got and ("Passed=%d" % exp) in got
        check(r, name, ok, got)

    # ---- AST 对抗 ----
    rc, out = run([PY, os.path.join(BASE, "adversarial-verify.py")])
    check(r, "AST adv Python 18", rc == 0 and "0 FAIL" in out, lastline(out))
    rc, out = run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   os.path.join(BASE, "ps-ast-verify.ps1")])
    check(r, "AST adv PS 8", rc == 0 and "0 FAIL" in out, lastline(out))

    # ---- CLI 冒烟(正式版入口) ----
    cli = os.path.join(BASE, "src", "opsguard.py")
    rc, out = run([PY, cli, "doctor"])
    check(r, "CLI doctor exit0", rc == 0 and "python" in out, lastline(out))
    rc, out = run([PY, cli, "backend"])
    check(r, "CLI backend exit0", rc == 0 and "effective" in out, lastline(out))
    rc, out = run([PY, cli, "fix", "--sample", "error"])
    check(r, "CLI fix unconfirmed=1", rc == 1, "exit=%d" % rc)
    # 本地模型已移除, install-local 子命令不该存在; 改为验证新证据命令
    rc, out = run([PY, cli, "selftest"])
    check(r, "CLI selftest matrix", rc == 0 and "total_cases" in out, "exit=%d" % rc)
    rc, out = run([PY, cli, "astcheck"])
    check(r, "CLI astcheck deny", rc == 0 and '"blocked": 10' in out, "exit=%d" % rc)
    rc, out = run([PY, cli, "netdiag", "--catalog"])
    check(r, "CLI netdiag catalog", rc == 0 and '"total"' in out, "exit=%d" % rc)
    rc, out = run([PY, cli, "hashdemo"])
    check(r, "CLI hashdemo 3-hash", rc == 0 and '"assert_restored_equals_before": true' in out
          and '"assert_after_differs_before": true' in out, "exit=%d" % rc)
    # Key/模型管理冒烟: 必须走隔离临时 keystore, 绝不碰真实仓库, Key 不明文出现在输出.
    import tempfile
    _kd = tempfile.mkdtemp(prefix="og-verify-ks-")
    _kp = os.path.join(_kd, "keys.json")
    _kenv = dict(os.environ)
    _kenv["OPSGUARD_KEYSTORE"] = _kp
    _kenv["OPSGUARD_API_KEY"] = ""
    _kenv["PYTHONIOENCODING"] = "utf-8"
    def _krc(args):
        try:
            p = subprocess.run([PY, cli] + args, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30, env=_kenv,
                               input="sk-verifykey1234567890\n")
            return p.returncode, (p.stdout or "") + (p.stderr or "")
        except Exception as e:
            return -1, str(e)
    krc, kout = _krc(["key", "add", "deepseek"])
    check(r, "CLI key add masked", krc == 0 and "sk-v***7890" in kout
          and "verifykey1234567890" not in kout, "exit=%d" % krc)
    krc, kout = _krc(["model", "use", "deepseek", "deepseek-v4-pro"])
    check(r, "CLI model use", krc == 0 and "deepseek-v4-pro" in kout, "exit=%d" % krc)
    krc, kout = _krc(["backend"])
    check(r, "CLI backend keystore triplet", krc == 0 and "keystore:deepseek" in kout
          and "deepseek-v4-pro" in kout and "verifykey1234567890" not in kout, "exit=%d" % krc)
    krc, kout = _krc(["model", "prices", "deepseek"])
    check(r, "CLI model prices official", krc == 0 and "api-docs.deepseek.com" in kout
          and "¥" in kout, "exit=%d" % krc)
    krc, kout = _krc(["model", "prices", "not-a-vendor"])
    check(r, "CLI prices unknown exit4", krc == 4, "exit=%d" % krc)
    krc, kout = _krc(["key", "remove", "deepseek"])
    check(r, "CLI key remove", krc == 0 and '"action": "removed"' in kout, "exit=%d" % krc)
    # 无 Key 时 ai 子命令明确提示先添加(隔离 keystore 已 remove, 为空).
    krc, kout = _krc(["ai", "--message", "DNS 打不开"])
    check(r, "CLI ai no-key hint", krc == 5 and "no_ai_key" in kout
          and "key add" in kout and "verifykey1234567890" not in kout, "exit=%d" % krc)
    try:
        if os.path.isfile(_kp):
            os.remove(_kp)
        os.rmdir(_kd)
    except OSError:
        pass

    # ---- 夹具键 / 真实 DNS (列表传参, $_ 不被 shell 展开) ----
    rc, out = run([PS, "-NoProfile", "-Command", "Write-Output (Test-Path 'HKCU:\\Software\\OpsGuardTest')"])
    check(r, "Fixture key cleaned", "False" in out, out.strip())
    rc, out = run([PS, "-NoProfile", "-Command",
                   "(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {$_.ServerAddresses.Count -gt 0} "
                   "| Select-Object -First 1).ServerAddresses -join ','"])
    check(r, "Real DNS intact", "192.168.1.1" in out or "10.253.240.1" in out, out.strip())

    # ---- 护栏 ZERO(构建前后快照对比) ----
    try:
        a = json.load(open(os.path.join(BASE, "baseline.json"), encoding="utf-8-sig"))
        b = json.load(open(os.path.join(BASE, "baseline-formal.json"), encoding="utf-8-sig"))
        ta = {t["path"]: t for t in a["targets"]}
        tb = {t["path"]: t for t in b["targets"]}
        # 用户 m04253 已授权给 windeploy-kit / lan-ops-scan 真加 --ai，
        # 故这 4 个文件是"任务内授权改动"，从护栏差异中排除；其余任何变化仍算 FAIL。
        ALLOWED = {
            "windeploy-kit": {"WinDeploy.ps1", "modules/AI-Commentary.psm1", "modules\\AI-Commentary.psm1", "README.md"},
            "lan-ops-scan": {"lanops.py", "ai_ops.py", "README.md"},
        }
        def _is_allowed(root, rel):
            norm = rel.replace("\\", "/")
            # pyc / __pycache__ 是运行垃圾，不是任务数据，护栏一律忽略其增删
            if norm.endswith(".pyc") or "/__pycache__/" in ("/" + norm):
                return True
            key = root.rstrip("\\/").split("\\")[-1].split("/")[-1]
            allowed = ALLOWED.get(key, set())
            return any(a.replace("\\", "/") == norm for a in allowed)
        total = 0
        details = []
        for p in ta:
            fa = {f["rel"]: (f["len"], f["sha"]) for f in ta[p].get("files", [])}
            fb = {f["rel"]: (f["len"], f["sha"]) for f in tb[p].get("files", [])}
            for rel in set(fb) - set(fa):
                if not _is_allowed(p, rel):
                    total += 1; details.append("+%s:%s" % (p.split('\\')[-1], rel))
            for rel in set(fa) - set(fb):
                if not _is_allowed(p, rel):
                    total += 1; details.append("-%s:%s" % (p.split('\\')[-1], rel))
            for rel in set(fa) & set(fb):
                if fa[rel] != fb[rel] and not _is_allowed(p, rel):
                    total += 1; details.append("~%s:%s" % (p.split('\\')[-1], rel))
        check(r, "Baseline ZERO", total == 0,
              "changes=%d%s" % (total, (" " + ";".join(details[:4])) if details else ""))
    except Exception as e:
        check(r, "Baseline ZERO", False, str(e)[:80])

    # ---- Release 清单哈希真实性(v0.1.0 历史交付资产仍应成立) ----
    try:
        rel = open(os.path.join(BASE, "Release-清单.md"), encoding="utf-8").read()
        pairs = re.findall(r"`([^`]+\.md)`\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`", rel)
        bad = []
        for fn, size, sha in pairs:
            fp = os.path.join(BASE, fn.replace("/", os.sep))
            if not os.path.exists(fp):
                continue
            data = open(fp, "rb").read()
            if hashlib.sha256(data).hexdigest() != sha or len(data) != int(size):
                bad.append(fn)
        check(r, "Release hashes", not bad and len(pairs) >= 2,
              ",".join(bad) or ("%d match" % len(pairs)))
    except Exception as e:
        check(r, "Release hashes", False, str(e)[:80])

    return r


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    all_pass = True
    for i in range(rounds):
        n = start + i
        print("\n########## FORMAL VERIFY ROUND %d ##########" % n)
        res = one_round(n)
        bad = 0
        for name, ok, detail in res:
            print("  %s %-22s %s" % ("PASS" if ok else "FAIL", name, detail))
            if not ok:
                bad += 1
        print("  ---- ROUND %d: %s (%d/%d) ----" %
              (n, "ALL PASS" if bad == 0 else "%d FAILED" % bad, len(res) - bad, len(res)))
        if bad:
            all_pass = False
    print("\n============ OVERALL: %s ============" %
          ("ALL ROUNDS PASS" if all_pass else "HAS FAILURES"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
