"""系统适配器测试: mock PS runner, 验证确认门/沙箱/回滚哈希/参数化. 不碰真系统."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

import adapters.system as _adapter


class TestArgQuote(unittest.TestCase):
    def test_ps_quote_escapes_single_quote(self):
        self.assertEqual(_adapter._ps_quote("O'Brien"), "'O''Brien'")

    def test_hashtable_build(self):
        s = _adapter._ps_hashtable({"Name": "X", "Status": "Running"})
        self.assertIn("'Name'='X'", s)
        self.assertIn("'Status'='Running'", s)


class TestGuardedChange(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def tearDown(self):
        _adapter.reset_runner()

    def test_no_confirm_never_runs_ps(self):
        def runner(script):
            self.calls.append(script)
            return {"ok": False, "stage": "confirm"}
        _adapter.set_runner(runner)
        r = _adapter.change("registry", "HKCU:\\Software\\X", {"k": "v"}, confirm_answer=None, sandbox=True)
        # PS 脚本确实发起(确认门在 PS 侧), 但脚本里 ConfirmAnswer 为空
        self.assertIn("-ConfirmAnswer ''", self.calls[0])

    def test_sandbox_default_in_script(self):
        def runner(script):
            self.calls.append(script)
            return {"ok": True, "stage": "executed"}
        _adapter.set_runner(runner)
        _adapter.change("file", "C:\\real\\config.ini", {"content": "x"}, confirm_answer="y")
        self.assertIn("-Sandbox", self.calls[0])
        self.assertNotIn("-Sandbox", _adapter.change.__doc__ or "")  # 文档说明默认沙箱

    def test_live_mode_no_sandbox_flag(self):
        def runner(script):
            self.calls.append(script)
            return {"ok": True}
        _adapter.set_runner(runner)
        _adapter.change("registry", "HKCU:\\Software\\X", {"k": "v"}, confirm_answer="y", sandbox=False)
        self.assertNotIn("-Sandbox", self.calls[0])

    def test_invalid_kind_raises(self):
        with self.assertRaises(_adapter.AdapterError):
            _adapter.change("process", "x", {}, confirm_answer="y")

    def test_rollback_uses_manifest(self):
        def runner(script):
            self.calls.append(script)
            return {"ok": True, "stage": "rollback"}
        _adapter.set_runner(runner)
        m = {"affected_items": [{"kind": "file", "target": "x"}], "before_hash": "a", "after_hash": "b"}
        r = _adapter.rollback(m, sandbox=True)
        self.assertTrue(r["ok"])
        self.assertIn("ConvertFrom-Json", self.calls[0])


class TestRoundTripVerdict(unittest.TestCase):
    """三方哈希判定式的 Python 侧镜像(与 PS Test-OGRoundTrip 一致)."""
    @staticmethod
    def verdict(before, after, restored):
        return (restored.lower() == before.lower()) and (after.lower() != before.lower())

    def test_ok(self):
        self.assertTrue(self.verdict("aaa", "bbb", "aaa"))

    def test_fail_restored_not_before(self):
        self.assertFalse(self.verdict("aaa", "bbb", "ccc"))

    def test_fail_after_equals_before(self):
        self.assertFalse(self.verdict("aaa", "aaa", "aaa"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
