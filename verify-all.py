# -*- coding: utf-8 -*-
"""OpsGuard parent-agent full acceptance runner.
Runs the entire suite N times (rounds). Each round: c1/c2 unittest, c1/c2/c3
Pester, 2 adversarial sets, baseline diff, fixture-key check, hash check.
Prints compact PASS/FAIL per check and a per-round verdict.
"""
import subprocess, sys, json, hashlib, os

BASE = r"C:/Users/Administrator/.dsh/im/opsguard"
PY = r"C:/Users/Administrator/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe"


def run(cmd, cwd=None, timeout=120):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, shell=True)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"


def check(results, name, ok, detail=""):
    results.append((name, ok, detail))


def one_round(rnd):
    r = []
    # --- Python unittest ---
    rc, out = run('"%s" -m unittest discover -s "%s/c1" -p "test_*.py" -q' % (PY, BASE))
    check(r, "C1 unittest 14", rc == 0 and "OK" in out, out.strip().splitlines()[-1] if out.strip() else "")
    rc, out = run('"%s" -m unittest test_c2 -q' % PY, cwd=BASE + "/c2")
    check(r, "C2 unittest 15", rc == 0 and "OK" in out, out.strip().splitlines()[-1] if out.strip() else "")

    # --- Pester via PowerShell ---
    pester = ('powershell -NoProfile -Command "Import-Module Pester -ErrorAction SilentlyContinue; '
              '$r = Invoke-Pester -Script \'%s\' -PassThru; '
              'Write-Output (\'PesterResult Passed=\' + $r.PassedCount + \' Failed=\' + $r.FailedCount + \' Total=\' + $r.TotalCount)"')
    for pname, script, exp in [
        ("C1 Pester 10", "c1/Redact.Tests.ps1", 10),
        ("C2 Pester 32", "c2/C2.Tests.ps1", 32),
        ("C3 Pester 20", "c3/Golden.Tests.ps1", 20),
    ]:
        rc, out = run(pester % (BASE + "/" + script), timeout=180)
        m = [l for l in out.splitlines() if "PesterResult" in l]
        got = m[-1].strip() if m else out.strip()[-80:]
        ok = rc == 0 and ("Failed=0" in got) and (("Passed=%d" % exp) in got)
        check(r, pname, ok, got)

    # --- adversarial ---
    rc, out = run('"%s" "%s/adversarial-verify.py"' % (PY, BASE))
    check(r, "AST adv Python 18", rc == 0 and "0 FAIL" in out, out.strip().splitlines()[-1] if out.strip() else "")
    rc, out = run('powershell -NoProfile -ExecutionPolicy Bypass -File "%s/ps-ast-verify.ps1"' % BASE, timeout=120)
    check(r, "AST adv PS 8", rc == 0 and "0 FAIL" in out, out.strip().splitlines()[-1] if out.strip() else "")

    # --- fixture key (must be absent) ---
    rc, out = run('powershell -NoProfile -Command "Write-Output (Test-Path \'HKCU:\\Software\\OpsGuardTest\')"')
    key_absent = "False" in out
    check(r, "Fixture key cleaned", key_absent, out.strip())

    # --- real DNS intact ---
    rc, out = run('powershell -NoProfile -Command "(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {$_.ServerAddresses.Count -gt 0} | Select-Object -First 1).ServerAddresses -join \',\'"')
    check(r, "Real DNS intact", "192.168.1.1" in out or "10.253.240.1" in out, out.strip())

    # --- baseline zero changes ---
    try:
        a = json.load(open(BASE + "/baseline.json", encoding="utf-8-sig"))
        b = json.load(open(BASE + "/baseline-final.json", encoding="utf-8-sig"))
        ta = {t["path"]: t for t in a["targets"]}
        tb = {t["path"]: t for t in b["targets"]}
        total_ch = 0
        for p in ta:
            fa = {f["rel"]: (f["len"], f["sha"], f["mtime"]) for f in ta[p].get("files", [])}
            fb = {f["rel"]: (f["len"], f["sha"], f["mtime"]) for f in tb[p].get("files", [])}
            total_ch += len(set(fb) - set(fa)) + len(set(fa) - set(fb)) + len([x for x in set(fa) & set(fb) if fa[x] != fb[x]])
        check(r, "Baseline ZERO changes", total_ch == 0, "changes=%d" % total_ch)
    except Exception as e:
        check(r, "Baseline ZERO changes", False, str(e))

    # --- Release hash truthfulness (first 2 files) ---
    try:
        rel = open(BASE + "/Release-清单.md", encoding="utf-8").read()
        import re
        pairs = re.findall(r"`([^`]+\.md)`\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`", rel)
        hash_ok = True
        detail = []
        for fn, size, sha in pairs:
            fp = os.path.join(BASE, fn.replace("/", os.sep))
            if not os.path.exists(fp):
                continue
            data = open(fp, "rb").read()
            actual = hashlib.sha256(data).hexdigest()
            ok = (actual == sha) and (len(data) == int(size))
            if not ok:
                hash_ok = False
                detail.append(fn + ":MISMATCH")
        check(r, "Release hashes (%d)" % len(pairs), hash_ok and len(pairs) >= 2, ",".join(detail) or "all match")
    except Exception as e:
        check(r, "Release hashes", False, str(e))

    return r


rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
start = int(sys.argv[2]) if len(sys.argv) > 2 else 4
all_pass = True
for i in range(rounds):
    n = start + i
    print("\n########## VERIFY ROUND %d ##########" % n)
    res = one_round(n)
    bad = 0
    for name, ok, detail in res:
        print("  %s %-22s %s" % ("PASS" if ok else "FAIL", name, detail))
        if not ok:
            bad += 1
    verdict = "ALL PASS" if bad == 0 else ("%d FAILED" % bad)
    print("  ---- ROUND %d: %s ----" % (n, verdict))
    if bad:
        all_pass = False
print("\n============ OVERALL: %s ============" % ("ALL ROUNDS PASS" if all_pass else "HAS FAILURES"))
