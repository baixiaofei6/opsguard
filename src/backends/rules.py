"""离线规则后端 - 无 Key / 无本地模型时的降级 - 复用 c2 已验证诊断引擎.

不包装成"AI", 如实标注"离线规则模式". 输出与云端/本地可对照(同一脱敏出口).
"""
from base import BaseBackend, MODE_RULES
import _bridge  # noqa: F401
import diagnose as _diag
import generate as _gen


class RulesBackend(BaseBackend):
    mode = MODE_RULES

    @property
    def available(self):
        return True  # 永远可用

    def _chat(self, redacted_text, **opts):
        """用 c2 诊断引擎给出结构化结论, 拼成纯文本(占位符不还原前先返回)."""
        scenario = opts.get("scenario") or _diag.SCENARIO_ERROR
        d = _diag.diagnose(redacted_text, scenario)
        proposals = _gen.generate(d)
        lines = ["【离线规则模式 · 未使用 AI 模型】"]
        lines.append(d.get("summary", ""))
        for p in proposals:
            lines.append("- %s：%s" % (p["title"], p["plain_english"]))
            lines.append("  命令(展示,未执行)：%s" % p["command"])
        return "\n".join(lines)


if __name__ == "__main__":
    import config as c
    import diagnose as d
    b = RulesBackend(c.load())
    r = b.ask(d.sample_evidence(d.SCENARIO_ERROR))
    print(r["text"])
