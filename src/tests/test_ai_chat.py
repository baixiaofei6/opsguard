# -*- coding: utf-8 -*-
"""AI 排障对话引擎回归 - 纯内存 mock，不出网、不碰系统、不泄漏 Key.

覆盖: 角色锁定 / action 解析 fail-closed / 确认模式 manual-auto / AST 拒绝不可覆盖 /
脱敏出口不绕过 / 执行默认夹具 / TUI 对话态端到端。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
for _p in (SRC, os.path.join(SRC, "backends"), ROOT,
           os.path.join(ROOT, "c1"), os.path.join(ROOT, "c2"), os.path.join(ROOT, "c3")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ai_chat as ai


GOOD_ACTION = ('结论：DNS 指错。\n'
               '<opsguard-action>{"command":"Set-DnsClientServerAddress -InterfaceIndex 12 '
               '-ServerAddresses (\\u0027192.168.1.1\\u0027)","kind":"dns","target":"12",'
               '"values":{"ServerAddresses":"192.168.1.1"},"reason":"fix dns"}</opsguard-action>')


class TestParseAction(unittest.TestCase):
    def test_parses_good_action(self):
        a = ai.parse_action(GOOD_ACTION)
        self.assertTrue(a)
        self.assertEqual(a["kind"], "dns")
        self.assertEqual(a["values"]["ServerAddresses"], "192.168.1.1")

    def test_none_when_no_block(self):
        self.assertIsNone(ai.parse_action("just text, no action block"))

    def test_none_token(self):
        self.assertIsNone(ai.parse_action("<opsguard-action>none</opsguard-action>"))

    def test_malformed_json_is_none(self):
        self.assertIsNone(ai.parse_action("<opsguard-action>{bad json}</opsguard-action>"))

    def test_bad_kind_rejected(self):
        self.assertIsNone(ai.parse_action(
            '<opsguard-action>{"command":"ipconfig","kind":"kernel","values":{"a":"b"}}</opsguard-action>'))

    def test_empty_values_rejected(self):
        self.assertIsNone(ai.parse_action(
            '<opsguard-action>{"command":"ipconfig","kind":"dns","values":{}}</opsguard-action>'))

    def test_role_locked_system_prompt(self):
        self.assertIn("服务器", ai.SYSTEM_PROMPT)
        self.assertIn("Windows", ai.SYSTEM_PROMPT)
        self.assertIn("Get-Service", ai.SYSTEM_PROMPT)
        self.assertIn("不要输出 API Key", ai.SYSTEM_PROMPT)


class TestConfirmMode(unittest.TestCase):
    def test_normalize_falls_back_to_manual(self):
        self.assertEqual(ai.normalize_confirm_mode("auto"), "auto")
        self.assertEqual(ai.normalize_confirm_mode("bypass"), "manual")
        self.assertEqual(ai.normalize_confirm_mode(None), "manual")

    def make_plan(self, verdict, executable=True):
        return {"executable": executable, "ast_verdict": verdict}

    def test_manual_requires_y(self):
        d = ai.decision_for(self.make_plan(ai._ast.REQUIRE_CONFIRM), "manual", None)
        self.assertFalse(d["execute"])
        self.assertTrue(d["need_confirm"])

    def test_manual_with_y_executes(self):
        d = ai.decision_for(self.make_plan(ai._ast.REQUIRE_CONFIRM), "manual", "y")
        self.assertTrue(d["execute"])
        self.assertFalse(d["need_confirm"])

    def test_manual_with_n_does_not(self):
        d = ai.decision_for(self.make_plan(ai._ast.REQUIRE_CONFIRM), "manual", "n")
        self.assertFalse(d["execute"])

    def test_auto_skips_ask(self):
        d = ai.decision_for(self.make_plan(ai._ast.REQUIRE_CONFIRM), "auto", None)
        self.assertTrue(d["execute"])
        self.assertFalse(d["need_confirm"])

    def test_deny_never_executes_even_auto(self):
        d = ai.decision_for({"executable": False, "ast_verdict": ai._ast.DENY}, "auto", "y")
        self.assertFalse(d["execute"])

    def test_allow_readonly_passes(self):
        d = ai.decision_for(self.make_plan(ai._ast.ALLOW_READONLY), "manual", None)
        self.assertTrue(d["execute"])
        self.assertFalse(d["need_confirm"])

    def test_empty_plan_no_execute(self):
        d = ai.decision_for(None, "auto")
        self.assertFalse(d["execute"])


class TestAIChatFlow(unittest.TestCase):
    def setUp(self):
        self._saved = ai._factory.ask

    def tearDown(self):
        ai._factory.ask = self._saved

    def test_send_builds_plan_via_ast(self):
        seen = {}

        def fake_ask(text, cfg=None, override=None, **opts):
            seen["text"] = text
            seen["opts"] = opts
            return {"text": GOOD_ACTION, "backend": "cloud", "redaction_applied": True,
                    "mapping_count": 2, "fallback_from": None}

        ai._factory.ask = fake_ask
        chat = ai.AIChat({})
        r = chat.send("DNS 指到 192.168.1.99 打不开网页")
        self.assertEqual(r["backend"], "cloud")
        self.assertTrue(r["plan"])
        # 命令是从 AI 回复里解析出来的(plan), 不在发送给 AI 的用户文本里
        self.assertIn("Set-DnsClientServerAddress", r["plan"]["action"]["command"])
        self.assertIn("DNS 指到", seen["text"])
        # system 角色锁定必须传到后端, 历史明文不得塞进 opts
        self.assertIn("system", seen["opts"])
        self.assertNotIn("messages", seen["opts"])
        self.assertEqual(len(chat.messages), 2)

    def test_history_redacted_text_contains_prefix(self):
        def fake_ask(text, cfg=None, override=None, **opts):
            fake_ask.last = text
            return {"text": "no action", "backend": "rules", "redaction_applied": False,
                    "mapping_count": 0}
        ai._factory.ask = fake_ask
        chat = ai.AIChat({})
        chat.send("first question")
        chat.send("second question")
        self.assertIn("用户:", fake_ask.last)
        self.assertIn("OpsGuard:", fake_ask.last)

    def test_backend_error_returns_error_not_raise(self):
        def fake_ask(*a, **k):
            raise RuntimeError("boom")
        ai._factory.ask = fake_ask
        chat = ai.AIChat({})
        r = chat.send("x")
        self.assertIn("error", r)

    def test_empty_input(self):
        self.assertIn("error", ai.AIChat({}).send(""))


class TestTUIAIMode(unittest.TestCase):
    """TUI /ai 对话态与 /aimode 切换: stdin 注入, 配置写临时文件, 不碰真实配置/系统."""
    def setUp(self):
        import json
        import tempfile
        import tui
        self.tui = tui
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        self.tmp.write('{"ai_confirm_mode":"manual"}')
        self.tmp.close()
        # 隔离 keystore 放一把假 Key, 让 /ai 能进对话态, 不依赖本机真 Key、不出网.
        self.store = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({"version": 1,
                   "providers": {"demo": {"api_base": "https://x.invalid/v1",
                                          "key": "sk-fake-only-for-test", "models": ["m"]}},
                   "active": {"provider": "demo", "model": "m"}}, self.store)
        self.store.close()
        self._old_store = os.environ.get("OPSGUARD_KEYSTORE")
        self._old_key = os.environ.get("OPSGUARD_API_KEY")
        os.environ["OPSGUARD_KEYSTORE"] = self.store.name
        os.environ.pop("OPSGUARD_API_KEY", None)

    def tearDown(self):
        os.unlink(self.tmp.name)
        os.unlink(self.store.name)
        if self._old_store is None:
            os.environ.pop("OPSGUARD_KEYSTORE", None)
        else:
            os.environ["OPSGUARD_KEYSTORE"] = self._old_store
        if self._old_key is not None:
            os.environ["OPSGUARD_API_KEY"] = self._old_key

    def run_tui(self, stdin_text):
        import io
        import contextlib
        old_in = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                self.tui.run_repl(cfg={"ai_confirm_mode": "manual", "backend": "rules"},
                                  dispatcher=lambda tokens: 0,
                                  config_path=self.tmp.name)
        finally:
            sys.stdin = old_in
        return buf.getvalue()

    def test_aimode_view(self):
        out = self.run_tui("/aimode\n/exit\n")
        self.assertIn("AI 修复确认模式", out)
        self.assertIn("manual", out)

    def test_aimode_switch_persists_to_temp_only(self):
        import json
        out = self.run_tui("/aimode auto\n/exit\n")
        self.assertIn("已设为 auto", out)
        with open(self.tmp.name, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["ai_confirm_mode"], "auto")

    def test_aimode_rejects_invalid(self):
        import json
        out = self.run_tui("/aimode bypass\n/exit\n")
        self.assertIn("仅支持", out)
        with open(self.tmp.name, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["ai_confirm_mode"], "manual")

    def test_ai_chat_no_args_error(self):
        out = self.run_tui("/ai\n/exit\n")
        self.assertIn("AI 排障对话", out)
        self.assertIn("确认模式", out)

    def test_ai_no_key_shows_hint(self):
        """无 Key 时 /ai 明确提示先添加 Key, 不进入静默降级的对话态."""
        import tempfile
        import contextlib
        import io
        empty = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        empty.write("{}")
        empty.close()
        old_store = os.environ.get("OPSGUARD_KEYSTORE")
        old_envkey = os.environ.get("OPSGUARD_API_KEY")
        os.environ["OPSGUARD_KEYSTORE"] = empty.name
        os.environ.pop("OPSGUARD_API_KEY", None)
        old_in = sys.stdin
        try:
            sys.stdin = io.StringIO("/ai\n/exit\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.tui.run_repl(cfg={"ai_confirm_mode": "manual", "backend": "auto"},
                                  dispatcher=lambda tokens: 0,
                                  config_path=self.tmp.name)
            out = buf.getvalue()
        finally:
            sys.stdin = old_in
            if old_store is None:
                os.environ.pop("OPSGUARD_KEYSTORE", None)
            else:
                os.environ["OPSGUARD_KEYSTORE"] = old_store
            if old_envkey is not None:
                os.environ["OPSGUARD_API_KEY"] = old_envkey
            os.unlink(empty.name)
        self.assertIn("没有配置 AI Key", out)
        self.assertIn("/key add", out)
        self.assertNotIn("── AI 排障对话", out)


class TestNoKeyDetection(unittest.TestCase):
    """has_ai_key / NO_KEY_HINT: 只看有无 Key, 不泄漏本体; 隔离临时 keystore."""
    def setUp(self):
        import tempfile
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        self.tmp.write("{}")
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_empty_keystore_has_no_key(self):
        os.environ.pop("OPSGUARD_API_KEY", None)
        self.assertFalse(ai.has_ai_key({}, path=self.tmp.name))

    def test_hint_tells_how_to_add_key(self):
        self.assertIn("key add", ai.NO_KEY_HINT)
        self.assertIn("/ai", ai.NO_KEY_HINT)

    def test_key_present_detected_without_value(self):
        import json
        with open(self.tmp.name, "w", encoding="utf-8") as f:
            json.dump({"version": 1,
                       "providers": {"demo": {"api_base": "https://x.invalid/v1",
                                              "key": "sk-demo-only-for-test", "models": ["m"]}},
                       "active": {"provider": "demo", "model": "m"}}, f)
        self.assertTrue(ai.has_ai_key({}, path=self.tmp.name))


class TestExecutePlanMock(unittest.TestCase):
    def setUp(self):
        import adapters.system as sysad
        self.saved = sysad._PS_RUNNER
        self.sysad = sysad

    def tearDown(self):
        self.sysad._PS_RUNNER = self.saved

    def test_execute_defaults_to_sandbox(self):
        seen = {}
        def fake_runner(script):
            seen["script"] = script
            return {"ok": True, "stage": "done", "manifest": "M"}
        self.sysad.set_runner(fake_runner)
        plan = {"action": {"kind": "registry", "target": "HKCU:\\Software\\OpsGuardTest",
                           "values": {"Demo": "x"}, "command": "Set-Service -Name X -Status Running"},
                "ast_verdict": ai._ast.REQUIRE_CONFIRM, "executable": True}
        dec = ai.decision_for(plan, "auto")
        r = ai.execute_plan(plan, dec)
        self.assertTrue(r["executed"])
        self.assertIn("-Sandbox", seen["script"])
        self.assertNotIn("-Sandbox;", seen["script"].replace(" -Sandbox", ""))

    def test_no_execute_when_declined(self):
        plan = {"action": {"kind": "dns", "target": "1", "values": {"a": "b"}},
                "ast_verdict": ai._ast.REQUIRE_CONFIRM, "executable": True}
        dec = ai.decision_for(plan, "manual", "n")
        r = ai.execute_plan(plan, dec)
        self.assertFalse(r["executed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
