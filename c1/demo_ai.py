#!/usr/bin/env python3
"""OpsGuard C1 · --ai 自包含样本演示（纯标准库）。

流程：样本报告 HTML → 结构化证据 → 脱敏 → 本地规则引擎（无 Key 降级）→ 回填 →
在样本【副本】的 </body> 前追加 <section id="opsguard-ai">，输出到 c1/out/，
绝不写回 samples/ 原件，绝不改造既有项目。

无 Key = 离线规则模式：不发起任何网络请求、不报错、不包装成离线 AI。
demo 仍走一遍脱敏管线，生成"脱敏后 payload 样例"供审计展示（对齐 TASK §4 0:40
展示脱敏卖点上镜），并如实标注"未实际出网"。真实出网链路的任何 payload 必须先过
redact.prepare_outbound()。

这是演示用样本报告；改造既有项目需用户另行授权。
"""
import argparse
import difflib
import html
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact import Redactor, prepare_outbound  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SAMPLES = os.path.join(PROJECT, "samples")
OUT = os.path.join(HERE, "out")

LEVEL_ZH = {"high": "高", "medium": "中", "low": "低"}
LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}
INTENT_ZH = {
    "allow_readonly": "[只读]",
    "require_confirm": "[需确认]",
    "deny": "[禁止·已拒]",
}


def load_sample(path):
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    m = re.search(r'<script[^>]*id="opsguard-evidence"[^>]*>(.*?)</script>', raw, re.S)
    if not m:
        raise ValueError("样本缺少 #opsguard-evidence 结构化证据块: " + path)
    data = json.loads(m.group(1))
    theme = "dark" if re.search(r'data-theme=["\']dark', raw) else "light"
    return raw, data, theme


def extract_evidence(data):
    """结构化证据：确定性地把样本 JSON 归一成结论 + 风险排序素材。"""
    items = []
    for f in data.get("findings", []):
        items.append({
            "id": f.get("id", ""),
            "title": f.get("title", ""),
            "level": f.get("level", "low"),
            "detail": f.get("detail", ""),
            "current": f.get("current", ""),
            "expected": f.get("expected", ""),
            "hint": f.get("hint", ""),
            "intent": f.get("intent", "readonly"),
            "suggest": f.get("suggest", ""),
        })
    items.sort(key=lambda x: LEVEL_ORDER.get(x["level"], 9))
    return {"source": data.get("source", ""), "hosts": list(data.get("hosts", [])), "findings": items}


def prepare_payload(evidence):
    """出网唯一出口：把结构化证据拼成待出网文本并脱敏。

    返回 (脱敏后整体 payload, 逐条脱敏文本列表, redactor)。
    任何真实出网只发送脱敏后 payload；映射表留在 redactor（本地）。
    """
    per_finding = []
    for f in evidence["findings"]:
        per_finding.append(
            "编号:%s 结论:%s 级别:%s 证据:%s 建议:%s" %
            (f["id"], f["title"], f["level"], f["detail"], f["suggest"])
        )
    corpus = "\n".join(per_finding)
    payload, redactor = prepare_outbound(corpus, evidence["hosts"])
    redacted_lines = [redactor.redact(line) for line in per_finding]
    return payload, redacted_lines, redactor


def local_rules(redacted_lines, evidence):
    """无 Key 降级：确定性本地规则引擎，输出与有 Key 同结构，话术含占位符。"""
    count = len(evidence["findings"])
    high = sum(1 for f in evidence["findings"] if f["level"] == "high")
    lines = [
        "当前为本地规则生成，未连接云端模型（离线规则模式）。",
        "本次共 %d 项发现，其中高风险 %d 项。" % (count, high),
        "输入证据已经出网唯一出口脱敏，占位符保留关联关系。",
    ]
    actions = []
    for i, (f, redacted) in enumerate(zip(evidence["findings"], redacted_lines), 1):
        actions.append({
            "rank": i,
            "title": f["title"],
            "level": f["level"],
            "intent": f["intent"],
            "intent_label": INTENT_ZH.get(f["intent"], "[只读]"),
            "redacted": redacted,
            "suggest": f["suggest"],
            "current": f["current"],
            "expected": f["expected"],
            "hint": f["hint"],
        })
    return {"summary": "\n".join(lines), "actions": actions}


def diff_block(current, expected, hint):
    if not current and not expected:
        return "（本项无需配置变更）"
    a = (current or "").splitlines()
    b = (expected or "").splitlines()
    diff = list(difflib.unified_diff(a, b, fromfile="-当前", tofile="+预期", lineterm=""))
    text = "\n".join(diff) if diff else "（无差异）"
    human = "将把接口 %s 的配置从 %s 改为 %s。" % (hint or "目标项", current or "空", expected or "空")
    return "<pre class=\"og-diff\">" + html.escape(text) + "</pre>\n<p class=\"og-human\">" + html.escape(human) + "</p>"


def card(title, label, css_cls, body):
    return (
        '<article class="og-card">'
        '<div class="og-card-h"><span class="og-tag ' + css_cls + '">' + html.escape(label) + '</span>'
        '<strong>' + html.escape(title) + '</strong></div>'
        '<div class="og-card-b">' + body + '</div></article>'
    )


def build_section(result, evidence, theme, redactor, payload):
    css = CSS_DARK if theme == "dark" else CSS_LIGHT
    actions_html = []
    for a in result["actions"]:
        z = INTENT_ZH.get(a["intent"], "[只读]")
        css_cls = {"[只读]": "ro", "[需确认]": "confirm", "[禁止·已拒]": "deny"}.get(z, "ro")
        lvl = LEVEL_ZH.get(a["level"], a["level"])
        human = redactor.restore(a["redacted"])
        cards = "".join([
            card("三态判定", z, css_cls,
                 "风险等级：" + html.escape(lvl) + "<br>命中节点：证据 " + html.escape(a["title"])),
            card("配置 diff", z if a["intent"] != "require_confirm" else "[需确认]",
                 "confirm" if a["intent"] == "require_confirm" else "ro",
                 diff_block(a["current"], a["expected"], a["hint"])),
            card("回滚证据", "[日志]", "log",
                 "本阶段为样本演示，真实三方哈希验证在 C3 提供。"
                 "<br><br><span class=\"og-muted\">预演不是沙箱。</span>"),
        ])
        actions_html.append(
            '<div class="og-finding"><h3>' + html.escape(a["title"]) + '</h3>'
            '<p class="og-human">一句话：' + html.escape(human) + '</p>'
            '<div class="og-cards">' + cards + '</div></div>'
        )

    restored_summary = redactor.restore(result["summary"])
    suggestions = redactor.restore("\n".join(a["suggest"] for a in result["actions"]))
    payload_display = html.escape(payload)  # 展示脱敏后 payload（占位符），供审计

    return (
        '<section id="opsguard-ai" data-theme="' + theme + '">'
        '<style>' + css + '</style>'
        '<div class="og-wrap">'
        '<h2>OpsGuard · AI 报告解读 <span class="og-badge">样本演示</span></h2>'
        '<p class="og-note">样本，非真实项目产物。本段落为 C1 演示追加，'
        '改造既有项目需用户另行授权。</p>'
        '<p class="og-mode">离线规则模式（无 Key）：未连接云端模型、未实际出网、脱敏不报错；'
        '下列 payload 为脱敏管线样例，证明若有 Key 出网内容不含原始 IP/MAC/主机名。</p>'
        '<div class="og-summary"><strong>人话总结</strong><pre>' + html.escape(restored_summary) + '</pre></div>'
        '<div class="og-risk"><strong>风险排序</strong><ol>' +
        "".join('<li>' + html.escape(a["title"]) + '（' + html.escape(LEVEL_ZH.get(a["level"], a["level"])) + '）</li>'
                for a in result["actions"]) +
        '</ol></div>'
        '<div class="og-actions"><strong>建议动作</strong><pre>' + html.escape(suggestions) + '</pre></div>'
        '<details class="og-payload"><summary>出网 payload（脱敏后，供审计）</summary><pre>' +
        payload_display + '</pre></details>'
        '<div class="og-findings">' + "".join(actions_html) + '</div>'
        '<p class="og-foot">' + html.escape("生成时间 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
            " · 本地规则引擎 · 零依赖") + '</p>'
        '</div></section>'
    )


CSS_BASE = (
    '#opsguard-ai{font-family:system-ui,Segoe UI,sans-serif;margin:2rem 0;border-radius:10px;padding:1.2rem;}'
    '#opsguard-ai .og-wrap{max-width:1100px;margin:auto;}'
    '#opsguard-ai h2{margin:0 0 .4rem;font-size:1.35rem;}'
    '#opsguard-ai .og-badge{font-size:.72rem;border:1px solid currentColor;border-radius:999px;padding:1px 8px;vertical-align:middle;}'
    '#opsguard-ai pre{white-space:pre-wrap;word-break:break-word;padding:.7rem;border-radius:6px;margin:.3rem 0 0;}'
    '#opsguard-ai .og-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem;}'
    '#opsguard-ai .og-card{border:1px solid;border-radius:8px;padding:.7rem;min-width:0;}'
    '#opsguard-ai .og-card-h{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-bottom:.4rem;}'
    '#opsguard-ai .og-tag{font-size:.75rem;border-radius:4px;padding:1px 6px;border:1px solid currentColor;}'
    '#opsguard-ai .og-human{font-size:.9rem;margin:.3rem 0;}'
    '#opsguard-ai .og-diff{font-family:Consolas,monospace;font-size:.8rem;}'
    '#opsguard-ai .og-muted{opacity:.7;}'
    '#opsguard-ai .og-finding{border-top:1px dashed;padding:.9rem 0;}'
    '#opsguard-ai .og-summary,#opsguard-ai .og-risk,#opsguard-ai .og-actions,#opsguard-ai .og-payload{margin:.8rem 0;}'
    '#opsguard-ai .og-note,#opsguard-ai .og-mode,#opsguard-ai .og-foot{font-size:.82rem;opacity:.85;}'
    '@media print{#opsguard-ai .og-cards{grid-template-columns:1fr;}}'
)
CSS_LIGHT = CSS_BASE + (
    '#opsguard-ai{background:#eef4fb;color:#1f2933;border:1px solid #c7d7e8;}'
    '#opsguard-ai pre,#opsguard-ai .og-card{background:#fff;border-color:#d0d7de;}'
    '#opsguard-ai .og-tag.ro{color:#176b3a;}#opsguard-ai .og-tag.confirm{color:#8a5a00;}'
    '#opsguard-ai .og-tag.deny{color:#a11;}#opsguard-ai .og-tag.log{color:#44546a;}'
)
CSS_DARK = CSS_BASE + (
    '#opsguard-ai{background:#111c28;color:#d7e0ea;border:1px solid #24384b;}'
    '#opsguard-ai pre,#opsguard-ai .og-card{background:#16212e;border-color:#24384b;}'
    '#opsguard-ai .og-tag.ro{color:#5fd08a;}#opsguard-ai .og-tag.confirm{color:#f0c75e;}'
    '#opsguard-ai .og-tag.deny{color:#ff7b7b;}#opsguard-ai .og-tag.log{color:#9fb3c8;}'
)


def write_output(raw, section, source_name):
    os.makedirs(OUT, exist_ok=True)
    stem = os.path.splitext(os.path.basename(source_name))[0]
    dest = os.path.join(OUT, stem + ".ai.html")
    marker = re.compile(r'</body>', re.I)
    if not marker.search(raw):
        raise ValueError("样本缺少 </body>: " + source_name)
    final = marker.sub(lambda m: section + "\n" + m.group(0), raw, count=1)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(final)
    return dest


def run_one(sample_path, key_mode=False):
    raw, data, theme = load_sample(sample_path)
    evidence = extract_evidence(data)
    if key_mode:
        raise RuntimeError("C1 样本演示只实现无 Key 降级路径；有 Key 云端模式不在本阶段实现。")
    payload, redacted_lines, redactor = prepare_payload(evidence)  # 脱敏（出网唯一出口）
    result = local_rules(redacted_lines, evidence)                  # 本地规则引擎
    section = build_section(result, evidence, theme, redactor, payload)  # 回填 + 追加段
    return write_output(raw, section, sample_path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="OpsGuard C1 --ai 自包含样本演示（离线规则模式）")
    ap.add_argument("--sample", help="单个样本 HTML 路径；默认处理 samples/ 下全部样本")
    ap.add_argument("--with-key", action="store_true",
                    help="有 Key 云端模式（C1 未实现，显式给出会明确报错，不静默包装）")
    args = ap.parse_args(argv)
    if args.with_key:
        print("C1 样本演示只覆盖无 Key 离线规则模式；有 Key 模式属后续阶段。", file=sys.stderr)
        return 2
    files = ([args.sample] if args.sample else [
        os.path.join(SAMPLES, "sample-lan-ops-scan.html"),
        os.path.join(SAMPLES, "sample-windeploy.html"),
    ])
    for path in files:
        dest = run_one(path, key_mode=False)
        print("生成：" + dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
