#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minecraft 式命令联想专项测试（纯内存，不碰真 tty/系统/网络）。"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import suggest
import tui


class TestSuggestEngine(unittest.TestCase):
    def test_prefix_suggestion(self):
        self.assertEqual(suggest.suggest("d"), "iagnose")
        self.assertEqual(suggest.suggest("di"), "agnose")
        self.assertEqual(suggest.suggest("ne"), "tdiag")
        self.assertEqual(suggest.suggest("f"), "ix")

    def test_full_command_no_suggestion(self):
        # 已经是完整命令，不能再联想（否则回车永远采纳不完）
        self.assertEqual(suggest.suggest("diagnose"), "")
        self.assertEqual(suggest.suggest("fix"), "")

    def test_slash_commands(self):
        self.assertEqual(suggest.suggest("/"), "verbose")
        self.assertEqual(suggest.suggest("/ver"), "bose")

    def test_subcommand_and_flag_suggestion(self):
        self.assertTrue(suggest.suggest("model f").startswith("etch"))
        self.assertEqual(suggest.suggest("fix --s"), "ample")
        self.assertEqual(suggest.suggest("fix --c"), "onfirm")

    def test_history_boost(self):
        # 历史里 d 只用过 doctor → doctor 应排在 diagnose 前面
        self.assertEqual(suggest.suggest("d", history=["doctor"]), "octor")

    def test_no_match_and_empty(self):
        self.assertEqual(suggest.suggest("xyz"), "")
        self.assertEqual(suggest.suggest(""), "")

    def test_no_network_no_import_side_effect(self):
        # suggest 模块不导入 urllib/requests，不触碰外部（源码级断言）
        with open(suggest.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("urllib", src)
        self.assertNotIn("requests", src)
        self.assertNotIn("socket", src)


class TestLineEditorAutoSuggest(unittest.TestCase):
    def _editor(self, keys, history=None, tty=True, vt=False, autosuggest=True):
        written = []
        ed = tui.LineEditor(
            prompt="❯ ",
            history=history,
            writer=lambda t: written.append(t),
            emit=lambda ls: written.append(tui.to_ansi(ls)),
            key_gen=lambda: iter(keys),
            tty=tty, vt=vt, autosuggest=autosuggest,
        )
        return ed, written

    def test_ghost_shown_after_each_letter(self):
        # 打 d → 淡字 iagnose；打 di → 淡字 agnose
        ed, written = self._editor(["CHAR:d", "CHAR:i", "ENTER", "ENTER"])
        self.assertEqual(ed.edit(), "diagnose")
        joined = "\n".join(written)
        self.assertIn("diagnose", joined)

    def test_enter_adopts_then_executes(self):
        # 第一次回车采纳补全（返回 None 表示还在编辑循环内）；第二次才提交
        ed, written = self._editor(["CHAR:f", "ENTER", "ENTER"])
        self.assertEqual(ed.edit(), "fix")

    def test_autosuggest_off_submits_literal(self):
        # 关闭联想：打 f 回车就是 "f"（确认态/老行为）
        ed, written = self._editor(["CHAR:f", "ENTER"], autosuggest=False)
        self.assertEqual(ed.edit(), "f")

    def test_ghost_not_shown_when_cursor_midline(self):
        # 光标不在行尾时不联想（Minecraft 只在输入末端联想）。
        # 打 d 那帧有联想是对的；LEFT 之后与最终帧都不该再有。
        ed, written = self._editor(["CHAR:d", "LEFT", "ENTER"])
        self.assertEqual(ed.edit(), "d")
        frames = [f for f in written if "❯" in f]
        self.assertTrue(any("联想:iagnose" in f for f in frames), frames)  # 打 d 时
        self.assertNotIn("iagnose", frames[-1])  # 最终帧干净
        self.assertNotIn("iagnose", frames[-2])  # LEFT 后光标在中间, 无联想


if __name__ == "__main__":
    unittest.main(verbosity=2)
