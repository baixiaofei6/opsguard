# -*- coding: utf-8 -*-
"""OpsGuard parent-agent independent adversarial verification for C2 AST gate.
NOT the subagent's own tests -- hand-written bypass/boundary cases.
"""
import sys
sys.path.insert(0, r"C:/Users/Administrator/.dsh/im/opsguard/c2")
import ast_guard as g

CASES = [
    ("Get-Service -Name Spooler", "allow_readonly"),
    ("Get-Content C:\\secret.txt", "deny"),
    ("Set-Service -Name Spooler -Status Running", "require_confirm"),
    ("Get-Service -Stat Running", "deny"),
    ("Get-Service --% -Name evil", "deny"),
    ("$c='Get-Service'; & $c", "deny"),
    ("& { Get-Service }", "deny"),
    ("Set-Alias gs Remove-Item; gs C:\\", "deny"),
    ("Invoke-Expression 'Get-Service'", "deny"),
    ("iex Get-Service", "deny"),
    ("powershell -enc AAAA", "deny"),
    ("Get-Ser`vice", "deny"),
    ("$x='Get-'; $x+'Service' | iex", "deny"),
    ("Remove-Service X", "deny"),
    ("Format-Volume C", "deny"),
    ("Get-Service -Name", "deny"),
    ("Get-WinEvent -LogName Security -MaxEvents 5", "allow_readonly"),
    ("set-service -name spooler -status running", "require_confirm"),
]

bad = 0
for cmd, exp in CASES:
    got = g.validate(cmd)["verdict"]
    ok = got == exp
    if not ok:
        bad += 1
    print(("OK  " if ok else "FAIL") + " [" + exp + "/" + got + "] " + cmd)

print("=== adversarial: " + str(len(CASES) - bad) + "/" + str(len(CASES)) +
      " pass, " + str(bad) + " FAIL ===")
