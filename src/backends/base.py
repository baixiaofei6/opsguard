"""OpsGuard 正式版 - AI 后端抽象基类 + 统一脱敏出口 - Python 3.8+ 纯标准库.

所有后端的 chat() 都走 BaseBackend.ask(): 先把用户输入过 c1.redact.prepare_outbound(),
断言 payload 不含原始 RFC1918 IP/MAC/精确主机名, 再把脱敏文本交给 _chat().
返回时把占位符回填为原值(本地展示)。脱敏断言对所有后端一视同仁。
本地模型后端已按用户 2026-11-23 决定彻底移除, 只保留 cloud + rules。
"""
import os
import re
import sys

# 独立路径引导: 保证 base/cloud/rules/config 与 c1/c2 模块都可扁平导入
_B = os.path.dirname(os.path.abspath(__file__))          # src/backends
_S = os.path.dirname(_B)                                 # src
_R = os.path.dirname(_S)                                 # opsguard
for _p in (_B, _S, os.path.join(_R, "c1"), os.path.join(_R, "c2"), os.path.join(_R, "c3")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import redact as _redact

MODE_CLOUD = "cloud"
MODE_RULES = "rules"


class BackendError(Exception):
    pass


class BaseBackend(object):
    mode = "base"

    def __init__(self, cfg=None, hosts=None):
        self.cfg = cfg or {}
        self.extra_hosts = hosts or []

    @property
    def available(self):
        """后端是否可用(有 Key / 本地在跑 / 永远可用). 子类实现。"""
        return True

    def _chat(self, redacted_text, **opts):
        """子类实现: 接收已脱敏文本, 返回模型文本(含占位符)."""
        raise NotImplementedError

    def ask(self, text, **opts):
        """统一出口: 脱敏 -> 断言 -> 调用 -> 回填。返回 dict.

        返回 {text, redacted, backend, redaction_applied, mapping_count}
        """
        redacted, redactor = _redact.prepare_outbound(text, self.extra_hosts)
        if not self._outbound_safe(redacted):
            raise BackendError("出网 payload 仍含疑似内网 IP/MAC, 拒绝发送")
        raw = self._chat(redacted, **opts)
        restored = redactor.restore(raw or "")
        return {
            "text": restored,
            "redacted": redacted,
            "backend": self.mode,
            "redaction_applied": redactor.redaction_applied,
            "mapping_count": len(redactor.mapping_table()),
        }

    @staticmethod
    def _outbound_safe(text):
        """二次断言: 脱敏后不得残留 RFC1918 IP 或 MAC. 主机名由 prepare_outbound 精确表处理。"""
        if not text:
            return True
        if _redact.RE_IP.search(text):
            return False
        if _redact.RE_MAC.search(text):
            return False
        return True
