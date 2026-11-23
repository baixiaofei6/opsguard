#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpsGuard TUI 命令联想引擎（Minecraft 风格淡字补全），Python 3.8+ 零依赖纯函数。

设计：
- 每输入一个字母，按「当前 token 前缀」从命令词库里联想最相关的一条，
  返回需要补到光标后的剩余部分（ghost text，淡字显示）。
- 回车采纳 ghost（补全成完整词），再次回车才执行——Minecraft 式直觉。
- 词库与 TUI 的 KNOWN_COMMANDS / opsguard.py 的 add_subparsers 对齐；
  不引入任何网络/系统访问，可纯内存单测。

公开 API：
    suggest(text, history=None) -> str   返回要给当前输入补的剩余串（无联想则 ""）
    candidates(text, history=None) -> list[str]  返回所有前缀匹配的候选全词（调试/测试用）
"""
from __future__ import print_function

# 顶层业务命令，按常用度排序（联想冲突时靠前优先）；与 build_parser 对齐。
TOP_COMMANDS = [
    "diagnose", "explain", "fix", "netdiag", "rollback", "audit",
    "backend", "doctor", "selftest", "astcheck", "sanitize", "hashdemo",
    "integrate", "key", "model",
]

# TUI 斜杠命令。
TUI_COMMANDS = [
    "/verbose", "/config", "/mode", "/help", "/exit",
]

# 二级子命令（第一个 token 命中后用）。
SUBCOMMANDS = {
    "key": ["list", "suggest", "add", "remove", "fetch"],
    "model": ["list", "add", "remove", "use", "fetch", "prices"],
}

# 每个命令的一级参数开关（打完命令 + 空格后联想常见 flag）。
FLAGS = {
    "fix": ["--sample", "--live", "--confirm", "--backend", "--target"],
    "diagnose": ["--report", "--backend"],
    "explain": ["--report", "--backend"],
    "netdiag": ["--symptom", "--catalog", "--top"],
    "audit": ["--last"],
    "model": ["fetch", "prices", "use", "list"],
    "key": ["add", "list", "remove", "fetch", "suggest"],
}


def _dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _pool(tokens, trailing_space):
    """返回当前应匹配的候选全词列表。"""
    if not tokens:
        return _dedup(TUI_COMMANDS + TOP_COMMANDS)
    first = tokens[0]
    if len(tokens) == 1 and not trailing_space:
        # 正在输入第一个词：斜杠命令优先，其次业务命令。
        if first.startswith("/"):
            return list(TUI_COMMANDS)
        return _dedup(TOP_COMMANDS + TUI_COMMANDS)
    # 已进入第一个命令的参数区：补它的 flag 与子命令（去重）
    return _dedup(FLAGS.get(first, []) + SUBCOMMANDS.get(first, []))


def candidates(text, history=None):
    """返回当前输入前缀匹配到的所有候选全词。"""
    raw = text if isinstance(text, str) else ""
    trailing = raw.endswith(" ")
    tokens = raw.strip().split()
    if not tokens:
        return []
    last = "" if trailing else tokens[-1]
    pool = _pool(tokens, trailing)
    # 正在输入的 token：前缀匹配（Minecraft 式），不把已完整输入的词再当候选。
    matched = [w for w in pool if w.startswith(last) and w != last]
    # 相关性排序：历史里出现过的优先，其次词库顺序（pool 已排好）。
    freq = {}
    for h in (history or []):
        for t in str(h).split():
            freq[t] = freq.get(t, 0) + 1
    if freq:
        matched.sort(key=lambda w: (-freq.get(w, 0), pool.index(w) if w in pool else 999))
    return matched


def suggest(text, history=None):
    """返回应补到光标后的剩余串（ghost text）；无联想返回 ''。"""
    raw = text if isinstance(text, str) else ""
    if not raw.strip():
        return ""
    trailing = raw.endswith(" ")
    tokens = raw.strip().split()
    last = "" if trailing else tokens[-1]
    cands = candidates(raw, history)
    if not cands:
        return ""
    best = cands[0]
    if trailing:
        return best  # 补一个空格后的下一个词
    return best[len(last):]  # 只补当前 token 的剩余部分
