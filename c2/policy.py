"""OpsGuard C2 - 权限分级 + 确认门(模拟) -- Python 3.8+ 纯标准库.

消费 AST 三态+理由:
  allow_readonly  -> allow (放行展示; C2 仍不执行)
  require_confirm -> confirm_required (默认 N, 无跳过, 无超时自动执行)
  deny            -> deny (硬拒, 确认门不得覆盖)
C2 确认门只做"展示方案 + 模拟确认流程", 绝不执行任何命令; 执行与回滚属于 C3.
"""
import ast_guard

ALLOW = "allow"
CONFIRM_REQUIRED = "confirm_required"
CONFIRMED = "confirmed"
REJECTED = "rejected"
DENY = "deny"
_YES = {"y", "yes"}


def decide(guard_result, confirm_answer=None):
    """根据 AST 判定给出权限决策. confirm_answer 仅在 require_confirm 时生效.

    confirm_answer=None 或任意非严格 y/yes 表示"默认 N / 未确认"; 不接受跳过开关.
    """
    verdict = guard_result.get("verdict") if isinstance(guard_result, dict) else None
    reason = guard_result.get("reason", "") if isinstance(guard_result, dict) else ""
    if verdict == ast_guard.DENY:
        return {"decision": DENY, "reason": "AST 判定 deny, 硬拒: " + reason,
                "ast_verdict": verdict, "executed": False}
    if verdict == ast_guard.ALLOW_READONLY:
        return {"decision": ALLOW, "reason": "白名单只读, 放行展示(C2 不执行): " + reason,
                "ast_verdict": verdict, "executed": False}
    if verdict == ast_guard.REQUIRE_CONFIRM:
        answer = "" if confirm_answer is None else str(confirm_answer).strip().lower()
        if answer in _YES:
            return {"decision": CONFIRMED, "reason": "模拟确认 = y; 仅授权展示, 执行留待 C3",
                    "ast_verdict": verdict, "executed": False}
        return {"decision": CONFIRM_REQUIRED,
                "reason": "需人工确认, 默认 N; 未确认不进入执行(无跳过/无超时自动执行)",
                "ast_verdict": verdict, "executed": False}
    return {"decision": DENY, "reason": "未知 AST 三态, fail-closed 硬拒",
            "ast_verdict": verdict, "executed": False}


def confirm_gate(guard_result, answer=None):
    """确认门: 返回 (是否通过确认, 决策 dict). deny 永远为 False."""
    d = decide(guard_result, answer)
    return (d["decision"] in (ALLOW, CONFIRMED)), d


if __name__ == "__main__":
    import json
    g = ast_guard.validate("Set-Service -Name Spooler -Status Running")
    for a in (None, "n", "y"):
        print(json.dumps(decide(g, a), ensure_ascii=False))
