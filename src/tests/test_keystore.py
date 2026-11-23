# -*- coding: utf-8 -*-
"""API Key / 模型仓库测试: 增删改变更/脱敏/边界/原子写/解析优先级.

全部用临时路径, 绝不读写真实 ~/.keystore, 绝不出网, 绝不明文打印 Key.
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import keystore as ks
import backends.factory as factory
from backends.base import MODE_CLOUD, MODE_RULES


class _TempStore(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.mkdtemp(prefix="og-ks-")
        self.p = os.path.join(self._d, "keys.json")

    def tearDown(self):
        try:
            if os.path.isfile(self.p):
                os.remove(self.p)
            os.rmdir(self._d)
        except OSError:
            pass


class TestMask(unittest.TestCase):
    def test_long_key_masks_middle(self):
        self.assertEqual(ks.mask("sk-abcdefghijklmnop"), "sk-a***mnop")

    def test_short_key_fully_masked(self):
        self.assertEqual(ks.mask("abc"), "***")
        self.assertEqual(ks.mask(""), "")

    def test_mask_never_leaves_more_than_4_ends(self):
        m = ks.mask("12345678901234567890")
        self.assertNotIn("56789012345", m)
        self.assertTrue(m.startswith("1234") and m.endswith("7890"))


class TestKeyLifecycle(_TempStore):
    def test_add_then_list_masked(self):
        ks.set_key("deepseek", "sk-secret1234567890", path=self.p)
        st = ks.list_keys(path=self.p)
        self.assertEqual(len(st["providers"]), 1)
        item = st["providers"][0]
        self.assertEqual(item["provider"], "deepseek")
        self.assertNotIn("secret1234567890", str(st))
        self.assertIn("***", item["key_masked"])
        self.assertEqual(item["active_model"], "deepseek-flash")  # 预设首个模型自动选中

    def test_update_key_keeps_single_entry(self):
        ks.set_key("openai", "sk-old00000000000000", path=self.p)
        ks.set_key("openai", "sk-new11111111111111", path=self.p)
        st = ks.list_keys(path=self.p)
        self.assertEqual(len(st["providers"]), 1)
        data = ks.load(self.p)
        self.assertEqual(data["providers"]["openai"]["key"], "sk-new11111111111111")

    def test_remove_key_clears_active(self):
        ks.set_key("deepseek", "sk-1234567890abcdef", path=self.p)
        ks.remove_key("deepseek", path=self.p)
        st = ks.list_keys(path=self.p)
        self.assertEqual(st["providers"], [])
        self.assertEqual(st["active"], {})

    def test_remove_missing_raises(self):
        with self.assertRaises(ks.KeystoreError):
            ks.remove_key("nope", path=self.p)

    def test_remove_one_of_two_switches_active(self):
        ks.set_key("deepseek", "sk-aaaaaaaaaaaaaaaa", path=self.p)
        ks.set_key("openai", "sk-bbbbbbbbbbbbbbbb", path=self.p)
        ks.use_model("openai", "gpt-4o-mini", path=self.p)
        ks.remove_key("openai", path=self.p)
        st = ks.list_keys(path=self.p)
        self.assertEqual(st["active"]["provider"], "deepseek")


class TestModels(_TempStore):
    def test_add_remove_use_model(self):
        ks.set_key("deepseek", "sk-cccccccccccccccc", path=self.p)
        ks.add_model("deepseek", "my-custom-model", path=self.p)
        st = ks.list_keys(path=self.p)
        self.assertIn("my-custom-model", st["providers"][0]["models"])
        ks.use_model("deepseek", "my-custom-model", path=self.p)
        self.assertEqual(ks.load(self.p)["active"]["model"], "my-custom-model")
        ks.remove_model("deepseek", "my-custom-model", path=self.p)
        self.assertEqual(ks.load(self.p)["active"]["model"], "deepseek-flash")  # 切回剩余首个

    def test_use_unknown_model_raises(self):
        ks.set_key("deepseek", "sk-dddddddddddddddd", path=self.p)
        with self.assertRaises(ks.KeystoreError):
            ks.use_model("deepseek", "not-in-list", path=self.p)

    def test_add_model_without_key_raises(self):
        with self.assertRaises(ks.KeystoreError):
            ks.add_model("deepseek", "x", path=self.p)

    def test_remove_last_model(self):
        ks.set_key("custom", "sk-eeeeeeeeeeeeeeee", api_base="https://x.example/v1",
                   models=["only"], path=self.p)
        ks.remove_model("custom", "only", path=self.p)
        self.assertEqual(ks.load(self.p)["active"], {})


class TestValidation(_TempStore):
    def test_empty_key_rejected(self):
        with self.assertRaises(ks.KeystoreError):
            ks.set_key("deepseek", "   ", path=self.p)

    def test_bad_provider_rejected(self):
        for name in ("", "has space", "../evil", "a" * 50):
            with self.assertRaises(ks.KeystoreError):
                ks.set_key(name, "sk-1234567890abcdef", path=self.p)

    def test_bad_base_rejected(self):
        with self.assertRaises(ks.KeystoreError):
            ks.set_key("deepseek", "sk-1234567890abcdef", api_base="ftp://nope", path=self.p)

    def test_newline_in_key_rejected(self):
        with self.assertRaises(ks.KeystoreError):
            ks.set_key("deepseek", "sk-abc\ndef", path=self.p)

    def test_bad_model_rejected(self):
        with self.assertRaises(ks.KeystoreError):
            ks.use_model("deepseek", "bad model!", path=self.p)

    def test_corrupt_file_degrades_to_empty(self):
        with open(self.p, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(ks.load(self.p)["providers"], {})

    def test_unknown_fields_ignored(self):
        with open(self.p, "w", encoding="utf-8") as f:
            import json
            json.dump({"version": 9, "providers": {"x": {"key": "sk-1234567890abcdef"}}, "junk": 1}, f)
        d = ks.load(self.p)
        self.assertEqual(d["version"], 1)
        self.assertIn("x", d["providers"])


class TestResolve(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("OPSGUARD_API_KEY", None)
        os.environ.pop("OPSGUARD_KEYSTORE", None)

    def _store(self):
        d = tempfile.mkdtemp(prefix="og-res-")
        p = os.path.join(d, "keys.json")
        self.addCleanup(lambda: (os.path.isfile(p) and os.remove(p), os.rmdir(d)))
        return p

    def test_keystore_active_is_authoritative_triplet(self):
        p = self._store()
        os.environ.pop("OPSGUARD_API_KEY", None)
        ks.set_key("deepseek", "sk-fromstore12345678",
                   api_base="https://api.deepseek.com", models=["deepseek-flash"], path=p)
        r = ks.resolve({"api_base": "https://wrong.example", "cloud_model": "wrong"}, path=p)
        self.assertEqual(r["key"], "sk-fromstore12345678")
        self.assertEqual(r["api_base"], "https://api.deepseek.com")  # 不用 cfg 的错 base
        self.assertEqual(r["model"], "deepseek-flash")
        self.assertEqual(r["source"], "keystore:deepseek")

    def test_env_fallback_when_store_empty(self):
        p = self._store()
        os.environ["OPSGUARD_API_KEY"] = "sk-envkey1234567890"
        r = ks.resolve({"api_base": "https://x/v1", "cloud_model": "m1"}, path=p)
        self.assertEqual(r["key"], "sk-envkey1234567890")
        self.assertEqual(r["source"], "env:OPSGUARD_API_KEY")
        self.assertEqual(r["model"], "m1")

    def test_empty_when_nothing(self):
        p = self._store()
        os.environ.pop("OPSGUARD_API_KEY", None)
        r = ks.resolve({}, path=p)
        self.assertEqual(r["key"], "")
        self.assertEqual(r["source"], "none")

    def test_custom_env_name(self):
        p = self._store()
        os.environ["MY_KEY"] = "sk-custom1234567890"
        r = ks.resolve({"api_key_env": "MY_KEY"}, path=p)
        self.assertEqual(r["source"], "env:MY_KEY")
        os.environ.pop("MY_KEY", None)

    def test_single_custom_provider_without_model_still_works(self):
        # 自定义服务商无预设模型: Key 存了就不能"云端不可用", 用配置默认模型兜底.
        p = self._store()
        os.environ.pop("OPSGUARD_API_KEY", None)
        ks.set_key("myvendor", "sk-customvendor123456",
                   api_base="https://llm.myvendor.example/v1", models=[], path=p)
        r = ks.resolve({"cloud_model": "my-model"}, path=p)
        self.assertEqual(r["key"], "sk-customvendor123456")
        self.assertEqual(r["api_base"], "https://llm.myvendor.example/v1")
        self.assertEqual(r["model"], "my-model")
        self.assertEqual(r["source"], "keystore:myvendor")


class TestFactoryUsesKeystore(_TempStore):
    def test_cloud_model_and_source_from_keystore(self):
        os.environ.pop("OPSGUARD_API_KEY", None)
        old = os.environ.get("OPSGUARD_KEYSTORE")
        os.environ["OPSGUARD_KEYSTORE"] = self.p
        try:
            ks.set_key("deepseek", "sk-factory1234567890",
                       api_base="https://api.deepseek.com", models=["deepseek-v4-pro"])
            ks.use_model("deepseek", "deepseek-v4-pro")
            st = factory.status({"backend": "auto"})
            self.assertTrue(st[MODE_CLOUD]["available"])
            self.assertEqual(st[MODE_CLOUD]["model"], "deepseek-v4-pro")
            self.assertEqual(st[MODE_CLOUD]["key_source"], "keystore:deepseek")
            self.assertIn("keystore:deepseek", st["effective_detail"])
            self.assertIn("deepseek-v4-pro", st["effective_detail"])
        finally:
            if old is None:
                os.environ.pop("OPSGUARD_KEYSTORE", None)
            else:
                os.environ["OPSGUARD_KEYSTORE"] = old


class TestAutoConfigure(unittest.TestCase):
    """用户核心诉求：只给 Key + 点一下服务商，地址/模型自动带出，不手填地址。"""

    def test_official_presets_use_current_model_names(self):
        # 以官方文档为准(2026-11 核实)：deepseek-chat/reasoner 已于 2026-07-24 停用
        self.assertEqual(ks.PRESETS["deepseek"]["api_base"], "https://api.deepseek.com")
        self.assertIn("deepseek-flash", ks.PRESETS["deepseek"]["models"])
        self.assertIn("deepseek-v4-pro", ks.PRESETS["deepseek"]["models"])
        self.assertNotIn("deepseek-chat", ks.PRESETS["deepseek"]["models"])
        self.assertEqual(ks.PRESETS["dashscope"]["api_base"],
                         "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(ks.PRESETS["moonshot"]["api_base"], "https://api.moonshot.cn/v1")
        self.assertIn("zhipu", ks.PRESETS)
        # 实测(2026-11-23)：同一把智谱 Key 用 glm-4.6 会 429/余额不足, glm-4-flash 免费可用.
        # 免费档必须排在默认模型首位, 否则用户"只填 Key"却默认选到收费模型直接失败.
        self.assertEqual(ks.PRESETS["zhipu"]["models"][0], "glm-4-flash")
        self.assertIn("glm-4.7-flash", ks.PRESETS["zhipu"]["models"])
        self.assertEqual(ks.PRESETS["zhipu"]["api_base"],
                         "https://open.bigmodel.cn/api/paas/v4")

    def test_guess_provider_prefixes(self):
        self.assertEqual(ks.guess_provider("sk-proj-abcdefghijkl")[0], "openai")
        p, conf, reason = ks.guess_provider("sk-abcdefghijkl")
        self.assertIsNone(p)  # 多家通用 sk-，不乱猜
        self.assertEqual(conf, "ambiguous")
        self.assertEqual(ks.guess_provider("1234567890abcdefghij.abcdefghijklmnop")[0], "zhipu")

    def test_add_key_with_preset_auto_fills_base_and_model(self):
        with tempfile.TemporaryDirectory(prefix="og-auto-") as d:
            p = os.path.join(d, "keys.json")
            # 模拟：用户只给了 Key 和点选的服务商，api_base/models 都不填
            r = ks.set_key("deepseek", "sk-1234567890abcdef", path=p)
            self.assertEqual(r["api_base"], "https://api.deepseek.com")
            self.assertEqual(r["models"], ["deepseek-flash", "deepseek-v4-pro"])
            self.assertEqual(r["active"], {"provider": "deepseek", "model": "deepseek-flash"})
            self.assertNotIn("sk-1234567890abcdef", str(r))  # 明文不回显
            # resolve 三元组同源可用（mock 后端不真出网）
            resolved = ks.resolve({"backend": "auto"}, path=p)
            self.assertEqual(resolved["key"], "sk-1234567890abcdef")
            self.assertEqual(resolved["api_base"], "https://api.deepseek.com")
            self.assertEqual(resolved["model"], "deepseek-flash")
            self.assertEqual(resolved["source"], "keystore:deepseek")

    def test_fetch_models_uses_only_chosen_provider_and_no_key_leak(self):
        calls = []

        class _Resp(object):
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                return b'{"data":[{"id":"m-alpha"},{"id":"m-beta"},{"id":"bad id"}]}'

        def _fake_urlopen(req, timeout=None):
            calls.append((req.full_url, dict(req.headers)))
            self.assertTrue(req.full_url.startswith("https://api.deepseek.com/"))
            self.assertTrue(req.full_url.endswith("/models"))
            return _Resp()

        models, why = ks.fetch_models("deepseek", "sk-SUPERSECRET1234",
                                      urlopen=_fake_urlopen)
        self.assertEqual(models, ["m-alpha", "m-beta"])
        self.assertEqual(why, "ok")
        self.assertEqual(len(calls), 1)  # 只访问选定那一家
        self.assertNotIn("SUPERSECRET1234", models)
        self.assertNotIn("SUPERSECRET1234", why)

    def test_fetch_models_fail_returns_reason_no_key_leak(self):
        def _boom(req, timeout=None):
            raise RuntimeError("boom with key in url maybe")

        models, why = ks.fetch_models("deepseek", "sk-SUPERSECRET1234", urlopen=_boom)
        self.assertEqual(models, [])
        self.assertEqual(why, "fetch_failed")
        self.assertNotIn("SUPERSECRET", why)


if __name__ == "__main__":
    unittest.main(verbosity=2)
