#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpsGuard TUI - Claude Code 风格终端交互界面, 宇宙主题 logo(黑洞/行星/星野), Python 3.8+ 纯标准库.

设计依据(真实取证, 非印象):
- strings 抓自真实 claude.exe v2.1.319(仅抓到确认/提交文案, 键位表在 Rust/Bun 压缩代码里抓不到):
    "- Press return to submit."
    "Space to toggle, Enter to confirm, a to select all, n to select none, i to invert"
    "Yes, and don't ask again for ..." / "No, and tell ... what to do differently"
- 主命令行编辑键位来自官方文档 code.claude.com/docs/zh-CN/interactive-mode 的
  Text editing / Command history 表 (Ctrl+A/E/K/U/W、Alt+B/F/D、↑↓/Ctrl+P/N
  历史、Ctrl+R 反搜、Esc 清行); 不是从二进制逆出来的, 如实标注.
- pty+VT102 逐格测量布局(copperhead/claude-ui-layout.md, Claude Code v2.1.220):
    logo 彩色 + name bold + version/cwd 灰(#999999) + 深色底 + 多行 banner
    + 内容滚动区 + 底部输入框 + 右对齐状态 + 权限确认菜单
- 本模块 logo 为宇宙主题: 黑洞吸积盘 + 带环行星 + 星野, 逐字符分色做层次, 其余结构对齐 Claude Code.

统一数据模型: Line = list[Span], Span = (text, rgb_or_None, bold_bool).
同一份内容既能 to_ansi (真实终端) 又能 to_html (截图), 保证截图即真实输出.
"""
import os
import sys

try:
    import suggest as _suggest   # Minecraft 式命令联想（与 tui.py 同目录）
except ImportError:
    _suggest = None


# 淡字（ghost text）颜色：比普通灰更暗，Claude/Minecraft 风格"未采纳的联想"。
GHOST = (95, 105, 120)


def _out(txt):
    """统一输出口：write 后立刻 flush。

    Claude Code(Node readline 的 kRefreshLine)每次重绘都立即吐到终端；
    Python 默认对非 tty 管道/部分控制台是块缓冲，只 write 不 flush 会让
    打字的字符卡在缓冲区里——这就是"打字看不见"的根因之一。
    """
    sys.stdout.write(txt)
    try:
        sys.stdout.flush()
    except Exception:
        pass


def _enable_windows_vt():
    """Windows 控制台开启 ANSI/VT 处理(ENABLE_VIRTUAL_TERMINAL_PROCESSING)。

    \x1b[2K 清行、\x1b[N G 定位光标在 Windows conhost 默认关闭, 会以字面
   转义序列显示或被忽略 —— 这是"打字看不见/满屏乱码"的第二个根因。
   返回 True=可用 ANSI 光标控制; False=调用方需降级为纯 \r + 标记渲染。
   """
    if os.name != "nt":
        return True  # Unix/macOS 终端原生支持 VT
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if not k32.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if mode.value & vt:
            return True
        return bool(k32.SetConsoleMode(h, mode.value | vt))
    except Exception:
        return False


# ---------- 宇宙配色 (RGB) ----------
MOON     = (168, 185, 235)   # 强调色 - 银蓝(提示符/哈希, 兼容旧引用)
MOON_D   = (120, 138, 200)   # 暗银蓝
NAME     = (240, 246, 252)   # 品牌名 - 近白
STAR     = (240, 246, 252)   # 亮星
STAR_D   = (139, 148, 158)   # 暗星
DISK_OUT = (86, 182, 194)    # 吸积盘外层 - 蓝青
DISK_MID = (176, 120, 220)   # 吸积盘中层 - 紫
DISK_IN  = (255, 170, 60)    # 吸积盘内层 - 金橙
BRIGHT   = (255, 235, 180)   # 光子环 - 亮白金
CORE     = (46, 40, 58)      # 事件视界 - 极暗
PLANET   = (88, 166, 255)    # 行星 - 蓝
RING     = (210, 153, 34)    # 行星环 - 金
GRAY   = (139, 148, 158)   # 元信息 - 灰 (#8b949e, 对齐实测)
DIM    = (110, 118, 129)   # 更暗的灰
GREEN  = (63, 185, 80)
YELLOW = (210, 153, 34)
RED    = (248, 81, 73)
BLUE   = (88, 166, 255)
CYAN   = (86, 182, 194)
USER   = (255, 198, 109)   # 用户消息 - 暖黄
BORDER = (88, 96, 110)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERSION = "v0.2.0"   # 单一版本常量, 与 Release-清单.md 保持一致; banner/status 都读它

# 合法子命令白名单 (与 opsguard.py build_parser 的 add_subparsers 保持一致).
# TUI 里输错命令时先在这里拦, 避免 argparse 的 usage/error 打到 stderr 污染交互界面.
KNOWN_COMMANDS = {
    "diagnose", "explain", "fix", "rollback", "audit", "backend", "doctor",
    "astcheck", "sanitize", "selftest", "hashdemo", "netdiag", "integrate",
    "key", "model",  # API Key / 模型管理(也可在 TUI 用 /key /model 交互)
}


# ---------- styled line helpers ----------
def S(text, color=None, bold=False):
    """一个片段: text, rgb, bold."""
    return (text, color, bold)


def line(*spans):
    return list(spans)


def plain(text, color=None, bold=False):
    return line(S(text, color, bold))


def dw(s):
    """终端显示宽度: 全角/中文算 2, 其余算 1. 用于等宽字体对齐."""
    w = 0
    for ch in s:
        o = ord(ch)
        if o < 0x20 or (0x7f <= o < 0xa0):
            continue
        if (0x1100 <= o <= 0x115f) or (0x2e80 <= o <= 0xa4cf) or \
           (0xac00 <= o <= 0xd7a3) or (0xf900 <= o <= 0xfaff) or \
           (0xfe30 <= o <= 0xfe6f) or (0xff00 <= o <= 0xff60) or \
           (0xffe0 <= o <= 0xffe6) or (0x20000 <= o <= 0x3fffd) or o == 0x3000:
            w += 2
        else:
            w += 1
    return w


def pad(s, width):
    """按显示宽度右侧补空格到 width."""
    return s + " " * max(0, width - dw(s))


# ---------- 宇宙主题 logo ----------
def moon_logo():
    """宇宙场景 logo(细致多层): 黑洞吸积盘 + 带环行星 + 星野.
    每字符按物理位置分色: 星空点/盘外蓝青→中紫→内金/光子环白金/事件视界极暗.
    函数沿用 moon_logo 名字以兼容 banner() 调用, 返回 6 行 spans."""
    def s(t, c, b=False):
        return S(t, c, b)
    return [
        # 星野: 疏密错落的亮点, 亮星近白 / 暗星灰
        line(s("  ·      ✦      ·        ·   ", STAR_D),
             s("✧", STAR, True), s("     ·   ", STAR_D), s("·", STAR)),
        # 吸积盘外缘: 蓝青, 左侧有带环行星
        line(s("       ╭─────────╮       ", DISK_OUT),
             s("  ·", STAR_D), s("   ╭──╮", RING), s("  ", STAR_D)),
        # 盘中层(紫) + 行星本体(蓝) + 环
        line(s("     ╭╯ ╭─────╮ ╰╮  ", DISK_MID),
             s(" ◯", PLANET, True), s("═", RING), s("    ✦", STAR)),
        # 光子环(白金) + 事件视界(极暗) + 内盘金
        line(s("    ╭ ", DISK_OUT), s("╭", DISK_IN), s("●●●", BRIGHT, True),
             s("╮", DISK_IN), s(" ╮   ", DISK_OUT), s("  ·", STAR_D)),
        # 事件视界核心 + 吸积盘下缘紫/蓝青
        line(s("    ╰╮ ", DISK_OUT), s("●", CORE), s("███", CORE),
             s("●", CORE), s(" ╭╯ ", DISK_OUT), s("    ", STAR_D)),
        # 盘尾收束 + 星野
        line(s("      ╰──╯ ╰───╯     ", DISK_MID),
             s("   ·      ✧     ·  ", STAR_D)),
    ]


def banner(cfg=None, version=None):
    """品牌头: 左侧宇宙 logo, 右侧名称/版本/后端/cwd. 返回 lines."""
    cfg = cfg or {}
    version = version or VERSION   # 版本只从单一常量取, 不再写死
    backend = cfg.get("backend", "auto")
    cwd = os.path.basename(ROOT.rstrip("\\/")) or ROOT
    logo = moon_logo()
    texts = [
        ("✦ OpsGuard  ", NAME, True, " " + version, GRAY, False),
        ("   can prove safe · CLI", GRAY, False, "", None, False),
        ("   backend=" + str(backend), CYAN, False, "", None, False),
        ("   PS 5.1 · Pester 3.4", DIM, False, "", None, False),
        ("   ~\\" + cwd, GRAY, False, "", None, False),
        ("", None, False, "", None, False),
    ]
    out = []
    for i, lg in enumerate(logo):
        t1, c1, b1, t2, c2, b2 = texts[i]
        sp = list(lg)
        sp.append(S("  ", None, False))
        sp.append(S(t1, c1, b1))
        if t2:
            sp.append(S(t2, c2, b2))
        out.append(sp)
    return out


# ---------- 组件 ----------
def rule(char="─", width=72, color=BORDER):
    return plain(char * width, color)


def blank():
    return plain("")


def user_msg(text):
    return line(S("❯ ", MOON, True), S(text, USER, False))


def assistant_msg(text):
    return line(S("● ", CYAN, True), S(text, NAME, False))


def tool_call(name, detail):
    return line(S("  ⏺ ", GREEN, True), S(name, GREEN, True), S("  " + detail, GRAY, False))


def ast_card(verdict, reason, before, after, hash_before):
    """三栏证据卡: AST / diff / rollback hash. 纯 ASCII 内容 + 等宽栏, 保证边框对齐.

    三栏内部宽度(字符): C1=22, C2=24, C3=20; 用 pad() 按显示宽度补齐.
    呼应阶段A/B视觉规范(拍板全A): 深色终端 + 三栏证据卡 + unified diff.
    """
    C1, C2, C3 = 22, 24, 20
    top = "  ┌─ " + pad("AST VERDICT", C1 - 1) + "┬─ " + pad("DIFF", C2 - 1) + \
          "┬─ " + pad("ROLLBACK HASH", C3 - 2) + "┐"
    bar = "  └" + "─" * (C1 + 2) + "┴" + "─" * (C2 + 2) + "┴" + "─" * (C3 + 2) + "┘"

    def row(a_sp, b_sp, c_sp):
        # a_sp/b_sp/c_sp: list of Span; 用显示宽度补齐到栏宽
        def fit(spans, width):
            used = sum(dw(t) for t, _, _ in spans)
            out = list(spans)
            if used < width:
                out.append((" " * (width - used), None, False))
            return out
        out = [S("  │ ", BORDER, False)]
        out += fit(a_sp, C1)
        out += [S(" │ ", BORDER, False)]
        out += fit(b_sp, C2)
        out += [S(" │ ", BORDER, False)]
        out += fit(c_sp, C3)
        out += [S(" │", BORDER, False)]
        return out

    vcolor = RED if "confirm" in verdict else GREEN
    return [
        plain(top, BORDER, False),
        row([S(verdict, vcolor, True)],
            [S("- " + before, RED, False)],
            [S("before ", GRAY, False), S(hash_before[:10], MOON, False)]),
        row([S(reason[:C1], GRAY, False)],
            [S("+ " + after, GREEN, False)],
            [S("after  (pending)", DIM, False)]),
        row([S("tier=require_confirm", GRAY, False)],
            [S("unified diff ready", GRAY, False)],
            [S("verify (pending)", DIM, False)]),
        plain(bar, BORDER, False),
    ]


def confirm_menu(command):
    """Claude Code 风格权限确认菜单, 键位来自真实 strings.

    诚实约束: 本软件无"永久免问/自动批准"开关(安全红线), 菜单不列出不存在的功能。
    """
    return [
        line(S("  ⚠ ", YELLOW, True), S("Confirm this change?  ", NAME, True), S("修改类操作默认 N, 需人工确认", GRAY, False)),
        line(S("     " + command[:70], CYAN, False)),
        blank(),
        line(S("  ❯ ", MOON, True), S("[y] 仅本次允许", NAME, False)),
        line(S("    [N] 取消(默认) · [d] 看 diff · [a] 看 AST 理由", GRAY, False)),
        blank(),
        line(S("  每次修改都要确认, 无永久免问开关; 操作前已备份、可回滚", DIM, False)),
    ]


def status_bar(cfg=None, mode="manual"):
    cfg = cfg or {}
    return status(cfg, mode=mode)


def status(cfg=None, mode="manual"):
    """状态栏只展示可从配置/上下文得到的事实, 不放写死的假数字。"""
    cfg = cfg or {}
    backend = cfg.get("backend", "auto")
    return line(
        S("  ✦ OpsGuard ", STAR, True), S(VERSION, GRAY, False), S("  │  ", BORDER, False),
        S("backend: " + str(backend), CYAN, False), S("  │  ", BORDER, False),
        S("mode: " + str(mode), GRAY, False), S("  │  ", BORDER, False),
        S("confirm: N (default)", YELLOW, False),
    )


def input_box(placeholder="message OpsGuard..."):
    W = 72
    inner = pad("  ❯ " + placeholder, W)
    return [
        plain("  ╭" + "─" * W + "╮", BORDER, False),
        line(S("  │", BORDER, False), S(inner, DIM, False), S("│", BORDER, False)),
        plain("  ╰" + "─" * W + "╯", BORDER, False),
    ]


# ---------- 交互式选择菜单（方向键上下切换，Claude Code 风格） ----------
def _menu_label(item):
    return str(item[0] if isinstance(item, (tuple, list)) else item)


def _menu_value(item):
    return item[1] if isinstance(item, (tuple, list)) else item


def _ansi_up(n):
    return "\033[%dA" % n if n > 0 else ""


def _draw_menu(items, cursor, prompt=""):
    """生成菜单 Span 行：当前项 ❯ 高亮、带 [序号]，其余灰。与截图同源。"""
    out = []
    if prompt:
        out.append(line(S("  " + prompt, GRAY, False)))
    for i, item in enumerate(items):
        label = "[%d] %s" % (i + 1, _menu_label(item))
        if i == cursor:
            out.append(line(S("  ❯ ", MOON, True), S(label, NAME, True)))
        else:
            out.append(line(S("    ", DIM, False), S(label, GRAY, False)))
    return out


def _MENU_HINT():
    # 保留"输入序号"字样以兼容既有测试/习惯：方向键与数字都可用。
    return "  ↑↓ 切换 · Enter 确认 · 或输入序号 · Esc 取消"


def _tty_key_gen():
    """真实终端读原始按键，归一为语义键。Windows=msvcrt，Unix=termios。

    语义键集（行编辑 + 菜单共用，消费者各取所需）：
    UP/DOWN/LEFT/RIGHT/HOME/END/DELETE/BACKSPACE/ENTER/ESC/TAB
    CTRL_A/E/K/U/W/P/N/R/L/D/C / ALT_B/F/D / NUM:x / CHAR:x
    """
    if os.name == "nt":
        import msvcrt
        ext = {72: "UP", 80: "DOWN", 75: "LEFT", 77: "RIGHT",
               71: "HOME", 79: "END", 83: "DELETE"}
        ctrl = {"\x01": "CTRL_A", "\x05": "CTRL_E", "\x0b": "CTRL_K",
                "\x15": "CTRL_U", "\x17": "CTRL_W", "\x10": "CTRL_P",
                "\x0e": "CTRL_N", "\x12": "CTRL_R", "\x0c": "CTRL_L",
                "\x18": "CTRL_X", "\x19": "CTRL_Y"}
        alt = {98: "ALT_B", 102: "ALT_F", 100: "ALT_D"}
        while True:
            c = msvcrt.getwch()
            if c in ("\x00", "\xe0"):
                c2 = msvcrt.getwch()
                k = ord(c2) if c2 else 0
                if k in alt and c == "\x00":
                    yield alt[k]
                else:
                    yield ext.get(k, "OTHER")
            elif c in ("\x08", "\x7f"):
                yield "BACKSPACE"
            elif c == "\t":
                yield "TAB"
            elif c == "\r":
                yield "ENTER"
            elif c in ("\x1b", "\x03"):
                yield "ESC"
            elif c in ctrl:
                yield ctrl[c]
            elif c == "\x04":
                yield "CTRL_D"
            elif c.isdigit():
                yield "NUM:" + c
            else:
                yield "CHAR:" + c
    else:
        import tty as _tty
        import termios as _term
        fd = sys.stdin.fileno()
        old = _term.tcgetattr(fd)
        try:
            _tty.setcbreak(fd)
            while True:
                c = sys.stdin.read(1)
                if not c:
                    break
                yield from _parse_escape_stream_char(c, sys.stdin)
        finally:
            _term.tcsetattr(fd, _term.TCSADRAIN, old)


def _parse_escape_stream_char(c, src):
    """把一个字符（必要时继续从 src 读）翻成语义键。tty 与注入流共用。"""
    if c == "\x1b":
        c2 = src.read(1)
        if c2 == "[":
            c3 = src.read(1)
            simple = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT",
                      "H": "HOME", "F": "END"}
            if c3 in simple:
                yield simple[c3]
            elif c3 in ("1", "7"):
                src.read(1)  # 吞掉 ~
                yield "HOME"
            elif c3 in ("4", "8"):
                src.read(1)
                yield "END"
            elif c3 == "3":
                src.read(1)
                yield "DELETE"
            else:
                yield "OTHER"
        elif c2.lower() in ("b", "f", "d"):
            yield {"b": "ALT_B", "f": "ALT_F", "d": "ALT_D"}[c2.lower()]
        elif c2 == "\x1b":
            yield "ESC_ESC"
        else:
            yield "ESC"
    elif c in ("\x08", "\x7f"):
        yield "BACKSPACE"
    elif c == "\t":
        yield "TAB"
    elif c in ("\r", "\n"):
        yield "ENTER"
    elif c in ("\x01", "\x05", "\x0b", "\x15", "\x17", "\x10",
               "\x0e", "\x12", "\x0c", "\x18", "\x19"):
        yield {"\x01": "CTRL_A", "\x05": "CTRL_E", "\x0b": "CTRL_K",
               "\x15": "CTRL_U", "\x17": "CTRL_W", "\x10": "CTRL_P",
               "\x0e": "CTRL_N", "\x12": "CTRL_R", "\x0c": "CTRL_L",
               "\x18": "CTRL_X", "\x19": "CTRL_Y"}[c]
    elif c == "\x03":
        yield "ESC"
    elif c == "\x04":
        yield "CTRL_D"
    elif c.isdigit():
        yield "NUM:" + c
    else:
        yield "CHAR:" + c


def _stream_key_gen(text):
    """注入文本解析成语义键流（测试/管道）：与真终端 _parse_escape_stream_char 同源。"""
    class _S(object):
        def __init__(self, t):
            self.t = t
            self.i = 0
        def read(self, n=1):
            if self.i >= len(self.t):
                return ""
            r = self.t[self.i:self.i + n]
            self.i += n
            return r
    src = _S(text)
    while src.i < len(text):
        for k in _parse_escape_stream_char(src.read(1), src):
            yield k


class LineEditor(object):
    """Claude Code 风格主命令输入行编辑器（纯内存，可注入，不碰真 tty/系统）。

    键位依据（真实取证，见模块 docstring）：官方文档 interactive-mode 的
    Text editing / Command history 表 —— Ctrl+A/E/K/U/W、Alt+B/F/D、
    Up/Down(或 Ctrl+P/N) 翻历史、Backspace/Delete、Ctrl+R 反搜索。
    单行输入不做"多行内先移光标"的分支（我们没有多行输入）。
    """
    def __init__(self, prompt="❯ ", history=None, emit=None, writer=None,
                 key_gen=None, tty=None, vt=None, autosuggest=True):
        self.prompt = prompt
        self.autosuggest = bool(autosuggest) and _suggest is not None
        self.history = list(history or [])       # 最旧 -> 最新
        self.emit = emit or (lambda ls: _out(render(ls) + "\n"))
        self.writer = writer or _out
        self.key_gen = key_gen                   # None => 真终端 _tty_key_gen
        self.tty = bool(sys.stdin.isatty()) if tty is None else tty
        # vt=None 时只在真 tty 上探测；测试注入环境默认 vt=False（用可见标记，
        # 断言稳定，不会因宿主控制台能力不同而漂移）。
        if vt is None:
            vt = _enable_windows_vt() if self.tty else False
        self.vt = bool(vt)
        self.buf = []
        self.cur = 0
        self.hist_idx = None
        self.draft = ""
        self.kill_buf = ""
        self._last_width = 0  # 无 VT 降级渲染时上次绘制宽度(用于覆盖旧行)

    def _text(self):
        return "".join(self.buf)

    def _ghost(self, disp, cursor, search):
        """当前联想的 ghost text（光标在行尾才联想，Minecraft 式）。"""
        if not self.autosuggest or search is not None:
            return ""
        if cursor != len(disp):
            return ""
        try:
            return _suggest.suggest(disp, self.history) or ""
        except Exception:
            return ""

    def _render(self, first=False, search=None):
        disp = self._text()
        cursor = self.cur
        suffix = ""
        if search is not None:
            disp = search.get("base", disp)
            cursor = len(disp)
            suffix = "  (reverse-i-search `%s`: %s)" % (
                search.get("query", ""), search.get("match", ""))
        ghost = self._ghost(disp, cursor, search)
        if self.tty and self.vt:
            # 真正支持 ANSI 光标控制：原地清行重绘 + 定位光标。
            if not first:
                self.writer("\r\x1b[2K")
            self.writer("  " + self.prompt + disp)
            if ghost:
                self.writer("\x1b[38;2;%d;%d;%dm" % GHOST)
                self.writer(ghost)
                self.writer("\x1b[0m")
            self.writer(suffix)
            col = dw(self.prompt) + cursor + 3
            self.writer("\x1b[%dG" % max(1, col))  # 光标停在联想之前 = 淡字在后面
        elif self.tty:
            # Windows conhost 没开 VT：无颜色/定位，用可见光标 │ + 尾注联想。
            # 淡字无法着色，降级成 " (联想:xxx)" 诚实提示，回车采纳后消失。
            text = "  " + self.prompt + disp
            mark = "".join(disp[:cursor]) + "│" + "".join(disp[cursor:])
            hint = (" (联想:%s)" % ghost) if ghost else ""
            self.writer("\r" + " " * max(0, self._last_width) + "\r")
            self.writer("  " + self.prompt + mark + hint + suffix)
            self._last_width = dw(text + hint + suffix)
        else:
            mark = "".join(disp[:cursor]) + "│" + "".join(disp[cursor:])
            spans = [S("  " + self.prompt, NAME), S(mark, NAME)]
            if ghost:
                spans.append(S(ghost, GHOST))
            if suffix:
                spans.append(S(suffix, GRAY))
            self.emit([line(*spans)])

    def _load_hist(self, idx):
        self.hist_idx = idx
        val = self.history[idx] if 0 <= idx < len(self.history) else self.draft
        self.buf = list(val)
        self.cur = len(self.buf)

    def _word_left(self):
        i = self.cur
        while i > 0 and not self.buf[i - 1].isalnum():
            i -= 1
        while i > 0 and self.buf[i - 1].isalnum():
            i -= 1
        return i

    def _word_right(self):
        i = self.cur
        n = len(self.buf)
        while i < n and not self.buf[i].isalnum():
            i += 1
        while i < n and self.buf[i].isalnum():
            i += 1
        return i

    def edit(self):
        """返回提交的行字符串；None = 退出/中断（EOF、Ctrl+C、Ctrl+D 空行）。"""
        if not self.tty and self.key_gen is None:
            line_in = sys.stdin.readline()
            if line_in == "":
                return None
            return line_in.rstrip("\r\n")
        keys = self.key_gen() if callable(self.key_gen) else (self.key_gen or _tty_key_gen())
        self._render(first=True)
        search = None
        for key in keys:
            if key == "ENTER":
                if search is not None:
                    m = search.get("match", "")
                    if m:
                        self.buf = list(m)
                        self.cur = len(self.buf)
                    search = None
                    self._render()
                    continue
                text = self._text()
                # Minecraft 式：有联想且这是第一次回车 → 采纳补全，不执行；
                # 采纳后的文本再按回车（此时词已完整、无联想）才真正提交。
                ghost = self._ghost(text, self.cur, None)
                if ghost and self.autosuggest:
                    self.buf = list(text + ghost)
                    self.cur = len(self.buf)
                    self.hist_idx = None
                    self._render()
                    continue
                if text.strip():
                    if not self.history or self.history[-1] != text:
                        self.history.append(text)
                if self.tty and self.vt:
                    self.writer("\r\x1b[2K")
                    self.writer("  " + self.prompt + text + "\n")
                elif self.tty:
                    # 无 VT：\r + 空格覆盖旧行后写最终文本 + 换行。
                    self.writer("\r" + " " * max(0, self._last_width) + "\r")
                    self.writer("  " + self.prompt + text + "\n")
                return text
            if key in ("ESC", "ESC_ESC", "CTRL_C"):
                if search is not None:
                    search = None
                    self._render()
                    continue
                if key == "CTRL_C":
                    return None
                # 单/双 Esc：清空当前行（草稿不入历史，符合"清空"预期）
                self.buf = []
                self.cur = 0
                self.hist_idx = None
                self.draft = ""
                self._render()
                continue
            if key == "CTRL_D":
                if not self.buf:
                    return None
                if self.cur < len(self.buf):
                    del self.buf[self.cur]
                self._render()
                continue
            if key == "CTRL_R":
                search = {"query": "", "base": self._text(),
                          "match": "", "start": self.hist_idx}
                self._render(search=search)
                continue
            if search is not None:
                if key.startswith("CHAR:") or key.startswith("NUM:"):
                    ch = key.split(":", 1)[1]
                    search["query"] += ch
                    q = search["query"].lower()
                    hit = ""
                    for h in reversed(self.history):
                        if q in h.lower():
                            hit = h
                            break
                    search["match"] = hit
                    self._render(search=search)
                elif key == "BACKSPACE":
                    search["query"] = search["query"][:-1]
                    q = search["query"].lower()
                    hit = ""
                    for h in reversed(self.history):
                        if not q or q in h.lower():
                            hit = h
                            break
                    search["match"] = hit
                    self._render(search=search)
                continue
            if key.startswith("CHAR:") or key.startswith("NUM:"):
                ch = key.split(":", 1)[1]
                self.buf.insert(self.cur, ch)
                self.cur += 1
                self.hist_idx = None
            elif key == "LEFT":
                self.cur = max(0, self.cur - 1)
            elif key == "RIGHT":
                self.cur = min(len(self.buf), self.cur + 1)
            elif key in ("HOME", "CTRL_A"):
                self.cur = 0
            elif key in ("END", "CTRL_E"):
                self.cur = len(self.buf)
            elif key == "UP" or key == "CTRL_P":
                if self.hist_idx is None:
                    self.draft = self._text()
                    if self.history:
                        self._load_hist(len(self.history) - 1)
                elif self.hist_idx > 0:
                    self._load_hist(self.hist_idx - 1)
            elif key == "DOWN" or key == "CTRL_N":
                if self.hist_idx is not None:
                    if self.hist_idx < len(self.history) - 1:
                        self._load_hist(self.hist_idx + 1)
                    else:
                        self.hist_idx = None
                        self.buf = list(self.draft)
                        self.cur = len(self.buf)
            elif key == "BACKSPACE":
                if self.cur > 0:
                    del self.buf[self.cur - 1]
                    self.cur -= 1
                    self.hist_idx = None
            elif key == "DELETE":
                if self.cur < len(self.buf):
                    del self.buf[self.cur]
                    self.hist_idx = None
            elif key == "CTRL_K":
                self.kill_buf = "".join(self.buf[self.cur:])
                self.buf = self.buf[:self.cur]
            elif key == "CTRL_U":
                self.kill_buf = "".join(self.buf[:self.cur])
                self.buf = self.buf[self.cur:]
                self.cur = 0
            elif key == "CTRL_W":
                j = self.cur
                while j > 0 and self.buf[j - 1].isspace():
                    j -= 1
                while j > 0 and not self.buf[j - 1].isspace():
                    j -= 1
                self.kill_buf = "".join(self.buf[j:self.cur])
                del self.buf[j:self.cur]
                self.cur = j
            elif key == "ALT_B":
                self.cur = self._word_left()
            elif key == "ALT_F":
                self.cur = self._word_right()
            elif key == "ALT_D":
                j = self._word_right()
                self.kill_buf = "".join(self.buf[self.cur:j])
                del self.buf[self.cur:j]
            elif key == "CTRL_Y":
                if self.kill_buf:
                    self.buf[self.cur:self.cur] = list(self.kill_buf)
                    self.cur += len(self.kill_buf)
            elif key == "CTRL_L":
                self.writer("\x1b[2J\x1b[H")
            elif key == "TAB":
                pass  # 补全未实现，保留按键不误插字符
            else:
                continue
            self._render()
        return None


def select_menu(items, prompt="选择:", default=0, emit=None, writer=None, key_gen=None, tty=None):
    """方向键上下切换 + 回车确认 + Esc/q 取消的交互菜单（Claude Code 风格）。

    items: [label, ...] 或 [(label, value), ...]；返回 value 或 None（取消/跳过）。
    - tty=True：真终端原始按键循环，writer 发光标控制实现原地重绘；
    - tty=False：从注入文本读，纯数字=序号（兼容旧习惯），含 \\x1b[=方向键按键流；
    - tty=None：按 sys.stdin.isatty() 自动。
    emit(lines)/writer(str)/key_gen 都可注入，便于纯内存测试（不碰真 tty/系统）。
    """
    items = list(items or [])
    if not items:
        return None
    n = len(items)
    if tty is None:
        tty = bool(sys.stdin.isatty())
    if emit is None:
        emit = lambda ls: _out(render(ls) + "\n")
    if writer is None:
        writer = lambda s: _out(s)
    cursor = default % n
    rows = n + (1 if prompt else 0) + 1  # 菜单 + 可选标题 + 提示行

    def draw(erase=False):
        if tty and erase:
            writer(_ansi_up(rows))
        emit(_draw_menu(items, cursor, prompt))
        emit([line(S(_MENU_HINT(), DIM, False))])

    if not tty:
        draw()  # 无论 tty 与否都先把菜单画出来（截图/测试断言依赖菜单行）
        if key_gen is None:
            text = sys.stdin.readline()
            stripped = text.strip()
            if stripped == "":
                emit([line(S("  已跳过，未改动。", DIM, False))])
                return None
            if stripped.isdigit():
                idx = int(stripped)
                if 1 <= idx <= n:
                    return _menu_value(items[idx - 1])
                emit([line(S("  序号无效（1~%d），未改动。" % n, YELLOW, False))])
                return None
            keys = _stream_key_gen(text)
        else:
            keys = iter(key_gen)
        for key in keys:
            if key == "UP":
                cursor = (cursor - 1) % n
            elif key == "DOWN":
                cursor = (cursor + 1) % n
            elif key.startswith("NUM:"):
                idx = int(key[4:])
                if 1 <= idx <= n:
                    cursor = idx - 1
            elif key == "ENTER":
                emit([line(S("  ✓ 已选择 ", GREEN, True), S(_menu_label(items[cursor]), NAME, False))])
                return _menu_value(items[cursor])
            elif key == "ESC":
                emit([line(S("  已取消，未改动。", YELLOW, False))])
                return None
            else:
                continue
            draw()
        return None

    # 真实终端：原始按键循环 + 原地重绘。
    keys = key_gen if key_gen is not None else _tty_key_gen()
    draw()
    for key in keys:
        if key == "UP":
            cursor = (cursor - 1) % n
        elif key == "DOWN":
            cursor = (cursor + 1) % n
        elif key.startswith("NUM:"):
            idx = int(key[4:])
            if 1 <= idx <= n:
                cursor = idx - 1
        elif key == "ENTER":
            writer(_ansi_up(rows))
            emit(_draw_menu(items, cursor, prompt))
            emit([line(S("  ✓ 已选择 " + _menu_label(items[cursor]), GREEN, True))])
            return _menu_value(items[cursor])
        elif key == "ESC":
            writer(_ansi_up(rows))
            emit([line(S("  已取消，未改动。", YELLOW, False))])
            return None
        else:
            continue
        draw(erase=True)  # 方向键改动后原地重绘（上移光标覆盖旧菜单）
    return None


def _do_menu_items():
    """OpsGuard 本身能干的活——一等公民功能菜单。

    每项 = (界面说明文字, 预置的真实样例 argv)。选中后交给 run_repl 统一 dispatch，
    复用折叠/确认状态机/tag 显示。全部走内置样例或隔离夹具，不碰真系统。
    每项 argv 都是真跑过、退出码符合预期的（见正式版测试记录 `/do 功能菜单轮`）。
    """
    sample = ""
    try:
        import glob
        cands = sorted(glob.glob(os.path.join(ROOT, "c1", "out", "*.html")))
        if cands:
            sample = cands[0]
    except Exception:
        pass
    items = [
        ("① 报错排障     只读诊断，给结论和修复建议", ["diagnose", "--sample", "error"]),
        ("② 断网排障     16 类根因决策树（只读）", ["netdiag", "--symptom", "dns", "--top", "3"]),
    ]
    if sample:
        items.append(("③ 报告解读     脱敏 → 规则后端 → 回填 → 展示（离线可跑）", ["explain", "--report", sample, "--backend", "rules"]))
    items += [
        ("④ 带回滚修复   诊断 → AST → 确认 → 备份 → 哈希（演练，不真改）", ["fix", "--sample", "fix"]),
        ("⑤ AST 拦截演示 混淆变体逐条拦（deny 侧证据）", ["astcheck"]),
        ("⑥ 脱敏证据     出网 payload + 映射表", ["sanitize"]),
        ("⑦ 回滚哈希演示 变更 → 备份 → 回滚 → 三方哈希闭环", ["hashdemo"]),
        ("⑧ 拦截矩阵汇总 黄金测试集用例数字", ["selftest"]),
        ("⑨ 环境自检     Python / PowerShell / Pester / Key 状态", ["doctor"]),
        ("⑩ 后端状态     云 / 规则 后端选择", ["backend"]),
        ("⑪ 审计日志     最近 5 条操作", ["audit", "--last", "5"]),
        ("⑫ 生成 --ai 补丁 为既有项目生成（默认只预览，不写回）", ["integrate", "--target", ROOT]),
    ]
    return items


def _handle_do(emit, key_gen=None, tty=None):
    """弹核心功能菜单，返回选中的 argv（tokens）或 None（取消）。"""
    items = _do_menu_items()
    emit([line(S("  ── OpsGuard 能做什么 ", CYAN, True),
               S("· ↑↓ 选 · Enter 用真实样例试跑 · Esc 返回 ──", DIM, False))])
    chosen = select_menu(items, prompt="选一个功能看真实效果:", emit=emit,
                         key_gen=key_gen, tty=tty)
    return list(chosen) if chosen else None


# ---------- 完整演示画面 (内容来自正式版真实运行结果) ----------
def build_demo():
    cfg = {"backend": "rules"}
    L = []
    L += banner(cfg)
    L.append(blank())
    L.append(rule())
    L.append(plain("  /fix  ·  报错排障 / 带回滚修复        /help 查看全部子命令", GRAY, False))
    L.append(rule())
    L.append(blank())
    L += [user_msg("DNS 又指到不可达地址了，帮我看看并修一下")]
    L.append(blank())
    L += [tool_call("diagnose", "scenario=fix  ·  evidence=DNS 203.0.113.254 unreachable")]
    L.append(assistant_msg("诊断完成：DNS 服务器被指向不可达地址 203.0.113.254，建议改回 192.168.1.1。"))
    L.append(blank())
    L += [tool_call("ast_guard", "validate(Set-DnsClientServerAddress …)")]
    L += ast_card(
        "require_confirm",
        "allowlist hit: Set-DnsClientServerAddress",
        "DNS=203.0.113.254 UNREACHABLE",
        "DNS=192.168.1.1 OK",
        "3b7cc9d2d57f623c",
    )
    L.append(blank())
    L += confirm_menu("Set-DnsClientServerAddress -InterfaceIndex 12 -ServerAddresses 192.168.1.1")
    L.append(blank())
    L.append(status_bar(cfg))
    L += input_box()
    L.append(blank())
    return L


# ---------- renderers ----------
def to_text(lines):
    """去色纯文本渲染（无 VT 控制台兜底：不留 \x1b 转义乱码）。"""
    return "\n".join("".join(text for text, _c, _b in ln) for ln in lines)


# 全局 ANSI 能力开关：run_repl 启动时按平台/VT 能力设定。
# 默认 True 保持旧行为（截图/管道 to_html 等不受影响）；真控制台在 VT
# 探测失败时置 False，所有 render 走 to_text。
ANSI_OK = True


def render(lines):
    """按当前终端 ANSI 能力选择渲染：能上色就 to_ansi，否则纯文本。"""
    return to_ansi(lines) if ANSI_OK else to_text(lines)


def to_ansi(lines):
    def esc(rgb, bold):
        s = ""
        if rgb:
            s += "\033[38;2;%d;%d;%dm" % rgb
        if bold:
            s += "\033[1m"
        return s
    out = []
    for ln in lines:
        buf = "\033[0m"
        for text, color, bold in ln:
            buf += esc(color, bold) + text
            if color or bold:
                buf += "\033[0m"
        out.append(buf)
    return "\n".join(out)


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def to_html(lines, title="OpsGuard TUI"):
    """带样式的 HTML - 颜色直接来自 to_ansi 同一份 Span, 截图即真实输出."""
    def esc_html(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    body = []
    for ln in lines:
        spans = []
        for text, color, bold in ln:
            style = ""
            if color:
                style += "color:%s;" % _hex(color)
            if bold:
                style += "font-weight:700;"
            et = esc_html(text)
            if style:
                spans.append('<span style="%s">%s</span>' % (style, et))
            else:
                spans.append(et)
        body.append("".join(spans))
    content = "\n".join(body)
    return (
        '<!doctype html><html lang="zh"><head><meta charset="utf-8">'
        "<style>"
        "*{box-sizing:border-box}html,body{margin:0;padding:0}"
        "body{background:#0d1117;padding:18px 16px;"
        'font-family:"SFMono-Regular",Consolas,"Cascadia Mono","Microsoft YaHei",monospace;'
        "font-size:15px;line-height:1.5;white-space:pre;overflow-x:hidden}"
        "</style></head><body><pre style=\"margin:0;font:inherit;white-space:pre\">"
        + content +
        "</pre></body></html>"
    )


# ---------- 交互式 REPL (像 Claude Code 那样持续对话) ----------
def _captured(dispatcher, tokens):
    """捕获 dispatcher 的 stdout **和 stderr**, 供折叠/展开决定显示摘要还是全文.

    必须同时接 stderr: 子命令的错误提示(如 rollback manifest 不存在、参数错误)
    走 sys.stderr, 若只接 stdout 会漏到真实终端, 破坏 TUI 的界面完整性.
    """
    import io
    import contextlib
    if not dispatcher:
        return 0, ""
    buf = io.StringIO()
    errbuf = io.StringIO()
    rc = 0
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(errbuf):
            rc = dispatcher(tokens)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 0
    out = buf.getvalue()
    err = errbuf.getvalue()
    if err:
        out = (out + err) if out else err
    return rc, out


def _summarize(text):
    """把一段输出压成一行摘要(折叠态显示)."""
    import json
    stripped = text.strip()
    if not stripped:
        return "(no output)"
    try:
        obj = json.loads(stripped)
        for k in ("summary", "finding", "result", "effective_detail", "root_cause"):
            if k in obj and obj[k]:
                return "%s: %s" % (k, str(obj[k])[:56])
        return "json { %s }" % ", ".join(list(obj.keys())[:4])
    except Exception:
        pass
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return first[:60]


def _as_json(text):
    """把一段输出解析成 dict; 失败返回空 dict, 绝不抛异常."""
    import json
    try:
        obj = json.loads(text.strip())
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _with_confirm(tokens):
    """给命令追加 --confirm y, 并去掉旧的 --confirm(避免重复参数)."""
    out = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "--confirm":
            i += 2
            continue
        out.append(tokens[i])
        i += 1
    return out + ["--confirm", "y"]


def _help_lines():
    return [
        plain("  /do  ★ 看 OpsGuard 能做什么（方向键菜单 + 真实样例试跑）", MOON, True),
        plain("  Commands:", NAME, True),
        plain("    diagnose / explain / fix / netdiag / rollback / audit / backend / doctor", GRAY),
        plain("    selftest / astcheck / sanitize / hashdemo / integrate", GRAY),
        plain("  TUI:", NAME, True),
        plain("    /verbose       展开/折叠详细输出 (= Claude Code Ctrl+O)", GRAY),
        plain("    /key add            只填 Key 即可，点一下服务商，地址/模型自动配好", GRAY),
        plain("    /key [list|remove|fetch]  查看/删除 Key、从官方拉实时模型列表", GRAY),
        plain("    /model fetch <服务商>  拉实时模型→标注计费→方向键选一个（推荐）", GRAY),
        plain("    /model prices [服务商]  查官方核价表（本地不出网）", GRAY),
        plain("    /model [use|add|remove]  自由选择执行模型", GRAY),
        plain("    /config [set k v]  查看/设置配置 (持久化到 opsguard.config.json)", GRAY),
        plain("    /mode [manual|readonly]  权限模式(无 auto/bypass: 安全红线)", GRAY),
        plain("    /help  /exit", GRAY),
        plain("  选择菜单: ↑↓ 高亮切换 · Enter 确认 · Esc 取消（也可直接输序号）", GRAY),
        plain("  需确认时: y 确认 / N 取消(默认) / d 看 diff / a 看 AST 理由", GRAY),
        plain("  主命令编辑: ←→ 移光标 · ↑↓ 翻历史 · Home/End · Ctrl+A/E/K/U/W", DIM),
        plain("              Alt+B/F 按词移动 · Ctrl+R 搜历史 · Esc 清空 · 回车提交", DIM),
        plain("  淡字联想: 打字自动联想(MC式灰字) · Enter 采纳 · 再 Enter 执行", DIM),
    ]


def _confirm_menu_lines(info=None):
    """需确认时的菜单. 告知与选项必须和真实行为一致(用户硬要求).

    - mode=DRY-RUN: 明说"不真改/不备份", 绝不写"将真实改动系统".
    - mode=LIVE:    明说"真改系统+操作前备份+可回滚", 并列出目标.
    - 键位用行输入真实键 y/N/d/a, 不写抓不到的 Space/Enter.
    """
    info = info or {}
    mode = info.get("mode", "DRY-RUN")
    command = info.get("command", "")
    target = info.get("target", "")
    if mode == "LIVE":
        head = plain("  ? 执行此修改？将真实改动系统（操作前自动备份、可一键回滚）", NAME, True)
        note = plain("    目标: %s · 生产模式，请核对无误后再确认" % target, YELLOW)
    else:
        head = plain("  ? 这是模拟演练（DRY-RUN）：不会改动你的系统、不备份、不执行", NAME, True)
        note = plain("    确认后仍只展示完整流程；真改需显式加 --live --confirm y", DIM)
    return [
        head,
        line(S("    > ", GREEN, True), S((command[:70] if command else "(命令见 /verbose 展开)"), CYAN)),
        note,
        blank(),
        line(S("    ", None, False), S("[y] 确认  ", NAME, True),
             S("[N] 取消(默认)  ", GRAY, False), S("[d] 看 diff  ", GRAY, False),
             S("[a] 看 AST 理由", GRAY, False)),
        plain("    输入字母后回车 · 默认 N · 无超时自动执行 · 无永久免问开关", DIM, False),
    ]


def _handle_config(raw, cfg, emit):
    import json
    try:
        import config as _c
        path = _c.DEFAULT_CONFIG_PATH
    except Exception:
        emit([plain("  config 模块不可用", YELLOW)])
        return
    parts = raw.split()
    if len(parts) == 1:
        emit([
            plain("  ── config ─────────────────────────────", CYAN),
            plain("  backend        = %s   (auto / cloud / rules)" % cfg.get("backend"), GRAY),
            plain("  confirm_default= no    (安全红线, 不可改)", GRAY),
            plain("  timeout_sec    = %s" % cfg.get("timeout_sec"), GRAY),
            plain("  path           = %s" % path, DIM),
            plain("  用法: /config set <key> <value>", DIM),
        ])
        return
    if len(parts) >= 3 and parts[1] == "set":
        k = parts[2]
        v = parts[3] if len(parts) > 3 else ""
        # confirm_default 恒为 no 是安全红线, 不作为可设置项(避免假开关).
        if k == "confirm_default":
            emit([plain("  confirm_default 恒为 no(默认不执行), 属安全红线不可改。", YELLOW)])
            return
        if k not in ("backend", "timeout_sec"):
            emit([plain("  可设置: backend / timeout_sec (confirm_default 恒为 no)", YELLOW)])
            return
        if k == "timeout_sec":
            try:
                v = int(v)
            except ValueError:
                emit([plain("  timeout_sec 需整数", YELLOW)])
                return
        if k == "backend" and v not in ("auto", "cloud", "rules"):
            emit([plain("  backend 仅 auto/cloud/rules (本地模型已移除)", YELLOW)])
            return
        cfg[k] = v
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            emit([plain("  已写入 %s = %s" % (k, v), GREEN)])
        except Exception as e:
            emit([plain("  写配置失败: %s" % str(e)[:80], RED)])
        return
    emit([plain("  用法: /config 或 /config set <key> <value>", DIM)])


def _keystore_view(emit):
    """显示脱敏后的 Key / 模型清单. 绝不含明文."""
    try:
        import keystore as _ks
        st = _ks.list_keys()
    except Exception as e:
        emit([plain("  Key 仓库读取失败: %s" % str(e)[:100], RED)])
        return
    lines = [plain("  ── API Key（只显头4尾4）────────────────", CYAN)]
    if not st["providers"]:
        lines.append(plain("    (空) 用 /key add <服务商> 添加", GRAY))
    for p in st["providers"]:
        mark = " ◄ 当前" if p["active_model"] else ""
        lines.append(plain("    %-12s %s%s" % (p["provider"], p["key_masked"], mark), NAME))
        lines.append(plain("      base: %s" % p["api_base"], DIM))
        lines.append(plain("      模型: %s" % (", ".join(p["models"]) or "(无)"), GRAY))
    lines.append(plain("    预设服务商: %s" % ", ".join(st["presets"]), DIM))
    lines.append(plain("    完整 Key 永不显示/不入日志。", DIM))
    emit(lines)


def _read_key_secure(prompt):
    """读 Key 明文: tty 用 getpass(不回显), 非 tty 直接读一行.

    提示统一由调用方 emit 到 TUI 界面, 这里不往 stderr 写任何东西
    (getpass 在非 tty 下会往 stderr 写 "Password input may be echoed" 警告, 污染界面).
    """
    if sys.stdin.isatty():
        try:
            import getpass
            return getpass.getpass("")  # 提示已在界面 emit; 这里不重复提示也不写 stderr
        except Exception:
            pass
    line = sys.stdin.readline()
    return line.rstrip("\r\n") if line else ""


def _provider_menu(emit, key):
    """让用户在编号菜单里点一下服务商(只需填 Key, 地址/模型自动带出).

    返回 (provider|None, base|None). 选项顺序固定, 显示每家地址与默认模型.
    这一步是"只给 Key 也能用"的关键: sk- 前缀多家通用, 无法自动区分, 点一下即可.
    """
    import keystore as _ks
    guess, conf, reason = _ks.guess_provider(key)
    if guess and conf in ("high", "medium"):
        emit([plain("  已从 Key 格式识别为 %s（%s）。" % (guess, reason), GREEN)])
        return guess, None
    presets = list(_ks.PRESETS)
    emit([plain("  Key 前缀多家通用（%s），↑↓ 点一下服务商即可，地址和模型我自动配:" % reason, CYAN)])
    # 最后一项是"自定义"，选中后再单独要地址；用 value 元组携带是否自定义标记。
    items = []
    for p in presets:
        info = _ks.PRESETS[p]
        items.append(("%-11s %s  默认模型: %s" %
                      (p, info["api_base"], ", ".join(info["models"])), (p, None)))
    items.append(("自定义（自己填一次地址）", ("__custom__", None)))
    picked = select_menu(items, prompt="选择服务商：", emit=emit)
    if picked is None:
        emit([plain("  已取消。", YELLOW)])
        return None, None
    provider, base = picked
    if provider == "__custom__":
        emit([plain("  自定义：请在下一行输入接口地址（OpenAI 兼容，形如 https://.../v1）：", CYAN)])
        base = sys.stdin.readline().strip()
        if not base.startswith(("http://", "https://")):
            emit([plain("  地址无效，已取消。", YELLOW)])
            return None, None
        return "custom", base
    return provider, None


def _handle_key(raw, emit):
    """TUI 内的 Key 管理: /key /key add [服务商] /key remove <p> /key fetch <p>.

    只填 Key 也能加: 自动识别不出来就弹编号菜单点一下, 地址/模型自动带出.
    Key 明文一律安全读(不回显、不进 argv/历史), 只把脱敏摘要交给用户看.
    """
    import keystore as _ks
    parts = raw.split()
    if len(parts) == 1:
        _keystore_view(emit)
        emit([plain("  用法: /key add（只填 Key，再点一下服务商）· /key remove <服务商> · /key fetch <服务商>", DIM)])
        return
    action = parts[1].lower()
    if action == "add":
        emit([plain("  请在下一行输入 API Key（终端输入不回显）：", CYAN)])
        key = _read_key_secure("")
        if not key:
            emit([plain("  未输入 Key，已取消。", YELLOW)])
            return
        provider = parts[2] if len(parts) > 2 else None
        base = None
        if not provider:
            provider, base = _provider_menu(emit, key)
            if not provider:
                return
        try:
            r = _ks.set_key(provider, key, api_base=base)
            act = "添加" if r["action"] == "added" else "更新"
            emit([plain("  ✓ 已%s %s 的 Key: %s" % (act, provider, r["key_masked"]), GREEN),
                  plain("    接口地址: %s" % (r.get("api_base") or "(空)"), DIM),
                  plain("    当前执行模型: %s/%s" %
                        (r["active"].get("provider"), r["active"].get("model")), CYAN),
                  plain("    地址和模型已自动配好；Key 只存本机、脱敏显示，未进历史/日志。", DIM)])
        except _ks.KeystoreError as e:
            emit([plain("  " + str(e), YELLOW)])
            return
        # 用户核心诉求: 选厂商→发 Key→自动从官方拉实时模型→标注计费→编号选一个.
        # 默认开启(OPSGUARD_KEY_AUTOFETCH=1); 测试设 0 避免假 Key 真出网. 只访问所选那一家.
        if os.environ.get("OPSGUARD_KEY_AUTOFETCH", "1") == "0":
            emit([plain("    (自动拉模型已关闭) 用 /model fetch %s 手动拉取。" % provider, DIM)])
            return
        emit([plain("  正在从官方接口拉取 %s 的实时模型并标注计费（只访问这一家）…" % provider, CYAN)])
        models, why = _ks.fetch_models(provider, key, api_base=r.get("api_base") or base)
        if not models:
            emit([plain("  自动拉模型失败（%s）。Key 已存好，可稍后用 /key fetch %s 重试。" %
                        (why, provider), YELLOW)])
            return
        chosen = _show_models_with_pricing(emit, provider, models, interactive=True)
        for m in models:
            try:
                _ks.add_model(provider, m)
            except _ks.KeystoreError:
                pass
        if chosen:
            try:
                _ks.use_model(provider, chosen)
                emit([plain("  ✓ 执行模型已切换为 %s / %s（/backend 可确认）。" % (provider, chosen), GREEN)])
            except _ks.KeystoreError as e:
                emit([plain("  " + str(e), YELLOW)])
        return
    if action == "remove":
        if len(parts) < 3:
            emit([plain("  用法: /key remove <服务商>", YELLOW)])
            return
        try:
            r = _ks.remove_key(parts[2])
            emit([plain("  ✓ 已删除 %s 的 Key。" % r["provider"], GREEN)])
        except _ks.KeystoreError as e:
            emit([plain("  " + str(e), YELLOW)])
        return
    if action == "fetch":
        if len(parts) < 3:
            emit([plain("  用法: /key fetch <服务商>（从官方 /models 拉实时模型列表）", YELLOW)])
            return
        data = _ks.load()
        info = data["providers"].get(parts[2])
        if not info or not info.get("key"):
            emit([plain("  请先 /key add %s。" % parts[2], YELLOW)])
            return
        emit([plain("  正在从官方接口拉取 %s 的模型列表…" % parts[2], CYAN)])
        models, why = _ks.fetch_models(parts[2], info["key"], api_base=info.get("api_base"))
        if not models:
            emit([plain("  拉取失败（%s）。可手动 /model add %s <模型名>。" % (why, parts[2]), YELLOW)])
            return
        try:
            _ks.add_model(parts[2], models[0])
        except _ks.KeystoreError:
            pass
        emit([plain("  ✓ 拉到 %d 个模型（来源 %s/models）。官方计费标注如下:" %
                    (len(models), info.get("api_base")), GREEN)])
        _show_models_with_pricing(emit, parts[2], models, interactive=False)
        emit([plain("  想挑一个设为执行模型: 用 /model fetch %s（带计费编号选择）。" % parts[2], CYAN)])
        return
    emit([plain("  仅支持 /key /key add /key remove /key fetch", YELLOW)])


def _show_models_with_pricing(emit, provider, models, interactive=False):
    """展示带官方计费标注的模型编号清单；interactive=True 时读一行序号返回所选模型.

    计费来自 pricing.py（官方价格页人工核实）；/models 本身不返回价格，未收录的诚实标注
    "价格以官网为准"，绝不编造。返回选中的 model 或 None。
    """
    import keystore as _ks
    import pricing as _pr
    ann = _pr.annotate(provider, models)
    for ln in _pr.render_lines(provider, ann):
        c = GRAY if ln.startswith(("计费来源", "说明", "提示")) else NAME
        emit([plain("  " + ln, c)])
    if not interactive or not ann:
        return None
    unverified = [a["id"] for a in ann if not a["known"]]
    if unverified:
        emit([plain("  注意: %d 个模型本次未核到官方单价（%s），选它们会用余额，请先看官网价格页。" %
                    (len(unverified), ", ".join(unverified[:4]) + ("…" if len(unverified) > 4 else "")), YELLOW)])
    # 选项标签带计费，值才是 model id；方向键上下切换，回车确认（非 tty 仍可输序号）。
    items = [(a["id"] + "  <%s>  %s" % (a["tier_label"], a["label"]), a["id"]) for a in ann]
    return select_menu(items, prompt="选择执行模型（↑↓ 切换）：", emit=emit)


def _handle_model(raw, emit):
    """TUI 内模型选择: list/use/add/remove/fetch/prices.

    fetch = 从官方拉实时模型→标注计费→编号选一个设为执行模型（一站式）；
    prices = 查本地官方核价表（不出网）。
    """
    import keystore as _ks
    import pricing as _pr
    parts = raw.split()
    if len(parts) == 1:
        _keystore_view(emit)
        emit([plain("  用法: /model fetch <服务商> · /model prices [服务商] · /model use <服务商> <模型>", DIM)])
        return
    action = parts[1].lower()
    if action == "prices":
        provider = parts[2] if len(parts) > 2 else None
        if provider and not _pr.provider_info(provider):
            emit([plain("  未收录 %s 的核价表。可用: %s" %
                        (provider, ", ".join(sorted(_pr.PRICE_TABLE))), YELLOW)])
            return
        if provider:
            ann = _pr.annotate(provider, sorted(_pr.provider_info(provider)["models"]))
            for ln in _pr.render_lines(provider, ann):
                c = GRAY if ln.startswith(("计费来源", "说明", "提示")) else NAME
                emit([plain("  " + ln, c)])
        else:
            emit([plain("  已收录官方核价表（核实 %s）:" % _pr.VERIFIED, CYAN)])
            for p, v in sorted(_pr.PRICE_TABLE.items()):
                emit([plain("    %-11s %d 个模型 · 来源 %s" % (p, len(v["models"]), v["source"]), NAME)])
            emit([plain("  用 /model prices <服务商> 看逐个模型计费。", DIM)])
        return
    if action == "fetch":
        if len(parts) < 3:
            emit([plain("  用法: /model fetch <服务商>（拉实时模型→标计费→编号选一个）", YELLOW)])
            return
        provider = parts[2]
        data = _ks.load()
        info = data["providers"].get(provider)
        key = info["key"] if info else ""
        base = info.get("api_base") if info else None
        if not key:
            emit([plain("  请先 /key add %s。" % provider, YELLOW)])
            return
        emit([plain("  正在从官方接口拉取 %s 的模型列表（只访问这一家）…" % provider, CYAN)])
        models, why = _ks.fetch_models(provider, key, api_base=base)
        if not models:
            emit([plain("  拉取失败（%s）。可手动 /model add %s <模型名>。" % (why, provider), YELLOW)])
            return
        emit([plain("  ✓ 拉到 %d 个模型。下面标注计费后你可挑一个：" % len(models), GREEN)])
        chosen = _show_models_with_pricing(emit, provider, models, interactive=True)
        # 拉到的模型先加入可选清单, 方便后续 use（只读展示不在此写；写需非 readonly, run_repl 已拦）.
        for m in models:
            try:
                _ks.add_model(provider, m)
            except _ks.KeystoreError:
                pass
        if chosen:
            try:
                _ks.use_model(provider, chosen)
                emit([plain("  ✓ 执行模型已切换为 %s / %s（/backend 可确认）。" % (provider, chosen), GREEN)])
            except _ks.KeystoreError as e:
                emit([plain("  " + str(e), YELLOW)])
        return
    if action == "use" and len(parts) >= 4:
        try:
            r = _ks.use_model(parts[2], parts[3])
            emit([plain("  ✓ 执行模型已切换为 %s / %s" % (r["active"]["provider"], r["active"]["model"]), GREEN),
                  plain("    /backend 可确认当前生效情况。", DIM)])
        except _ks.KeystoreError as e:
            emit([plain("  " + str(e), YELLOW)])
        return
    if action == "add" and len(parts) >= 4:
        try:
            r = _ks.add_model(parts[2], parts[3])
            emit([plain("  ✓ 已为 %s 增加模型 %s" % (r["provider"], r["model"]), GREEN)])
        except _ks.KeystoreError as e:
            emit([plain("  " + str(e), YELLOW)])
        return
    if action == "remove" and len(parts) >= 4:
        try:
            r = _ks.remove_model(parts[2], parts[3])
            emit([plain("  ✓ 已从 %s 删除模型 %s" % (r["provider"], r["model"]), GREEN)])
        except _ks.KeystoreError as e:
            emit([plain("  " + str(e), YELLOW)])
        return
    emit([plain("  用法: /model use|add|remove <服务商> <模型>", YELLOW)])


def run_repl(cfg=None, dispatcher=None):
    """宇宙 logo 品牌头 + Claude Code 风格持续交互.

    dispatcher(argv:list[str]) -> int(exit_code), 由 opsguard.main 注入.
    支持: 折叠/展开 verbose、/config 设置、确认菜单、只读权限模式、命令历史.
    """
    global ANSI_OK
    cfg = cfg or {}
    # Windows GBK 控制台下 ❯/月牙等非 ASCII 字符无法编码 → 切 UTF-8(失败则降级)
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # 真控制台若没开 VT：既上不了色也控制不了光标 → 全局走纯文本渲染，
    # 保证 bat 双击的新窗口不会满屏 \x1b 乱码；管道/非 tty 保持 ANSI
    # （下游截图/to_html 仍拿到带色内容）。
    if sys.stdin.isatty():
        ANSI_OK = _enable_windows_vt()
    verbose = False
    perm_mode = "manual"  # manual | readonly; 不提供 auto/bypass(安全红线)
    history = []
    pending = None  # 等待确认: {"tokens": [...], "info": {...}}

    def emit(lines):
        try:
            _out(render(lines) + "\n")
        except Exception:
            pass

    try:
        _out(render(banner(cfg)) + "\n\n")
        _out(render([
            rule(),
            plain("  /do 看功能 · /help 命令 · /verbose 展开折叠(≈Ctrl+O) · /config 设置 · /exit 退出", GRAY),
            rule(),
        ]) + "\n\n")
    except Exception:
        pass
    while True:
        try:
            # 确认态无联想：否则 y/n/d/a 会被当成命令前缀补全（n→netdiag 等），
            # 吃掉用户的选择。命令输入态才开 Minecraft 式淡字联想。
            editor = LineEditor(prompt="❯ ", history=history, emit=emit,
                                writer=lambda txt: _out(txt),
                                autosuggest=(pending is None))
            raw = editor.edit()
            if raw is None:
                _out("\n")
                break
        except (EOFError, KeyboardInterrupt):
            _out("\n")
            break
        raw = raw.strip()
        if not raw:
            continue
        low = raw.lower()

        # ---- 确认状态机: 菜单列出的 y/N/d/a 必须真能响应 ----
        if pending is not None:
            # 确认态也能安全退出(等价于取消), 不把人卡在菜单里.
            if low in ("/exit", "exit", "quit", "/quit"):
                emit([plain("  已退出，未执行任何操作（默认 N）。", YELLOW)])
                break
            if low in ("y", "yes"):
                toks = _with_confirm(pending["tokens"])
                pending = None
                rc, captured = _captured(dispatcher, toks)
                if captured:
                    if verbose:
                        emit([plain(l) for l in captured.rstrip("\n").split("\n")])
                    else:
                        emit([line(S("  ▸ ", DIM), S(_summarize(captured), GRAY), S("   /verbose 展开", DIM))])
                tag = {0: "OK", 1: "CONFIRM", 2: "AST-DENY", 3: "FROZEN", 4: "ARGS", 5: "BACKEND"}.get(rc, str(rc))
                emit([line(S("  [" + tag + "]", GREEN if rc == 0 else (YELLOW if rc == 1 else RED), True))])
                continue
            if low in ("n", "no", ""):
                emit([plain("  已取消，未执行任何操作（默认 N）。", YELLOW)])
                pending = None
                continue
            if low == "d":
                # 真实 diff 是 {"before","after","unified"} 字典; 展示 unified 全文, 不显示键名.
                diff = pending["info"].get("diff")
                lines = [plain("  ── diff（当前 → 预期）──", CYAN)]
                if isinstance(diff, dict):
                    unified = diff.get("unified") or ""
                    if unified:
                        lines += [plain("  " + l) for l in unified.split("\n")]
                    else:
                        lines.append(plain("    before: %s" % diff.get("before", "?"), GRAY))
                        lines.append(plain("    after : %s" % diff.get("after", "?"), GRAY))
                elif isinstance(diff, str) and diff:
                    lines += [plain("  " + l) for l in diff.split("\n")]
                else:
                    lines.append(plain("  (此场景无 diff 数据)", DIM))
                emit(lines)
                continue
            if low == "a":
                reason = pending["info"].get("ast_reason", "") or "(无 AST 理由)"
                emit([plain("  ── AST 判定 ──", CYAN), plain("  verdict: %s" % pending["info"].get("ast_verdict", "?"), GRAY),
                      plain("  reason: " + reason, GRAY)])
                continue
            emit([plain("  请只输入 y / N / d / a（默认 N，取消）。其余输入不生效。", YELLOW)])
            continue

        if low in ("/exit", "exit", "quit", "/quit"):
            break
        if low in ("/help", "help", "?"):
            emit(_help_lines())
            continue
        if low in ("/verbose", "/expand", "/v"):
            verbose = not verbose
            emit([plain("  verbose(展开详细输出) = %s" % ("ON" if verbose else "OFF"), CYAN)])
            continue
        if low == "/mode":
            emit([plain("  权限模式: %s (manual / readonly; 无 auto/bypass——安全红线)" % perm_mode, CYAN)])
            continue
        if low.startswith("/mode "):
            m = low.split()[1] if len(low.split()) > 1 else ""
            if m in ("manual", "readonly"):
                perm_mode = m
                emit([plain("  权限模式已设为: %s" % m, GREEN)])
            else:
                emit([plain("  仅支持 manual / readonly", YELLOW)])
            continue
        if low.startswith("/config"):
            # readonly 只诊断不改任何东西: 连配置文件写入也拦(兑现"只读"承诺).
            if perm_mode == "readonly" and len(raw.split()) >= 3 and raw.split()[1] == "set":
                emit([plain("  [readonly] 只读模式不可改配置。/mode manual 解锁。", YELLOW)])
                continue
            _handle_config(raw, cfg, emit)
            continue
        if low.startswith("/key"):
            # 改 Key 属敏感写操作, readonly 拦下(查看/列表仍允许).
            if perm_mode == "readonly" and len(raw.split()) >= 3 and raw.split()[1].lower() in ("add", "remove"):
                emit([plain("  [readonly] 只读模式不可增删 Key。/mode manual 解锁。", YELLOW)])
                continue
            _handle_key(raw, emit)
            continue
        if low.startswith("/model"):
            if perm_mode == "readonly" and len(raw.split()) >= 3 and raw.split()[1].lower() in ("use", "add", "remove", "fetch"):
                hint = "（看计费用 /model prices，只读）" if raw.split()[1].lower() == "fetch" else ""
                emit([plain("  [readonly] 只读模式不可改模型%s。/mode manual 解锁。" % hint, YELLOW)])
                continue
            _handle_model(raw, emit)
            continue
        if low in ("/do", "do", "/功能", "/func"):
            # 核心能力一等公民入口: 方向键菜单列出 OpsGuard 本身能干的活,
            # 选中后把预置 argv 交给下面的统一 dispatch(折叠/确认/tag 全部复用).
            chosen = _handle_do(emit)
            if not chosen:
                continue
            tokens = chosen
        else:
            tokens = raw.lstrip("/").split()
        # 未知命令先在 TUI 内拦下: 不让 argparse 把 usage/error 打到 stderr 污染界面,
        # 也不要把参数错误(退出码4)误标成 AST-DENY(2).
        if tokens and tokens[0] not in KNOWN_COMMANDS:
            guess = ", ".join(sorted(KNOWN_COMMANDS))
            emit([line(S("  [ARGS] ", RED, True), S("未知命令 '%s'。可用命令: %s；/help 看用法。" % (tokens[0], guess), YELLOW))])
            continue
        if perm_mode == "readonly" and tokens and tokens[0] in ("fix", "rollback", "integrate"):
            emit([plain("  [readonly] 只读模式, %s 被拦截。/mode manual 解锁。" % tokens[0], YELLOW)])
            continue
        try:
            rc, captured = _captured(dispatcher, tokens)
            info = _as_json(captured)
            if captured:
                if verbose:
                    emit([plain(l) for l in captured.rstrip("\n").split("\n")])
                else:
                    emit([line(S("  ▸ ", DIM), S(_summarize(captured), GRAY), S("   /verbose 展开", DIM))])
            tag = {0: "OK", 1: "CONFIRM", 2: "AST-DENY", 3: "FROZEN", 4: "ARGS", 5: "BACKEND"}.get(rc, str(rc))
            c = GREEN if rc == 0 else (YELLOW if rc == 1 else RED)
            emit([line(S("  [" + tag + "]", c, True))])
            if rc == 1:
                # 需确认: 进状态机, 菜单告知必须和 mode 一致, 选项 y/N/d/a 真能响应.
                live = "--live" in tokens
                info["mode"] = "LIVE" if live else "DRY-RUN"
                pending = {"tokens": tokens, "info": info}
                emit(_confirm_menu_lines(info))
        except Exception as e:
            emit([line(S("  [error] " + str(e)[:120], RED, False))])
    return 0


# ---------- 入口 ----------
def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    mode = argv[0] if argv else "demo"
    cfg = {}
    if mode == "--demo" or mode == "demo":
        L = build_demo()
        out = os.path.join(ROOT, "tui-demo.ans")
        html = os.path.join(ROOT, "tui-demo.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(to_ansi(L))
        with open(html, "w", encoding="utf-8") as f:
            f.write(to_html(L))
        # 终端里也直接打印一次
        try:
            _out(to_ansi(L) + "\n")
        except Exception:
            pass
        return 0
    if mode == "--html":
        L = build_demo()
        html = os.path.join(ROOT, "tui-demo.html")
        with open(html, "w", encoding="utf-8") as f:
            f.write(to_html(L))
        print(html)
        return 0
    # 默认: 打印品牌头 + 交互提示 (真实终端里可接 REPL)
    L = banner(cfg) + [blank()] + [status_bar(cfg)]
    try:
        _out(to_ansi(L) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
