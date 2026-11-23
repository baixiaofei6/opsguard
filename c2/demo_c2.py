"""OpsGuard C2 - CLI 演示: 诊断 -> 生成 -> AST 三态 -> 权限分级 -> 方案展示.

全程不执行任何系统命令, 不改任何系统状态. 命令仅作为字符串做 AST 分析与展示.
视觉: 三态标签(颜色 + 中文双通道, NO_COLOR/非TTY 降级为纯文字), 三栏证据卡(AST判定/diff/一句人话).
"""
import os
import sys
import diagnose as diag
import generate as gen
import ast_guard
import policy

_LABEL = {
    "allow_readonly": "[只读]",
    "require_confirm": "[需确认]",
    "deny": "[禁止·已拒]",
    "confirm_required": "[需确认]",
    "confirmed": "[需确认]",
    "allow": "[只读]",
    "rejected": "[禁止·已拒]",
}
_COLOR = {"allow_readonly": "32", "require_confirm": "33", "deny": "31"}


def _use_color():
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def tag(state, color):
    label = _LABEL.get(state, "[" + str(state) + "]")
    if color and state in _COLOR:
        return "\033[" + _COLOR[state] + "m" + label + "\033[0m"
    return label  # no-color 降级: 语义由中文标签承载, 不丢.


def _card(title, lines):
    out = ["  +-- " + title + " " + "-" * max(0, 34 - len(title)) + "+"]
    for line in lines:
        out.append("  | " + line)
    out.append("  +" + "-" * 38 + "+")
    return "\n".join(out)


def _truncate(text, limit=30):
    if len(text) > limit:
        return text[:limit] + "...(" + str(len(text) - limit) + " more lines)"
    return text


def run(scenario=None, confirm_answer=None):
    color = _use_color()
    scenario = scenario or diag.SCENARIO_FIX
    print("=" * 58)
    print("OpsGuard C2 方案展示 (仅诊断与展示, 不执行任何命令)")
    print("=" * 58)
    print("场景: " + scenario + " | 证据: 内置样本")

    diagnosis = diag.diagnose(diag.sample_evidence(scenario), scenario)
    print("\n诊断结论: " + diagnosis["summary"])
    proposals = gen.generate(diagnosis)

    for idx, p in enumerate(proposals, 1):
        guard = ast_guard.validate(p["command"])
        decision = policy.decide(guard, confirm_answer)
        print("\n--- 方案 %d : %s ---" % (idx, p["title"]))
        print("候选命令(字符串, 不执行): " + p["command"])
        print("AST 三态: " + tag(guard["verdict"], color))
        print("权限决策: " + tag(decision["decision"], color))
        print("预期效果: " + p["expected_effect"])
        print(p["backup_hint"])
        print("\n[三栏证据卡]")
        card1 = _card("AST判定", [
            "三态: " + tag(guard["verdict"], color),
            "理由: " + _truncate(guard["reason"], 42),
            "命中: " + _truncate(str(guard["matched_node"]), 42),
        ])
        card2 = _card("diff(unified)", [
            line for line in p["diff"]["unified"].split("\n")
        ])
        card3 = _card("一句人话", [
            _truncate(p["plain_english"], 42),
            "---",
            "备份/回滚哈希: C3 阶段演示",
        ])
        print(card1)
        print(card2)
        print(card3)

    print("\n" + "=" * 58)
    print("说明: 以上命令仅为字符串分析与展示; 确认门为模拟流程(y/N 默认N),")
    print("      不执行、不备份、不回滚。执行与回滚在 C3 阶段。")
    print("=" * 58)


if __name__ == "__main__":
    sc = sys.argv[1] if len(sys.argv) > 1 else diag.SCENARIO_FIX
    run(sc)
