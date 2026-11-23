# -*- coding: utf-8 -*-
"""官方核价表测试: 来源真实性、annotate join、边界、不编造、不出网不碰系统."""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import pricing as p


class TestPriceTableIntegrity(unittest.TestCase):
    def test_every_provider_has_source_and_verified(self):
        for name, info in p.PRICE_TABLE.items():
            self.assertTrue(info.get("source", "").startswith("https://"), name)
            self.assertTrue(info.get("verified"), name)
            self.assertTrue(info.get("unit"), name)
            self.assertIsInstance(info.get("models"), dict, name)
            self.assertTrue(info["models"], name)

    def test_verified_date_is_current(self):
        self.assertEqual(p.VERIFIED, "2026-11-23")

    def test_deepseek_real_numbers(self):
        # 真查自官方 pricing 页, 空闲段输入¥1/命中¥0.02/输出¥4, 高峰×2.
        m = p.model_price("deepseek", "deepseek-flash")
        self.assertEqual(m["input"], 1.0)
        self.assertEqual(m["hit"], 0.02)
        self.assertEqual(m["output"], 4.0)
        self.assertEqual(m["peak_input"], 2.0)
        pro = p.model_price("deepseek", "deepseek-v4-pro")
        self.assertEqual(pro["input"], 4.5)
        self.assertEqual(pro["output"], 13.5)

    def test_zhipu_real_numbers_and_free_tier(self):
        f = p.model_price("zhipu", "glm-5.3-flash")
        self.assertEqual(f["input"], 0.8)
        self.assertEqual(f["output"], 2.8)
        self.assertEqual(p.model_price("zhipu", "glm-4-flash")["tier"], "free")

    def test_unknown_prices_not_fabricated(self):
        # Kimi/百炼/OpenAI 数字页未逐条抓到 → 必须标 unknown, 数字为 None, 不给假单价.
        for prov, model in (("moonshot", "kimi-k3.1-pro"), ("dashscope", "qwen-plus"),
                            ("openai", "gpt-4o")):
            m = p.model_price(prov, model)
            self.assertEqual(m["tier"], "unknown", (prov, model))
            self.assertIsNone(m["input"], (prov, model))
            self.assertIsNone(m["output"], (prov, model))
            self.assertIn("官网", m["label"])


class TestTuiModelSelection(unittest.TestCase):
    """TUI 编号选模型: 纯内存 mock stdin, 不出网、不写仓库、不碰系统."""

    def _run(self, models, stdin_line):
        import tui
        old = sys.stdin
        sys.stdin = io.StringIO(stdin_line + "\n")
        lines = []
        try:
            chosen = tui._show_models_with_pricing(lambda ls: lines.extend(ls), "deepseek", models,
                                                    interactive=True)
        finally:
            sys.stdin = old
        return chosen, "\n".join(str(x) for x in lines)

    def test_pick_by_index(self):
        chosen, out = self._run(["deepseek-flash", "deepseek-v4-pro"], "2")
        self.assertEqual(chosen, "deepseek-v4-pro")
        self.assertIn("[1] deepseek-flash", out)
        self.assertIn("[2] deepseek-v4-pro", out)
        self.assertIn("输入序号", out)

    def test_empty_means_skip(self):
        chosen, out = self._run(["deepseek-flash"], "")
        self.assertIsNone(chosen)
        self.assertIn("已跳过", out)

    def test_invalid_index_no_change(self):
        chosen, out = self._run(["deepseek-flash"], "99")
        self.assertIsNone(chosen)
        self.assertIn("序号无效", out)

    def test_unverified_model_warns(self):
        chosen, out = self._run(["deepseek-flash", "new-model"], "1")
        self.assertEqual(chosen, "deepseek-flash")
        self.assertIn("未核到官方单价", out)


class TestAnnotate(unittest.TestCase):
    def test_annotate_known_unknown_and_order(self):
        ann = p.annotate("deepseek", ["deepseek-flash", "brand-new-model", "deepseek-v4-pro"])
        self.assertEqual([a["id"] for a in ann],
                         ["deepseek-flash", "brand-new-model", "deepseek-v4-pro"])
        self.assertTrue(ann[0]["known"])
        self.assertEqual(ann[0]["tier"], "paid")
        self.assertFalse(ann[1]["known"])
        self.assertEqual(ann[1]["tier_label"], "价格待核实")
        self.assertIn("官网", ann[1]["label"])

    def test_annotate_dedups_invalid_models(self):
        ann = p.annotate("zhipu", ["glm-4-flash", "glm-4-flash", "bad model name!", 123, ""])
        ids = [a["id"] for a in ann]
        self.assertEqual(ids, ["glm-4-flash"])

    def test_annotate_unknown_provider_no_fabrication(self):
        ann = p.annotate("some-vendor", ["m1", "m2"])
        self.assertEqual(len(ann), 2)
        for a in ann:
            self.assertFalse(a["known"])
            self.assertEqual(a["source"], "")
            self.assertIn("官网", a["label"])

    def test_model_price_case_insensitive(self):
        self.assertEqual(p.model_price("DEEPSEEK", "DeepSeek-Flash")["input"], 1.0)

    def test_render_lines_contains_source_and_disclaimer(self):
        ann = p.annotate("deepseek", ["deepseek-flash"])
        lines = "\n".join(p.render_lines("deepseek", ann))
        self.assertIn("https://api-docs.deepseek.com", lines)
        self.assertIn("[1] deepseek-flash", lines)
        self.assertIn("以账单为准", lines)
        self.assertIn("不返回价格", lines)

    def test_no_network_call(self):
        # 核价表模块只读常量, 不 import urllib / 不发请求.
        with open(os.path.join(SRC, "pricing.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("urlopen", src)
        self.assertNotIn("requests", src)


class TestSelectMenuArrows(unittest.TestCase):
    """方向键交互菜单：纯内存注入按键流，不碰真 tty、不出网、不写系统。"""

    def _run(self, items, keys, default=0, tty=True):
        import tui
        lines, writes = [], []
        chosen = tui.select_menu(
            items, prompt="选择:", default=default,
            emit=lambda ls: lines.extend(ls),
            writer=lambda s: writes.append(s),
            key_gen=iter(keys), tty=tty,
        )
        return chosen, "\n".join(str(x) for x in lines), writes

    def test_down_then_enter(self):
        items = [("flash", "flash-id"), ("pro", "pro-id"), ("mini", "mini-id")]
        chosen, out, writes = self._run(items, ["DOWN", "ENTER"])
        self.assertEqual(chosen, "pro-id")
        self.assertIn("❯", out)
        self.assertTrue(any("\033[" in w for w in writes), "tty 应有光标重绘")

    def test_up_wraps_to_last(self):
        items = [("a", "a"), ("b", "b"), ("c", "c")]
        chosen, out, _ = self._run(items, ["UP", "ENTER"], default=0)
        self.assertEqual(chosen, "c")

    def test_escape_cancels(self):
        items = [("a", "a"), ("b", "b")]
        chosen, out, _ = self._run(items, ["DOWN", "ESC"])
        self.assertIsNone(chosen)
        self.assertIn("取消", out)

    def test_number_key_selects_directly(self):
        items = [("a", "a"), ("b", "b"), ("c", "c")]
        chosen, out, _ = self._run(items, ["NUM:3", "ENTER"])
        self.assertEqual(chosen, "c")

    def test_arrow_bytes_parsed(self):
        # 真实终端把 \x1b[B 解析为 DOWN（用 _stream_key_gen 验证字节层）。
        import tui
        keys = list(tui._stream_key_gen("\x1b[A\x1b[B\r"))
        self.assertEqual(keys, ["UP", "DOWN", "ENTER"])

    def test_non_tty_index_still_works(self):
        # 非交互（管道/测试）仍可用数字序号，保持向后兼容。
        import tui
        old = sys.stdin
        sys.stdin = io.StringIO("2\n")
        lines = []
        try:
            chosen = tui.select_menu([("a", "a"), ("b", "b")], emit=lambda ls: lines.extend(ls), tty=False)
        finally:
            sys.stdin = old
        self.assertEqual(chosen, "b")

    @unittest.skipIf(os.name != "nt", "Windows msvcrt branch only")
    def test_windows_msvcrt_arrow_bytes(self):
        # 真 Windows 控制台方向键是 \xe0+扫描码(P=下/H=上); mock msvcrt 验证翻译, 不碰真 tty.
        import tui
        class FakeMsvcrt:
            def __init__(self, seq):
                self.seq = list(seq)
            def getwch(self):
                return self.seq.pop(0)
        old = sys.modules.get("msvcrt")
        sys.modules["msvcrt"] = FakeMsvcrt(["\xe0", "P", "\xe0", "H", "\r"])
        try:
            gen = tui._tty_key_gen()
            keys = [next(gen) for _ in range(3)]
        finally:
            if old is None:
                del sys.modules["msvcrt"]
            else:
                sys.modules["msvcrt"] = old
        self.assertEqual(keys, ["DOWN", "UP", "ENTER"])


if __name__ == "__main__":
    unittest.main()
