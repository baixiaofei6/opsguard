#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpsGuard 核心功能菜单(/do)测试：全部走内置样例/隔离夹具，不碰真系统与任务外文件。"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
import tui

OPS = os.path.join(SRC, "opsguard.py")
PY = sys.executable

# 每个菜单项预置 argv 的期望退出码：fix 不带确认=1（需确认态），其余样例应成功=0。
EXPECTED_RC = {
    "diagnose": 0, "netdiag": 0, "explain": 0, "fix": 1,
    "astcheck": 0, "sanitize": 0, "hashdemo": 0, "selftest": 0,
    "doctor": 0, "backend": 0, "audit": 0, "integrate": 0,
}


def _cleanup(d, keyfile):
    try:
        if os.path.isfile(keyfile):
            os.remove(keyfile)
        os.rmdir(d)
    except OSError:
        pass


def run_cli(argv):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["OPSGUARD_API_KEY"] = ""
    d = tempfile.mkdtemp(prefix="og-do-")
    keyfile = os.path.join(d, "keys.json")
    env["OPSGUARD_KEYSTORE"] = keyfile
    try:
        p = subprocess.run([PY, OPS] + list(argv), cwd=ROOT,
                           capture_output=True, encoding="utf-8", errors="replace",
                           timeout=40, env=env)
        return p.returncode, p.stdout, p.stderr
    finally:
        _cleanup(d, keyfile)


def run_tui(stdin_text):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["OPSGUARD_API_KEY"] = ""
    d = tempfile.mkdtemp(prefix="og-dotui-")
    keyfile = os.path.join(d, "keys.json")
    env["OPSGUARD_KEYSTORE"] = keyfile
    try:
        p = subprocess.run([PY, OPS, "--tui"], cwd=ROOT, input=stdin_text,
                           capture_output=True, encoding="utf-8", errors="replace",
                           timeout=40, env=env)
        return p.returncode, p.stdout, p.stderr
    finally:
        _cleanup(d, keyfile)


class TestDoMenu(unittest.TestCase):
    def test_menu_covers_all_core_commands(self):
        items = tui._do_menu_items()
        cmds = [v[0] for _, v in items]
        for c in ("diagnose", "netdiag", "explain", "fix", "astcheck",
                  "sanitize", "hashdemo", "selftest", "doctor", "backend",
                  "audit", "integrate"):
            self.assertIn(c, cmds, "菜单缺少核心命令 %s" % c)
        self.assertGreaterEqual(len(items), 12)

    def test_every_item_runs_with_expected_exit_code(self):
        # 逐项真跑，确认每项预置 argv 都能出结果、退出码符合预期、无 traceback。
        for label, argv in tui._do_menu_items():
            with self.subTest(argv=argv):
                rc, out, err = run_cli(argv)
                self.assertEqual(rc, EXPECTED_RC[argv[0]],
                                 "%s -> rc=%d out=%s err=%s" % (argv, rc, out[:160], err[:160]))
                self.assertNotIn("Traceback", out + err)

    def test_no_live_no_apply_in_menu(self):
        # 功能菜单全部走样例/夹具：不得出现真改系统的 --live / --apply。
        for _, argv in tui._do_menu_items():
            self.assertNotIn("--live", argv, "菜单项不得含 --live: %s" % argv)
            self.assertNotIn("--apply", argv, "菜单项不得含 --apply: %s" % argv)

    def test_tui_do_select_first_runs_diagnose(self):
        rc, out, err = run_tui("/do\n1\n/exit\n")
        self.assertEqual(rc, 0)
        self.assertIn("OpsGuard 能做什么", out)
        self.assertIn("[OK]", out)
        self.assertIn("识别 2 项异常", out)
        self.assertEqual(err, "")

    def test_tui_do_esc_skips(self):
        rc, out, err = run_tui("/do\n\n/exit\n")
        self.assertEqual(rc, 0)
        self.assertIn("已跳过", out)
        self.assertEqual(err, "")

    def test_tui_do_invalid_index(self):
        rc, out, err = run_tui("/do\n99\n/exit\n")
        self.assertEqual(rc, 0)
        self.assertIn("序号无效", out)
        self.assertEqual(err, "")

    def test_help_shows_do_entry(self):
        rc, out, err = run_tui("/help\n/exit\n")
        self.assertEqual(rc, 0)
        self.assertIn("/do", out)
        self.assertIn("能做什么", out)


if __name__ == "__main__":
    unittest.main()
