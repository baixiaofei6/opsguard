# -*- coding: utf-8 -*-
"""OpsGuard 正式版 - AI 排障对话引擎 - Python 3.8+ 纯标准库.

用途: 给 CLI/TUI 增加「像 Claude Code 那样跟 AI 对话解决服务器/电脑问题」的能力.
AI 角色被锁定为 Windows/服务器排障专家; 所有对话文本统一走 factory.ask 的脱敏出口,
不绕过 BaseBackend 的 RFC1918 IP/MAC 断言.

安全铁律(不可降级):
- AI 给出的修复动作只是一段「建议」, 必须先过 c2.ast_guard 白名单; deny 硬拒,
  confirm_mode=auto 也不能覆盖 deny.
- confirm_mode=manual: require_confirm 类动作必须人工显式 y 才执行.
- confirm_mode=auto: 跳过「逐次人工问」, 但仍过 AST + 备份 + 哈希 + 失败回滚;
  auto 只省确认动作, 不省任何安全机制.
- 打真靶还是打夹具由 --live 单独控制, 与 confirm_mode 正交; 默认夹具(sandbox).
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_HERE, "backends"), _ROOT,
           os.path.join(_ROOT, "c1"), os.path.join(_ROOT, "c2"), os.path.join(_ROOT, "c3")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ast_guard as _ast
import factory as _factory
import keystore as _keystore

MODE_MANUAL = "manual"
MODE_AUTO = "auto"
CONFIRM_MODES = (MODE_MANUAL, MODE_AUTO)

# AI 角色锁定: 只做服务器/电脑排障, 不臆造, 修复建议必须走白名单命令.
SYSTEM_PROMPT = (
    "你是 OpsGuard 内置的服务器与电脑排障专家，只解决 Windows 系统、网络、服务、"
    "注册表、DNS、网卡等真实运维问题。只依据用户给出的现象与证据回答，不臆造事实；"
    "不确定就说明还需要哪些信息。回答用简洁中文，先给结论，再给依据，最后给处置建议。"
    "如果你认为需要执行一条修复命令，只能在回答末尾输出一个 <opsguard-action> 块，"
    "里面是严格 JSON，字段 command/kind/target/values/reason；command 只能是如下白名单 cmdlet: "
    "Get-Service/Set-Service/Get-DnsClientServerAddress/Set-DnsClientServerAddress/"
    "Get-NetAdapter/ipconfig，禁止编码命令、变量动态拼接、下载执行链、别名、管道到 iex。"
    "kind 只能是 dns/service/registry/file 之一。不需要执行就输出 <opsguard-action>none</opsguard-action>。"
    "任何情况下都不要输出 API Key 或凭据。"
)

_ACTION_RE = re.compile(r"<opsguard-action>\s*(.*?)\s*</opsguard-action>", re.S | re.I)
_VALID_KINDS = ("dns", "service", "registry", "file")


def normalize_confirm_mode(value):
    """非法值退回 manual(安全侧)."""
    v = str(value or "").strip().lower()
    return v if v in CONFIRM_MODES else MODE_MANUAL


def has_ai_key(cfg=None, path=None):
    """是否有可用的云端 AI Key(keystore 或环境变量). 绝不看 key 本体, 只看有无.

    用于 /ai 与 ai 子命令进入对话前的前置提示: 没 Key 时应明确告诉用户先 key add,
    而不是让 auto 静默降级到离线规则模式导致用户以为 AI 没生效.
    """
    r = _keystore.resolve(cfg or {}, path=path)
    return bool(r.get("key"))


NO_KEY_HINT = (
    "当前没有配置 AI Key，AI 对话无法使用。"
    "请先添加 Key：在界面里输 /key add <服务商>（然后按提示粘贴 Key），"
    "或命令行 opsguard key add <服务商>；地址与模型会自动配好。"
    "添加后再输 /ai 进入对话。"
)


def parse_action(reply):
    """从 AI 回复里解析修复建议. 返回 dict 或 None. 解析失败一律 None(fail-closed)."""
    if not reply:
        return None
    m = _ACTION_RE.search(reply)
    if not m:
        return None
    body = m.group(1).strip()
    if not body or body.lower() == "none":
        return None
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    command = str(data.get("command") or "").strip()
    kind = str(data.get("kind") or "").strip().lower()
    target = data.get("target")
    values = data.get("values")
    reason = str(data.get("reason") or "")[:200]
    if not command or kind not in _VALID_KINDS:
        return None
    if not isinstance(values, dict) or not values:
        return None
    # 值全部转字符串, 防 AI 塞结构化对象进 PS 参数.
    vals = dict((str(k)[:40], str(v)[:200]) for k, v in values.items())
    return {
        "command": command[:500],
        "kind": kind,
        "target": str(target)[:200] if target is not None else "",
        "values": vals,
        "reason": reason,
    }


class AIChat(object):
    """多轮排障对话. 文本走脱敏出口; action 走 AST 判定. 不做任何执行."""

    def __init__(self, cfg=None, backend=None):
        self.cfg = cfg or {}
        self.backend = backend or self.cfg.get("backend") or "auto"
        self.messages = []          # [{role,content}] 已回填的本地展示历史

    def send(self, user_text, backend_override=None):
        """发一句, 返回 {reply, action, plan, backend, redaction_applied, mapping_count}.

        plan 是 AST 判定结果(不执行); executable 仅表示「AST 未拒且 kind 合法」,
        真正的执行与否由调用方按 confirm_mode / --live 决定.
        """
        if not user_text or not str(user_text).strip():
            return {"error": "空输入"}
        # 组装带角色锁定的对话上下文. system 提示不进脱敏文本(它不含内网信息);
        # 历史与当前输入一起作为 user 内容走统一脱敏出口.
        context = self._build_context(str(user_text))
        try:
            r = _factory.ask(context, self.cfg, backend_override or self.backend,
                             system=SYSTEM_PROMPT)
        except Exception as e:
            return {"error": str(e)[:160]}
        reply = r.get("text", "")
        action = parse_action(reply)
        plan = None
        if action is not None:
            guard = _ast.validate(action["command"])
            verdict = guard.get("verdict")
            plan = {
                "action": action,
                "ast_verdict": verdict,
                "ast_reason": guard.get("reason", ""),
                "executable": verdict in (_ast.ALLOW_READONLY, _ast.REQUIRE_CONFIRM),
            }
        self.messages.append({"role": "user", "content": str(user_text)})
        self.messages.append({"role": "assistant", "content": reply})
        return {
            "reply": reply,
            "action": action,
            "plan": plan,
            "backend": r.get("backend"),
            "fallback_from": r.get("fallback_from"),
            "redaction_applied": r.get("redaction_applied"),
            "mapping_count": r.get("mapping_count", 0),
        }

    def _build_context(self, current):
        parts = []
        for msg in self.messages[-12:]:   # 只带最近 12 条, 控上下文长度
            role = "用户" if msg.get("role") == "user" else "OpsGuard"
            parts.append("%s: %s" % (role, str(msg.get("content") or "")[:600]))
        parts.append("用户: " + current[:1200])
        return "\n".join(parts)

    def clear(self):
        self.messages = []


def decision_for(plan, confirm_mode, confirm_answer=None, live=False):
    """把 AI 修复计划和确认模式翻译成执行决策(不执行).

    返回 dict: execute(bool)/need_confirm(bool)/reason/live.
    - deny: 永远不执行(即使 auto).
    - manual + require_confirm: 需人工 y, 否则不执行.
    - auto + require_confirm: 免逐次问, 直接执行(仍走备份/哈希/回滚).
    - allow_readonly: 放行.
    """
    mode = normalize_confirm_mode(confirm_mode)
    if not plan or not plan.get("executable"):
        return {"execute": False, "need_confirm": False,
                "reason": "AST 拒绝或无可执行的 AI 建议(plan 为空/deny)", "live": bool(live)}
    verdict = plan.get("ast_verdict")
    if verdict == _ast.ALLOW_READONLY:
        return {"execute": True, "need_confirm": False,
                "reason": "AST 白名单只读, 放行", "live": bool(live)}
    if verdict == _ast.REQUIRE_CONFIRM:
        if mode == MODE_AUTO:
            return {"execute": True, "need_confirm": False,
                    "reason": "auto 信任模式: 免逐次人工确认, 仍走备份/哈希/回滚", "live": bool(live)}
        yes = str(confirm_answer or "").strip().lower() in ("y", "yes")
        return {"execute": bool(yes), "need_confirm": not yes,
                "reason": "manual 模式: 需人工 y 确认" if not yes else "manual 模式: 已获人工 y",
                "live": bool(live)}
    return {"execute": False, "need_confirm": False,
            "reason": "未知 AST 判定, fail-closed", "live": bool(live)}


def execute_plan(plan, decision, sandbox_root=None):
    """按决策执行 AI 修复建议(仅 decision.execute=True 时).

    先 change(带备份/manifest), 若 --rollback 由调用方另行处理; 这里只做受控变更。
    真靶与否由调用方通过 sandbox=not decision['live'] 决定(默认夹具).
    """
    if not decision or not decision.get("execute"):
        return {"executed": False, "reason": "决策未授权执行"}
    action = plan["action"]
    import adapters.system as _adapter
    kw = dict(sandbox=not decision.get("live"), sandbox_root=sandbox_root,
              ast_verdict=plan.get("ast_verdict") or _ast.REQUIRE_CONFIRM)
    if decision.get("live"):
        kw["confirm_answer"] = "y"   # live 只在已获确认(manual y / auto)后走到这里
    try:
        r = _adapter.change(action["kind"], action["target"], action["values"], **kw)
    except Exception as e:
        return {"executed": False, "reason": "执行器异常: %s" % str(e)[:120]}
    return {"executed": True, "result": r, "live": bool(decision.get("live"))}


if __name__ == "__main__":
    demo = parse_action('结论：DNS 指错。\n<opsguard-action>{"command":"Set-DnsClientServerAddress -InterfaceIndex 12 -ServerAddresses (\'192.168.1.1\')","kind":"dns","target":"12","values":{"ServerAddresses":"192.168.1.1"},"reason":"改回正常DNS"}</opsguard-action>')
    print(json.dumps({"parsed": bool(demo), "decision_manual": decision_for(
        {"executable": True, "ast_verdict": "require_confirm"}, MODE_MANUAL, None),
        "decision_auto": decision_for(
            {"executable": True, "ast_verdict": "require_confirm"}, MODE_AUTO)},
        ensure_ascii=False, indent=2))
