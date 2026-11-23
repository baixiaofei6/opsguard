"""混合 AI 后端测试: 脱敏出口 / 三后端契约 / auto 降级 / 可插拔. 全部 mock, 不出网."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

import config as _config
import backends.factory as factory
from backends.base import BaseBackend, BackendError, MODE_CLOUD, MODE_RULES
from backends.rules import RulesBackend


class FakeBackend(BaseBackend):
    """测试用后端: 回显收到的脱敏文本(用于断言 payload 已脱敏)."""
    mode = "fake"

    def __init__(self, cfg=None, hosts=None, capture=None):
        super(FakeBackend, self).__init__(cfg, hosts)
        self.capture = capture if capture is not None else []

    @property
    def available(self):
        return True

    def _chat(self, redacted_text, **opts):
        self.capture.append(redacted_text)
        return "ECHO:" + redacted_text


class TestOutboundRedaction(unittest.TestCase):
    def test_private_ip_redacted_before_send(self):
        cap = []
        b = FakeBackend(capture=cap)
        r = b.ask("DNS 指向 192.168.1.99 和 10.0.0.5 解析失败")
        self.assertNotIn("192.168.1.99", cap[0])
        self.assertNotIn("10.0.0.5", cap[0])
        self.assertIn("IP_1", cap[0])
        self.assertTrue(r["redaction_applied"])
        self.assertGreaterEqual(r["mapping_count"], 2)

    def test_mac_redacted(self):
        cap = []
        FakeBackend(capture=cap).ask("MAC 00:1A:2B:3C:4D:5E 异常")
        self.assertNotIn("00:1A:2B:3C:4D:5E", cap[0])

    def test_placeholder_restored_in_result(self):
        b = FakeBackend()
        r = b.ask("主机 192.168.50.7 不可达")
        self.assertIn("192.168.50.7", r["text"])
        self.assertNotIn("192.168.50.7", r["redacted"])

    def test_non_private_ip_not_redacted(self):
        cap = []
        FakeBackend(capture=cap).ask("公网 8.8.8.8 正常")
        self.assertIn("8.8.8.8", cap[0])  # 如实: RFC1918 之外不脱敏


class TestBackendContract(unittest.TestCase):
    def test_rules_backend_never_requires_key(self):
        b = RulesBackend({})
        self.assertTrue(b.available)
        r = b.ask("DNS unreachable 名称解析失败", scenario="error")
        self.assertEqual(r["backend"], MODE_RULES)
        self.assertIn("离线规则模式", r["text"])

    def test_base_requires_chat_impl(self):
        b = BaseBackend({})
        with self.assertRaises(NotImplementedError):
            b._chat("x")

    def test_outbound_assertion_blocks_residual_private_ip(self):
        # 直接调断言: 含 RFC1918 必须 False
        self.assertFalse(BaseBackend._outbound_safe("host 10.1.2.3 down"))
        self.assertTrue(BaseBackend._outbound_safe("host [IP_1] down"))


class TestAutoFallback(unittest.TestCase):
    def test_auto_falls_to_rules_when_cloud_unavailable(self):
        # 隔离 keystore: 否则本机真实 Key 会让 cloud 可用, 测试跑到真后端(且不该依赖真 Key).
        d = tempfile.mkdtemp(prefix="og-fallback-")
        empty_ks = os.path.join(d, "empty-keys.json")
        old = os.environ.get("OPSGUARD_KEYSTORE")
        os.environ["OPSGUARD_KEYSTORE"] = empty_ks
        try:
            cfg = {"api_base": "https://api.openai.com/v1", "api_key_env": "NO_SUCH_KEY_ENV_XYZ",
                   "backend": "auto"}
            r = factory.ask("DNS unreachable 名称解析失败", cfg, override="auto")
            self.assertEqual(r["backend"], MODE_RULES)
            self.assertTrue(r["fallback_from"])  # 记录了降级原因
        finally:
            if old is None:
                os.environ.pop("OPSGUARD_KEYSTORE", None)
            else:
                os.environ["OPSGUARD_KEYSTORE"] = old
            try:
                os.remove(empty_ks)
                os.rmdir(d)
            except OSError:
                pass

    def test_status_no_local_backend(self):
        # 本地模型后端已移除, 状态里不该有 local 键
        st = factory.status({"backend": "auto"})
        self.assertNotIn("local", st)
        self.assertIn("cloud", st)
        self.assertIn("rules", st)

    def test_explicit_backend_no_fallback(self):
        cfg = {"backend": "rules"}
        r = factory.ask("服务 stopped 已停止", cfg, override="rules")
        self.assertEqual(r["backend"], MODE_RULES)
        self.assertIsNone(r["fallback_from"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
