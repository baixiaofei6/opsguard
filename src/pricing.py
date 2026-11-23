# -*- coding: utf-8 -*-
"""官方模型计费核价表 + 标注工具（零依赖）。

设计原则（重要）：
- /models 接口只返回模型 id，不返回价格。所以计费标注来自"官方价格页人工核实整理"，
  每个数字都能追到 source 链接，verified 记录核实日期；没查到数字的如实标注
  "以官网为准"+链接，绝不编造单价。
- 本表是"参考快照"，价格随时会变；真正扣费以厂商账单为准。
- 只做数据查询与标注，不发起网络请求、不碰系统、不读 Key。

核价表来源（2026-11-23 真查）：
- DeepSeek: https://api-docs.deepseek.com/zh-cn/quick_start/pricing
- 智谱 GLM: https://docs.bigmodel.cn/cn/guide/start/pricing
- Kimi/Moonshot: https://platform.kimi.com/docs/pricing/chat （数字表在动态块，本页未逐条抓到）
- 阿里云百炼: https://help.aliyun.com/zh/model-studio/models （模型清单页，单价需进各模型详情页）
- OpenAI: https://openai.com/api/pricing/ （商业页，API 单价需 platform 页）
"""
from __future__ import annotations

import re

# 核实日期与货币单位
VERIFIED = "2026-11-23"
UNIT = "CNY / 百万 tokens"

# 每家：source 链接 + verified + models 映射（模型名 -> 标注信息）
# tier: free(免费) / paid(付费) / unknown(未核实单价)
# label: 面向用户的简短计费说明（人话）
# input/output/hit: 数字仅用于机器可读展示，取自官方页；None 表示未抓到。
PRICE_TABLE = {
    "deepseek": {
        "source": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing",
        "verified": VERIFIED,
        "unit": UNIT,
        "note": "高峰=北京时间工作日9-12/14-18；空闲=其余时段及周末节假日。价格为输入(缓存命中/未命中)与输出分开计。",
        "models": {
            "deepseek-flash": {
                "tier": "paid", "input": 1.0, "hit": 0.02, "output": 4.0,
                "peak_hit": 0.04, "peak_input": 2.0, "peak_output": 8.0,
                "label": "空闲: 输入¥1/百万(命中¥0.02)·输出¥4/百万；高峰×2",
            },
            "deepseek-v4-pro": {
                "tier": "paid", "input": 4.5, "hit": 0.15, "output": 13.5,
                "peak_hit": 0.30, "peak_input": 9.0, "peak_output": 27.0,
                "label": "空闲: 输入¥4.5/百万(命中¥0.15)·输出¥13.5/百万；高峰×2",
            },
            # 旧名官方说明已下线(请求由 flash 接管并按 flash 计费)，保留别名标注
            "deepseek-v4-flash": {
                "tier": "paid", "input": 1.0, "hit": 0.02, "output": 4.0,
                "label": "旧名已下线，由 deepseek-flash 按 flash 价计费",
                "alias_of": "deepseek-flash",
            },
        },
    },
    "zhipu": {
        "source": "https://docs.bigmodel.cn/cn/guide/start/pricing",
        "verified": VERIFIED,
        "unit": UNIT,
        "note": "元/百万 tokens；缓存存储限时免费。GLM-5.x 价格取自官方 pricing 页的最新模型表与文本模型表。",
        "models": {
            "glm-5.3": {"tier": "paid", "input": 8.0, "hit": 2.0, "output": 28.0,
                        "label": "输入¥8/百万·输出¥28/百万·命中¥2/百万"},
            "glm-5.3-flash": {"tier": "paid", "input": 0.8, "hit": 0.23, "output": 2.8,
                              "label": "输入¥0.8/百万·输出¥2.8/百万·命中¥0.23/百万（Flash 便宜档）"},
            "glm-5.3-flashx": {"tier": "paid", "input": 2.0, "hit": 0.57, "output": 7.0,
                               "label": "输入¥2/百万·输出¥7/百万·命中¥0.57/百万"},
            "glm-5.3-flashx-legal": {"tier": "paid", "input": 2.0, "hit": 0.57, "output": 7.0,
                                     "label": "输入¥2/百万·输出¥7/百万·命中¥0.57/百万（法律优化）"},
            "glm-5.2": {"tier": "paid", "input": 8.0, "hit": 2.0, "output": 28.0,
                        "label": "输入¥8/百万·输出¥28/百万·命中¥2/百万"},
            "glm-5.1": {"tier": "paid", "input": 6.0, "hit": 1.3, "output": 24.0,
                        "label": "<32K: 输入¥6/百万·输出¥24/百万；≥32K 涨至¥8/¥28"},
            "glm-5-turbo": {"tier": "paid", "input": 5.0, "hit": 1.2, "output": 22.0,
                            "label": "<32K: 输入¥5/百万·输出¥22/百万；≥32K 涨至¥7/¥26"},
            "glm-5": {"tier": "paid", "input": 4.0, "hit": 1.0, "output": 18.0,
                      "label": "<32K: 输入¥4/百万·输出¥18/百万；≥32K 涨至¥6/¥22"},
            # 实测免费档（此前真 Key 跑 glm-4-flash 成功、未扣费）；本次 pricing 页未逐条列价
            "glm-4-flash": {"tier": "free", "input": None, "hit": None, "output": None,
                            "label": "免费档（实测该 Key 可调用且不扣费）"},
            "glm-4.7-flash": {"tier": "free", "input": None, "hit": None, "output": None,
                              "label": "免费档（官方文档标长期免费）"},
        },
    },
    "moonshot": {
        "source": "https://platform.kimi.com/docs/pricing/chat",
        "verified": VERIFIED,
        "unit": UNIT,
        "note": "Kimi K3.1 Pro/K3 输入按量计费+缓存命中优惠，批量推理为标准价60%。本次抓取的页面未逐条返回单价数字，具体价格以官网表格为准。",
        "models": {
            "kimi-k3.1-pro": {"tier": "unknown", "input": None, "hit": None, "output": None,
                              "label": "按量计费，具体单价以官网为准（批量60%）"},
            "kimi-k3.1-pro-highspeed": {"tier": "unknown", "input": None, "hit": None, "output": None,
                                        "label": "按量计费，具体单价以官网为准"},
            "kimi-k3": {"tier": "unknown", "input": None, "hit": None, "output": None,
                        "label": "按量计费，具体单价以官网为准（批量60%）"},
            "kimi-k2.5": {"tier": "unknown", "input": None, "hit": None, "output": None,
                          "label": "K2 系列将下线，价格以官网为准"},
        },
    },
    "dashscope": {
        "source": "https://help.aliyun.com/zh/model-studio/models",
        "verified": VERIFIED,
        "unit": UNIT,
        "note": "百炼提供千问及第三方模型，单价在各模型详情页；本次仅抓到模型清单页，具体价格以官网详情页为准。新用户常有免费额度。",
        "models": {
            "qwen4-max": {"tier": "unknown", "input": None, "hit": None, "output": None,
                          "label": "单价以官网详情页为准（新用户常有免费额度）"},
            "qwen3.7-plus": {"tier": "unknown", "input": None, "hit": None, "output": None,
                             "label": "单价以官网详情页为准"},
            "qwen3.8-flash": {"tier": "unknown", "input": None, "hit": None, "output": None,
                              "label": "Flash 低档，单价以官网详情页为准"},
            "qwen-plus": {"tier": "unknown", "input": None, "hit": None, "output": None,
                          "label": "单价以官网详情页为准"},
            "qwen-turbo": {"tier": "unknown", "input": None, "hit": None, "output": None,
                           "label": "单价以官网详情页为准"},
            "qwen-max": {"tier": "unknown", "input": None, "hit": None, "output": None,
                         "label": "单价以官网详情页为准"},
        },
    },
    "openai": {
        "source": "https://openai.com/api/pricing/",
        "verified": VERIFIED,
        "unit": "USD / 百万 tokens",
        "note": "OpenAI 按 USD 计费；商业定价页未逐条返回 API 单价数字，具体价格以 platform 定价页为准。",
        "models": {
            "gpt-4o-mini": {"tier": "unknown", "input": None, "hit": None, "output": None,
                            "label": "低价档，USD 按量计费，单价以官网为准"},
            "gpt-4o": {"tier": "unknown", "input": None, "hit": None, "output": None,
                       "label": "USD 按量计费，单价以官网为准"},
            "gpt-4.1-mini": {"tier": "unknown", "input": None, "hit": None, "output": None,
                             "label": "USD 按量计费，单价以官网为准"},
        },
    },
}

_TIER_LABEL = {"free": "免费", "paid": "付费", "unknown": "价格待核实"}


def _valid(model):
    return isinstance(model, str) and bool(re.match(r"^[A-Za-z0-9_.:/-]{1,80}$", model))


def provider_info(provider):
    """返回某服务商的核价表元信息（不含模型明细）；未收录返回 None。"""
    return PRICE_TABLE.get(str(provider).lower().strip())


def model_price(provider, model):
    """查单个模型的标注信息；未收录返回 None（调用方据此标"以官网为准"）。"""
    p = PRICE_TABLE.get(str(provider).lower().strip())
    if not p:
        return None
    m = p["models"].get(str(model).strip().lower())
    if m:
        return dict(m)
    # 大小写不敏感兜底
    for k, v in p["models"].items():
        if k.lower() == str(model).strip().lower():
            return dict(v)
    return None


def annotate(provider, models):
    """把实时拉取的模型 id 列表标注计费。

    返回 [{"id","tier","tier_label","label","source","verified","known"}...]，顺序与输入一致。
    未收录的模型 known=False，label 明确写"价格以官网为准"，不编造。
    """
    provider = str(provider).lower().strip()
    p = PRICE_TABLE.get(provider)
    source = p["source"] if p else ""
    verified = p["verified"] if p else ""
    out = []
    seen = set()
    for raw in models or []:
        if not _valid(raw) or raw in seen:
            continue
        seen.add(raw)
        info = model_price(provider, raw)
        if info:
            out.append({
                "id": raw,
                "tier": info.get("tier", "unknown"),
                "tier_label": _TIER_LABEL.get(info.get("tier", "unknown"), "价格待核实"),
                "label": info.get("label", ""),
                "source": source,
                "verified": verified,
                "known": True,
            })
        else:
            out.append({
                "id": raw,
                "tier": "unknown",
                "tier_label": _TIER_LABEL["unknown"],
                "label": "价格以官网为准（本次核价表未收录该模型）",
                "source": source,
                "verified": verified,
                "known": False,
            })
    return out


def render_lines(provider, annotated, with_index=True):
    """把 annotate() 结果渲染成终端/微信可读的行（人话、克制、对齐）。"""
    lines = []
    p = PRICE_TABLE.get(str(provider).lower().strip())
    if p:
        lines.append("计费来源: %s（核实 %s）" % (p["source"], p["verified"]))
        if p.get("note"):
            lines.append("说明: " + p["note"])
    else:
        lines.append("该服务商未收录官方核价表，价格以官网账单为准。")
    for i, it in enumerate(annotated, 1):
        prefix = "[%d] " % i if with_index else "- "
        lines.append("%s%s  <%s>  %s" % (prefix, it["id"], it["tier_label"], it["label"]))
    lines.append("提示: /models 只返回模型名不返回价格；以上价格来自官方价格页人工核实，实际扣费以账单为准。")
    return lines


if __name__ == "__main__":
    import json
    demo = annotate("deepseek", ["deepseek-flash", "deepseek-v4-pro", "some-new-model"])
    print(json.dumps(demo, ensure_ascii=False, indent=2))
