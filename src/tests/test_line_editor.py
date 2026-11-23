# -*- coding: utf-8 -*-
"""主命令行编辑器测试: Claude Code 风格行编辑/历史，全注入按键流，不碰真 tty/系统。

键位依据: code.claude.com/docs/zh-CN/interactive-mode 的 Text editing /
Command history 表（本机 claude.exe 是 Rust/Bun 打包，strings 抓不到键位表，
如实以官方文档为准，见 tui.py 模块 docstring）。
"""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import tui


def make_editor(keys, history=None, tty=True):
    """构造一个纯内存 LineEditor；返回 (editor, out_buffer)。"""
    buf = io.StringIO()
    ed = tui.LineEditor(
        prompt="❯ ",
        history=history,
        emit=lambda ls: buf.write(tui.to_ansi(ls) + "\n"),
        writer=lambda txt: buf.write(txt),
        key_gen=list(keys),
        tty=tty,
        autosuggest=False,  # 机制测试隔离联想（联想由 TestAutoSuggest 专项覆盖）
    )
    return ed, buf


class TestLineEditorBasics(unittest.TestCase):
    def test_type_and_submit(self):
        ed, _ = make_editor(["CHAR:h", "CHAR:i", "ENTER"])
        self.assertEqual(ed.edit(), "hi")

    def test_submit_goes_to_history(self):
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "ENTER"])
        self.assertEqual(ed.edit(), "ab")
        self.assertEqual(ed.history, ["ab"])

    def test_insert_at_cursor_after_left(self):
        # "ab" 后 LEFT 一次到中间, 插 X => aXb
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "LEFT", "CHAR:X", "ENTER"])
        self.assertEqual(ed.edit(), "aXb")

    def test_backspace_deletes_before_cursor(self):
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "BACKSPACE", "ENTER"])
        self.assertEqual(ed.edit(), "a")

    def test_delete_removes_at_cursor(self):
        # "ab", HOME 到头, DELETE 删 a => "b"
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "HOME", "DELETE", "ENTER"])
        self.assertEqual(ed.edit(), "b")

    def test_ctrl_a_e_move(self):
        # "abc", Ctrl+A 到头, 插 X => Xabc, Ctrl+E 到尾, 插 Y => XabcY
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "CHAR:c", "CTRL_A",
                             "CHAR:X", "CTRL_E", "CHAR:Y", "ENTER"])
        self.assertEqual(ed.edit(), "XabcY")

    def test_end_key_insert(self):
        ed, _ = make_editor(["CHAR:a", "HOME", "END", "CHAR:b", "ENTER"])
        self.assertEqual(ed.edit(), "ab")


class TestLineEditorKillRing(unittest.TestCase):
    def test_ctrl_k_cuts_to_end_then_ctrl_y_pastes(self):
        # "abcd", 移到 2, Ctrl+K 删 "cd", Ctrl+Y 粘回 => abcd
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "CHAR:c", "CHAR:d",
                             "LEFT", "LEFT", "CTRL_K", "CTRL_Y", "ENTER"])
        self.assertEqual(ed.edit(), "abcd")

    def test_ctrl_u_cuts_to_start(self):
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "CHAR:c", "CTRL_U", "ENTER"])
        self.assertEqual(ed.edit(), "")

    def test_ctrl_w_deletes_word(self):
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "CHAR: ", "CHAR:c", "CHAR:d",
                             "CTRL_W", "ENTER"])
        self.assertEqual(ed.edit(), "ab ")

    def test_alt_b_alt_f_word_nav(self):
        # "ab cd", Alt+B 到 cd 前插 X => ab Xcd
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "CHAR: ", "CHAR:c", "CHAR:d",
                             "ALT_B", "CHAR:X", "ENTER"])
        self.assertEqual(ed.edit(), "ab Xcd")

    def test_alt_d_deletes_word_forward(self):
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "CHAR: ", "CHAR:c", "CHAR:d",
                             "HOME", "ALT_D", "ENTER"])
        self.assertEqual(ed.edit(), " cd")


class TestLineEditorHistory(unittest.TestCase):
    def test_up_recalls_last_down_restores_draft(self):
        hist = ["doctor", "backend"]
        # 起手打 draft, UP 取最后一条, DOWN 回草稿
        ed, _ = make_editor(["CHAR:x", "UP", "DOWN", "ENTER"], history=hist)
        self.assertEqual(ed.edit(), "x")

    def test_up_submit_recalled_command(self):
        hist = ["doctor", "backend"]
        ed, _ = make_editor(["UP", "ENTER"], history=hist)
        self.assertEqual(ed.edit(), "backend")

    def test_ctrl_p_n_alias_history(self):
        hist = ["one", "two"]
        ed, _ = make_editor(["CTRL_P", "CTRL_P", "CTRL_N", "ENTER"], history=hist)
        self.assertEqual(ed.edit(), "two")

    def test_esc_clears_line(self):
        ed, _ = make_editor(["CHAR:a", "CHAR:b", "ESC", "ENTER"])
        self.assertEqual(ed.edit(), "")

    def test_ctrl_c_aborts(self):
        ed, _ = make_editor(["CHAR:a", "CTRL_C"])
        self.assertIsNone(ed.edit())

    def test_ctrl_d_on_empty_aborts(self):
        ed, _ = make_editor(["CTRL_D"])
        self.assertIsNone(ed.edit())

    def test_ctrl_r_reverse_search(self):
        hist = ["doctor", "backend check", "backend model"]
        # Ctrl+R 输 "back" 反搜命中 "backend model"；第1个 Enter 采纳回输入行，
        # 第2个 Enter 才提交（Claude Code 真实语义：采纳≠执行）。
        ed, _ = make_editor(["CTRL_R"] + ["CHAR:" + c for c in "back"] + ["ENTER", "ENTER"], history=hist)
        self.assertEqual(ed.edit(), "backend model")


class TestLineEditorCompat(unittest.TestCase):
    def test_non_tty_readline_compat(self):
        ed = tui.LineEditor(key_gen=None, tty=False)
        old = sys.stdin
        sys.stdin = io.StringIO("doctor\n")
        try:
            self.assertEqual(ed.edit(), "doctor")
        finally:
            sys.stdin = old

    def test_stream_key_gen_arrow_and_ctrl(self):
        keys = list(tui._stream_key_gen("ab\x1b[DX\x01\x05\x0b\r"))
        self.assertEqual(keys[:4], ["CHAR:a", "CHAR:b", "LEFT", "CHAR:X"])
        self.assertIn("CTRL_A", keys)
        self.assertIn("CTRL_E", keys)
        self.assertIn("CTRL_K", keys)
        self.assertEqual(keys[-1], "ENTER")

    def test_no_real_tty_touched(self):
        # 所有测试都注入 key_gen；真实 _tty_key_gen 未被调用。
        ed, _ = make_editor(["CHAR:q", "ENTER"])
        self.assertEqual(ed.edit(), "q")
        self.assertTrue(ed.key_gen is not None)


class TestVisibleTyping(unittest.TestCase):
    """打字可见性回归：writer 必须 flush、无 VT 时必须有可见光标标记。

    根因：writer 只 write 不 flush → 打字内容卡在 Python 块缓冲看不到；
    Windows cmd 默认没开 VT → \x1b[2K/\x1b[NG 转义失效。
    """
    def test_out_flushes(self):
        calls = []
        class S:
            def write(self, t): calls.append(("w", t))
            def flush(self): calls.append(("f", None))
        old = tui.sys.stdout
        tui.sys.stdout = S()
        try:
            tui._out("hello")
        finally:
            tui.sys.stdout = old
        self.assertEqual(calls, [("w", "hello"), ("f", None)])

    def test_no_vt_shows_cursor_marker_each_char(self):
        # tty=True, vt=False（模拟 cmd 未开 VT）：逐字应有 │ 光标标记 + \r 覆盖。
        written = []
        keys = ["CHAR:h", "CHAR:i", "ENTER"]
        ed = tui.LineEditor(prompt="❯ ", writer=lambda t: written.append(t),
                            key_gen=lambda: iter(keys), tty=True, vt=False,
                            autosuggest=False)
        self.assertEqual(ed.edit(), "hi")
        frames = [t for t in written if "❯" in t]
        # h 和 i 每一步都必须带可见光标标记，最后提交行是纯文本
        self.assertTrue(any("h│" in f for f in frames), frames)
        self.assertTrue(any("hi│" in f for f in frames), frames)
        self.assertTrue(any(t.startswith("\r") for t in written))

    def test_vt_uses_ansi_cursor_controls(self):
        written = []
        keys = ["CHAR:a", "ENTER"]
        ed = tui.LineEditor(prompt="❯ ", writer=lambda t: written.append(t),
                            key_gen=lambda: iter(keys), tty=True, vt=True,
                            autosuggest=False)
        self.assertEqual(ed.edit(), "a")
        self.assertTrue(any("\x1b[" in t and "G" in t for t in written))
        self.assertTrue(any("\x1b[2K" in t for t in written))

    def test_non_tty_each_char_visible(self):
        out = []
        keys = ["CHAR:h", "CHAR:i", "ENTER"]
        ed = tui.LineEditor(prompt="❯ ", emit=lambda ls: out.append(tui.to_ansi(ls)),
                            key_gen=lambda: iter(keys), tty=False, vt=False,
                            autosuggest=False)
        self.assertEqual(ed.edit(), "hi")
        self.assertTrue(any("h│" in s for s in out))
        self.assertTrue(any("hi│" in s for s in out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
