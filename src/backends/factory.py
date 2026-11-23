"""AI 后端工厂 - 按配置/参数选择并支持 auto 降级链 - 纯标准库.

auto: cloud(有Key) -> rules(兜底, 离线规则模式).
本地模型后端已按用户 2026-11-23 决定彻底移除。
降级时每个候选都重新走 BaseBackend.ask() 的完整脱敏出口.
可插拔: 新增后端实现 BaseBackend 并在 _REGISTRY 注册即可.
"""
import os
import sys

_S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src
_B = os.path.join(_S, "backends")
for _p in (_B, _S):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config as _config
import keystore as _keystore
from base import BackendError, MODE_CLOUD, MODE_RULES
from cloud import CloudBackend
from rules import RulesBackend

_REGISTRY = {
    MODE_CLOUD: CloudBackend,
    MODE_RULES: RulesBackend,
}


def build(mode, cfg=None, hosts=None, resolved=None):
    cls = _REGISTRY.get(mode)
    if cls is None:
        raise BackendError("未知后端: %s" % mode)
    # resolved 仅 CloudBackend 消费; 其它后端 __init__ 不接受第三参, 故分流
    if mode == MODE_CLOUD and resolved is not None:
        return cls(cfg, hosts, resolved=resolved)
    return cls(cfg, hosts)


def status(cfg=None, override=None):
    """返回各后端状态 dict(供 backend 子命令 / doctor 用)."""
    cfg = cfg or _config.load()
    out = {}
    for mode in (MODE_CLOUD, MODE_RULES):
        b = build(mode, cfg)
        out[mode] = {"available": bool(b.available), "mode": mode}
    resolved = _keystore.resolve(cfg)
    out[MODE_CLOUD]["key_configured"] = bool(resolved["key"])
    out[MODE_CLOUD]["key_source"] = resolved["source"]
    out[MODE_CLOUD]["model"] = resolved["model"]
    out[MODE_CLOUD]["api_base"] = resolved["api_base"]
    out["effective"] = _config.effective_backend(cfg, override)
    # 人话解释(GLM P1-4): 当前实际会用哪个后端, 为什么
    eff = out["effective"]
    if eff == "auto":
        chosen = MODE_CLOUD if out[MODE_CLOUD]["available"] else MODE_RULES
        if chosen == MODE_CLOUD:
            reason = "已配置 API Key (%s, 模型 %s)" % (resolved["source"], resolved["model"])
        else:
            reason = "云端未配 Key, 已如实降级到离线规则模式"
        out["effective_detail"] = "当前将使用：%s（%s）" % (chosen, reason)
    else:
        extra = (" — 模型 %s (%s)" % (resolved["model"], resolved["source"])) if eff == MODE_CLOUD else ""
        out["effective_detail"] = "当前将使用：%s（用户显式指定%s）" % (eff, extra)
    return out


def ask(text, cfg=None, override=None, hosts=None, **opts):
    """统一入口: 选后端 -> ask(); auto 下失败自动降级. 返回结果 dict 附带 backend 实际值。"""
    cfg = cfg or _config.load()
    mode = _config.effective_backend(cfg, override)
    if mode != "auto":
        result = build(mode, cfg, hosts).ask(text, **opts)
        result["fallback_from"] = None
        return result

    # auto 降级链: cloud -> rules
    errors = []
    for candidate in (MODE_CLOUD, MODE_RULES):
        b = build(candidate, cfg, hosts)
        if not b.available:
            errors.append("%s:unavailable" % candidate)
            continue
        try:
            result = b.ask(text, **opts)
            result["fallback_from"] = errors or None
            return result
        except BackendError as e:
            errors.append("%s:%s" % (candidate, str(e)[:60]))
    raise BackendError("auto 降级链全失败: " + "; ".join(errors))


if __name__ == "__main__":
    import json
    print(json.dumps(status(), ensure_ascii=False, indent=2))
