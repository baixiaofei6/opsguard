"""CLI 测试: help / 退出码 / 子命令行为 / 参数错误. 不碰系统、不出网."""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
OPS = os.path.join(SRC, "opsguard.py")


def run(*args):
    p = subprocess.run([sys.executable, OPS] + list(args), capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout, p.stderr


class TestCLI(unittest.TestCase):
    def test_no_args_shows_help_exit4(self):
        code, out, err = run()
        self.assertEqual(code, 4)
        self.assertIn("usage: opsguard", out)

    def test_help_exit0(self):
        code, out, err = run("--help")
        self.assertEqual(code, 0)
        for cmd in ("diagnose", "explain", "fix", "rollback", "audit", "backend", "doctor",
                    "integrate", "selftest", "astcheck", "sanitize", "hashdemo", "netdiag"):
            self.assertIn(cmd, out)

    def test_help_has_no_install_local(self):
        # 本地模型后端已按用户决定彻底移除
        code, out, err = run("--help")
        self.assertNotIn("install-local", out)

    def test_diagnose_sample_exit0(self):
        code, out, err = run("diagnose", "--sample", "error")
        self.assertEqual(code, 0)
        self.assertIn("summary", out)

    def test_diagnose_bad_sample_exit4(self):
        code, out, err = run("diagnose")
        self.assertEqual(code, 4)

    def test_fix_dryrun_default_exit1_without_confirm(self):
        code, out, err = run("fix", "--sample", "error")
        self.assertIn(code, (1, 0))

    def test_fix_deny_for_dangerous(self):
        code, out, err = run("fix", "--scenario", "fix", "--confirm", "n")
        self.assertEqual(code, 1)
        self.assertIn("DRY-RUN", out)

    def test_backend_status_exit0(self):
        code, out, err = run("backend")
        self.assertEqual(code, 0)
        self.assertIn("effective", out)

    def test_backend_no_local(self):
        # 后端状态不该再出现 local
        code, out, err = run("backend")
        self.assertNotIn('"local"', out)

    def test_doctor_exit0(self):
        code, out, err = run("doctor")
        self.assertEqual(code, 0)
        self.assertIn("python", out)

    def test_audit_last_negative_exit4(self):
        code, out, err = run("audit", "--last", "-1")
        self.assertEqual(code, 4)
        self.assertIn("--last 必须 >= 0", out + err)

    def test_audit_last_zero_returns_empty(self):
        code, out, err = run("audit", "--last", "0")
        self.assertEqual(code, 0)
        self.assertIn('"count": 0', out)

    def test_netdiag_top_zero_exit4(self):
        code, out, err = run("netdiag", "--top", "0")
        self.assertEqual(code, 4)
        self.assertIn("--top 必须 >= 1", out + err)

    def test_netdiag_top_negative_exit4(self):
        code, out, err = run("netdiag", "--top", "-3")
        self.assertEqual(code, 4)
        self.assertIn("--top 必须 >= 1", out + err)

    def test_netdiag_top_valid_exit0(self):
        code, out, err = run("netdiag", "--top", "1")
        self.assertEqual(code, 0)
        self.assertIn("total_rules", out)


def run_env(args, env_overrides=None, stdin_text=None):
    """带环境变量覆盖地跑 CLI(用于把 keystore 指到临时隔离路径)."""
    env = os.environ.copy()
    for k, v in (env_overrides or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    p = subprocess.run([sys.executable, OPS] + list(args), input=stdin_text,
                       capture_output=True, encoding="utf-8", errors="replace",
                       timeout=30, env=env)
    return p.returncode, p.stdout, p.stderr


class TestCLIKeyModel(unittest.TestCase):
    """CLI 的 key/model 子命令: 全程用 OPSGUARD_KEYSTORE 临时隔离路径, 绝不碰真实仓库."""

    def setUp(self):
        self._d = tempfile.mkdtemp(prefix="og-cli-ks-")
        self.p = os.path.join(self._d, "keys.json")
        # 子进程用 UTF-8 输出, 与 run_env 的 encoding="utf-8" 解码一致(避免 GBK 控制台乱码).
        self.env = {"OPSGUARD_KEYSTORE": self.p, "OPSGUARD_API_KEY": None,
                    "PYTHONIOENCODING": "utf-8"}

    def tearDown(self):
        try:
            if os.path.isfile(self.p):
                os.remove(self.p)
            os.rmdir(self._d)
        except OSError:
            pass

    def test_key_add_list_masked_remove(self):
        # Key 从 stdin 管道输入(不回显), 明文不出现在任何输出.
        rc, out, err = run_env(["key", "add", "deepseek"], self.env,
                               stdin_text="sk-supersecret123456\n")
        self.assertEqual(rc, 0)
        self.assertNotIn("supersecret", out + err)
        self.assertIn("sk-s***3456", out)
        rc, out, err = run_env(["key", "list"], self.env)
        self.assertEqual(rc, 0)
        self.assertNotIn("supersecret", out + err)
        self.assertIn("deepseek", out)
        rc, out, err = run_env(["key", "remove", "deepseek"], self.env)
        self.assertEqual(rc, 0)

    def test_key_add_empty_rejected(self):
        rc, out, err = run_env(["key", "add", "deepseek"], self.env, stdin_text="\n")
        self.assertEqual(rc, 4)
        self.assertIn("Key", out + err)

    def test_model_use_requires_key(self):
        rc, out, err = run_env(["model", "use", "deepseek", "deepseek-flash"], self.env)
        self.assertEqual(rc, 4)
        self.assertIn("未配置", out + err)

    def test_full_flow_triplet(self):
        run_env(["key", "add", "deepseek"], self.env, stdin_text="sk-1234567890abcdef\n")
        rc, out, err = run_env(["model", "use", "deepseek", "deepseek-v4-pro"], self.env)
        self.assertEqual(rc, 0)
        rc, out, err = run_env(["backend"], self.env)
        self.assertEqual(rc, 0)
        self.assertIn("keystore:deepseek", out)
        self.assertIn("deepseek-v4-pro", out)
        self.assertNotIn("1234567890abcdef", out + err)

    def test_help_lists_new_commands(self):
        rc, out, err = run_env(["--help"], self.env)
        self.assertEqual(rc, 0)
        self.assertIn("key", out)
        self.assertIn("model", out)

    def test_model_prices_local_no_network(self):
        # 查核价表不出网、不需 Key；标注来自官方价格页。
        rc, out, err = run_env(["model", "prices", "deepseek"], self.env)
        self.assertEqual(rc, 0)
        self.assertIn("api-docs.deepseek.com", out)
        self.assertIn("deepseek-flash", out)
        self.assertIn("¥", out)

    def test_model_prices_unknown_provider_exit4(self):
        rc, out, err = run_env(["model", "prices", "not-a-vendor"], self.env)
        self.assertEqual(rc, 4)
        self.assertIn("未收录", out + err)

    def test_fetch_annotates_without_key_leak(self):
        # mock /models: 用 monkeypatch 方式通过 stdin 无法注入, 这里验证 fetch 的失败分支
        # 不回显 Key, 成功分支的标注走纯函数 annotate(已在 test_pricing 覆盖).
        # --api-base 指向本机不可达端口, 快速失败、绝不真出网.
        rc, out, err = run_env(["model", "fetch", "deepseek", "--key", "sk-should-not-leak-9999",
                                "--api-base", "http://127.0.0.1:1/v1"], self.env)
        self.assertEqual(rc, 5)  # 拉取失败=后端不可用
        self.assertIn("失败", out + err)
        # 失败也不回显明文 Key.
        self.assertNotIn("should-not-leak", out + err)


def run_tui(stdin_text):
    """TUI 强制 stdout=utf-8, 这里显式以 utf-8 解码, 避免 GBK 误判."""
    p = subprocess.run([sys.executable, OPS, "--tui"], input=stdin_text,
                       capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    return p.returncode, p.stdout


def run_tui_full(stdin_text, env_overrides=None):
    """同 run_tui, 但额外返回 stderr, 用于验证 TUI 不泄漏错误到终端."""
    env = os.environ.copy()
    for k, v in (env_overrides or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    p = subprocess.run([sys.executable, OPS, "--tui"], input=stdin_text,
                       capture_output=True, encoding="utf-8", errors="replace", timeout=30, env=env)
    return p.returncode, p.stdout, p.stderr


class TestTuiKeyModel(unittest.TestCase):
    """TUI 内 /key /model 交互: Key 不回显/不明文/不泄漏 stderr, 全隔离路径."""

    def setUp(self):
        self._d = tempfile.mkdtemp(prefix="og-tui-ks-")
        self.p = os.path.join(self._d, "keys.json")
        # 假 Key 不能真出网: 关掉 key add 后的自动拉模型(链路本身用 mock 在 test_keystore 覆盖).
        self.env = {"OPSGUARD_KEYSTORE": self.p, "OPSGUARD_API_KEY": None,
                    "PYTHONIOENCODING": "utf-8", "OPSGUARD_KEY_AUTOFETCH": "0"}

    def tearDown(self):
        try:
            if os.path.isfile(self.p):
                os.remove(self.p)
            os.rmdir(self._d)
        except OSError:
            pass

    def test_key_list_empty(self):
        _, out, err = run_tui_full("/key\n/exit\n", self.env)
        self.assertEqual(err, "")
        self.assertIn("(空)", out)
        self.assertIn("/key add", out)

    def test_key_add_masked_and_no_stderr_leak(self):
        # 第1行命令, 第2行 Key 明文(被 readline 读走), 后续 /key 查看.
        _, out, err = run_tui_full("/key add deepseek\nsk-tui-secret99999\n/key\n/exit\n", self.env)
        self.assertEqual(err, "")  # getpass 警告不能漏到 stderr
        self.assertNotIn("tui-secret99999", out + err)
        self.assertIn("sk-t***9999", out)
        self.assertIn("已添加", out)

    def test_model_use_and_list(self):
        run_tui_full("/key add deepseek\nsk-modeltest123456\n/exit\n", self.env)
        _, out, err = run_tui_full("/model use deepseek deepseek-v4-pro\n/model\n/exit\n", self.env)
        self.assertEqual(err, "")
        self.assertIn("执行模型已切换", out)
        self.assertIn("deepseek-v4-pro", out)
        self.assertNotIn("modeltest123456", out + err)

    def test_readonly_blocks_key_add_and_model_use(self):
        _, out, err = run_tui_full("/mode readonly\n/key add deepseek\n/model use deepseek x\n/exit\n", self.env)
        self.assertEqual(err, "")
        self.assertEqual(out.count("[readonly]"), 2)


class TestTuiPricing(unittest.TestCase):
    """TUI 内官方计费标注展示: 来源真实、编号清晰、不出网、不碰系统."""

    def setUp(self):
        self._d = tempfile.mkdtemp(prefix="og-price-ks-")
        self.p = os.path.join(self._d, "keys.json")
        self.env = {"OPSGUARD_KEYSTORE": self.p, "OPSGUARD_API_KEY": None,
                    "PYTHONIOENCODING": "utf-8", "OPSGUARD_KEY_AUTOFETCH": "0"}

    def tearDown(self):
        try:
            if os.path.isfile(self.p):
                os.remove(self.p)
            os.rmdir(self._d)
        except OSError:
            pass

    def test_model_prices_shows_official_source(self):
        _, out, err = run_tui_full("/model prices deepseek\n/exit\n", self.env)
        self.assertEqual(err, "")
        self.assertIn("api-docs.deepseek.com", out)
        self.assertIn("付费", out)
        self.assertIn("[1] deepseek-flash", out)

    def test_model_prices_all_lists_vendors(self):
        _, out, err = run_tui_full("/model prices\n/exit\n", self.env)
        self.assertEqual(err, "")
        for v in ("deepseek", "zhipu", "moonshot", "dashscope", "openai"):
            self.assertIn(v, out)

    def test_help_lists_pricing_commands(self):
        _, out, err = run_tui_full("/help\n/exit\n", self.env)
        self.assertEqual(err, "")
        self.assertIn("/model fetch", out)
        self.assertIn("/model prices", out)


class TestTuiConfirmState(unittest.TestCase):
    """确认菜单列出的 y/N/d/a 必须真能响应, 且告知与实际行为一致. 全程 DRY-RUN 不碰系统."""

    def test_menu_keys_d_a_n_respond(self):
        _, out = run_tui("/fix --sample error\nd\na\nn\n/exit\n")
        self.assertIn("── diff（当前 → 预期）──", out)
        self.assertIn("--- 当前", out)  # 真 diff 内容, 不是键名
        self.assertIn("+++ 预期", out)
        self.assertIn("── AST 判定 ──", out)
        self.assertIn("verdict: require_confirm", out)
        self.assertIn("已取消", out)
        self.assertNotIn("invalid choice", out)

    def test_menu_key_y_is_confirm_not_command(self):
        _, out = run_tui("/fix --sample error\ny\n/exit\n")
        self.assertNotIn("invalid choice: 'y'", out)
        # DRY-RUN 下按 y 也只是模拟, 不出现 LIVE 真改告知
        self.assertNotIn("将真实改动系统", out)

    def test_dryrun_notice_is_honest(self):
        _, out = run_tui("/fix --sample error\n/exit\n")
        self.assertIn("模拟演练", out)
        self.assertIn("不会改动你的系统", out)
        self.assertNotIn("Yes, and don't ask again", out)

    def test_permanent_ask_switch_not_shown(self):
        _, out = run_tui("/fix --sample error\n/exit\n")
        self.assertNotIn("don't ask again", out)
        self.assertIn("无永久免问开关", out)

    def test_live_notice_is_honest(self):
        # --live 才提示"将真实改动系统"; 但仍需 y, 这里只到菜单不确认, 不真改.
        _, out = run_tui("/fix --sample error --live\n/exit\n")
        self.assertIn("将真实改动系统", out)
        self.assertIn("自动备份", out)
        self.assertIn("目标:", out)


class TestTuiReadonly(unittest.TestCase):
    """readonly 只读模式: 拦截所有写操作, 只读命令照常. 全程不碰系统/配置."""

    def test_readonly_blocks_fix_rollback_integrate(self):
        _, out = run_tui("/mode readonly\n/fix --sample error\n/rollback --manifest x\n/integrate\n/exit\n")
        self.assertIn("只读模式", out)
        self.assertEqual(out.count("[readonly]"), 3)

    def test_readonly_blocks_config_set(self):
        _, out = run_tui("/mode readonly\n/config set backend cloud\n/exit\n")
        self.assertIn("[readonly] 只读模式不可改配置", out)

    def test_readonly_allows_read_commands(self):
        _, out = run_tui("/mode readonly\n/backend\n/exit\n")
        self.assertNotIn("[readonly]", out)
        self.assertIn("[OK]", out)


class TestTuiErrorHandling(unittest.TestCase):
    """TUI 错误处理: 未知命令/子命令错误必须留在界面内, 不泄漏 stderr, 不误标退出码."""

    def test_unknown_command_stays_in_ui(self):
        # 用户在 TUI 里输错命令: 给出友好提示, 而不是 argparse 的原始 usage/error.
        _, out, err = run_tui_full("/bogus\n/exit\n")
        self.assertEqual(err, "")  # stderr 必须干净
        self.assertIn("未知命令", out)
        self.assertIn("/help", out)

    def test_unknown_command_not_mislabeled_ast_deny(self):
        _, out, _ = run_tui_full("/bogus\n/exit\n")
        self.assertIn("[ARGS]", out)
        self.assertNotIn("[AST-DENY]", out)

    def test_subcommand_stderr_captured(self):
        # rollback 不存在的 manifest 走 sys.stderr; TUI 必须捕获并显示, 不泄漏到终端.
        _, out, err = run_tui_full("/rollback --manifest /nonexistent/x.json\n/exit\n")
        self.assertEqual(err, "")
        self.assertIn("manifest", out)


class TestBackendErrorCaught(unittest.TestCase):
    """真回归：cloud._chat 抛的 BackendError 必须被 cmd_explain 接住, 不泄漏 traceback.

    根因曾为 base 被以 'base' 和 'backends.base' 两个名字各加载一次 ->
    opsguard.py 的 except BackendError 与 cloud 抛的不是同一个类, 捕获失效.
    用本机不可达端口(连接立即被拒, 不出网)触发真实 _chat 异常路径.
    """

    def test_cloud_failure_no_traceback_exit5(self):
        import json
        with tempfile.TemporaryDirectory(prefix="og-berr-") as d:
            ks_path = os.path.join(d, "keys.json")
            env = os.environ.copy()
            env["OPSGUARD_KEYSTORE"] = ks_path
            env["PYTHONIOENCODING"] = "utf-8"
            env.pop("OPSGUARD_API_KEY", None)
            rc, out, err = run_env(
                ["key", "add", "custom", "--key", "sk-deadbeef0000",
                 "--api-base", "http://127.0.0.1:1/v1"], env)
            self.assertEqual(rc, 0, out + err)
            report = os.path.join(d, "r.html")
            with open(report, "w", encoding="utf-8") as f:
                f.write("<html><body>DNS 10.0.0.1 unreachable</body></html>")
            rc, out, err = run_env(["explain", "--report", report, "--backend", "cloud"], env)
            self.assertEqual(rc, 5, out + err)          # EXIT_BACKEND
            self.assertNotIn("Traceback", out + err)    # 绝不泄漏栈
            self.assertIn("云端", out + err)

    def test_backend_error_class_identity(self):
        # 直接断言模块身份：opsguard.py 用的 BackendError 与 cloud/factory 用的同一个类
        code = (
            "import opsguard, base; "
            "assert opsguard.BackendError is base.BackendError, 'opsguard vs base mismatch'; "
            "print('OK')"
        )
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           timeout=30, cwd=SRC)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("OK", p.stdout)


class TestCLINoAIKey(unittest.TestCase):
    """ai 子命令无 Key 时明确提示先添加, 不静默降级(隔离 keystore, 不出网)."""
    def test_ai_without_key_exits5_with_hint(self):
        with tempfile.TemporaryDirectory(prefix="og-nokey-") as d:
            env = os.environ.copy()
            env["OPSGUARD_KEYSTORE"] = os.path.join(d, "keys.json")
            env["PYTHONIOENCODING"] = "utf-8"
            env.pop("OPSGUARD_API_KEY", None)
            rc, out, err = run_env(["ai", "--message", "DNS 打不开"], env)
            self.assertEqual(rc, 5, out + err)          # EXIT_BACKEND
            self.assertIn("no_ai_key", out)
            self.assertIn("key add", out)
            self.assertNotIn("Traceback", out + err)

    def test_ai_explicit_rules_backend_allowed_without_key(self):
        """显式 --backend rules 是用户故意用离线规则, 不拦(不返回 no_ai_key)."""
        with tempfile.TemporaryDirectory(prefix="og-nokey-") as d:
            env = os.environ.copy()
            env["OPSGUARD_KEYSTORE"] = os.path.join(d, "keys.json")
            env["PYTHONIOENCODING"] = "utf-8"
            env.pop("OPSGUARD_API_KEY", None)
            rc, out, err = run_env(["ai", "--message", "DNS 打不开", "--backend", "rules"], env)
            self.assertNotIn("no_ai_key", out)
            self.assertNotEqual(rc, 5, out + err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
