"""OpsGuard C1 · 脱敏层（P0，出网唯一出口）— Python 3.8+ 纯标准库。

职责
- RFC1918 内网 IP（10/8、172.16/12、192.168/16）：边界感知正则 + 八位组 0-255 校验。
- MAC 格式变体：冒号分隔、横杠分隔、Cisco 点分（4x4 十六进制）。
- 主机名：调用方提供的【精确匹配表】，禁止泛正则；按长度降序替换，避免 HOST / HOST.domain 互相干扰。
- 确定性映射：同一原值全程同一占位符 [IP_n] / [MAC_n] / [HOST_n]，保留关联推理。
- 回填：restore() 把占位符还原为原值后再展示。
- 映射表只留本地（mapping_table()），绝不随请求出网。

未覆盖（如实标注，MVP 范围外）
- 公网 IP（非 RFC1918 段）不脱敏。
- 敏感文件路径、用户名、自定义敏感字段不脱敏。
- IPv6、无分隔符 MAC（12 位连续，易误伤版本号）不脱敏。
- 云元数据地址、FQDN 自动发现等不在 MVP 覆盖内。

出网纪律
- 任何发往 LLM 的文本必须先经 Redactor.redact()；prepare_outbound() 是便捷唯一出口。
- 无 Key（离线规则模式）不出网，脱敏不触发、不报错。
"""
import re

_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_BOUNDARY_L = r"(?<![0-9.])"
_BOUNDARY_R = r"(?![0-9.])"
_RFC1918 = (
    r"(?:"
    r"10\." + _OCTET + r"\." + _OCTET + r"\." + _OCTET +
    r"|172\.(?:1[6-9]|2[0-9]|3[01])\." + _OCTET + r"\." + _OCTET +
    r"|192\.168\." + _OCTET + r"\." + _OCTET +
    r")"
)
RE_IP = re.compile(_BOUNDARY_L + _RFC1918 + _BOUNDARY_R)

_MAC_COLON_DASH = r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}"
_MAC_CISCO = r"(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}"
RE_MAC = re.compile(
    r"(?<![0-9A-Fa-f])(?:" + _MAC_COLON_DASH + r"|" + _MAC_CISCO + r")(?![0-9A-Fa-f])"
)


class Redactor(object):
    """持有一份本地确定性映射表的脱敏器。实例状态跨多次 redact() 累积。"""

    def __init__(self, hosts=None):
        unique = []
        seen = set()
        for h in (hosts or []):
            if h and h not in seen:
                seen.add(h)
                unique.append(h)
        self._hosts = sorted(unique, key=len, reverse=True)
        self._host_res = [
            (h, re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(h) + r"(?![A-Za-z0-9_-])"))
            for h in self._hosts
        ]
        self._map = {}       # placeholder -> original
        self._reverse = {}   # original -> placeholder
        self._counters = {"IP": 0, "MAC": 0, "HOST": 0}

    def _placeholder_for(self, kind, value):
        if value in self._reverse:
            return self._reverse[value]
        self._counters[kind] += 1
        ph = "[%s_%d]" % (kind, self._counters[kind])
        self._reverse[value] = ph
        self._map[ph] = value
        return ph

    def redact(self, text):
        """返回脱敏文本；原值 → 占位符的映射写入本地状态。"""
        if not text:
            return "" if text is None else text
        out = RE_MAC.sub(lambda m: self._placeholder_for("MAC", m.group(0)), text)
        out = RE_IP.sub(lambda m: self._placeholder_for("IP", m.group(0)), out)
        for host, rx in self._host_res:
            out = rx.sub(lambda m, h=host: self._placeholder_for("HOST", h), out)
        return out

    def restore(self, text):
        """把文本中的占位符还原为本地映射表里的原值。"""
        if not text:
            return "" if text is None else text
        out = text
        for ph in sorted(self._map, key=len, reverse=True):
            out = out.replace(ph, self._map[ph])
        return out

    def mapping_table(self):
        """返回本地映射表副本（ph -> 原值）。仅供本地日志/回填，禁止放进请求体。"""
        return dict(self._map)

    @property
    def redaction_applied(self):
        return any(self._counters.values())


def prepare_outbound(text, hosts=None):
    """出网唯一出口：返回 (已脱敏文本, redactor)。调用方只发送第一个返回值。"""
    redactor = Redactor(hosts)
    return redactor.redact(text), redactor
