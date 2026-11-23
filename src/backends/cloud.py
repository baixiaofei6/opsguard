"""云端 AI 后端 - urllib 实装 OpenAI 兼容 chat completions - 纯标准库.

Key 只从 config.api_key_env 指定的环境变量读, 绝不写日志/配置/错误文本.
所有 payload 已经由 BaseBackend.ask() 脱敏后才进到这里.
"""
import json
import urllib.error
import urllib.request

import config as _config
import keystore as _keystore
from base import BaseBackend, BackendError, MODE_CLOUD


class CloudBackend(BaseBackend):
    mode = MODE_CLOUD

    def __init__(self, cfg=None, hosts=None, resolved=None):
        super(CloudBackend, self).__init__(cfg, hosts)
        # 完整三元组(api_base/key/model)统一从 keystore.resolve 取, 保证同一出处;
        # resolved 可注入便于 mock 测试(不出网/不依赖真实 keystore).
        r = resolved if resolved is not None else _keystore.resolve(self.cfg)
        self.api_base = (r.get("api_base") or "https://api.openai.com/v1").rstrip("/")
        self.key = r.get("key") or ""
        self.model = r.get("model") or "gpt-4o-mini"
        self.source = r.get("source") or "none"
        self.timeout = int(self.cfg.get("timeout_sec") or 30)

    @property
    def available(self):
        return bool(self.key)

    def _chat(self, redacted_text, **opts):
        if not self.key:
            raise BackendError("云端后端未配置 Key (设环境变量 " +
                               (self.cfg.get("api_key_env") or "OPSGUARD_API_KEY") + ")")
        url = self.api_base + "/chat/completions"
        payload = {
            "model": opts.get("model") or self.model,
            "messages": [
                {"role": "system", "content": "你是 Windows 运维助手 OpsGuard。只基于给定证据回答，不臆造。"},
                {"role": "user", "content": redacted_text},
            ],
            "temperature": 0.2,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + self.key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 不回显 body(可能含回显的请求内容), 只给状态码
            raise BackendError("云端 HTTP %d" % e.code)
        except (urllib.error.URLError, OSError) as e:
            raise BackendError("云端网络失败: %s" % _safe_reason(e))
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise BackendError("云端响应格式异常(缺 choices[0].message.content)")


def _safe_reason(err):
    """从异常里取不含敏感信息的简短原因."""
    reason = getattr(err, "reason", None) or str(err)
    return str(reason)[:120]


if __name__ == "__main__":
    import config as c
    b = CloudBackend(c.load())
    print("cloud available:", b.available)
