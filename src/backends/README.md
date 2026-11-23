# OpsGuard AI 后端（可插拔）

两个后端实现同一接口 `BaseBackend.ask`，都经 `BaseBackend.ask()` 的**统一脱敏出口**：
- 用户输入先过 `c1/redact.prepare_outbound()`（RFC1918 IP / MAC / 精确主机名 → 占位符，映射留本地）；
- 断言 payload 不含内网 IP/MAC，否则拒发；
- `_chat()` 发出后，返回文本用本地映射回填占位符。

本地模型后端已按用户 2026-11-23 决定彻底移除（断网排障靠完备决策树，不靠模型猜测）。

## 两个实现

| 模式 | 类 | 传输 | 可用性 | Key |
|---|---|---|---|---|
| `cloud` | `CloudBackend` | urllib → OpenAI 兼容 `/chat/completions` | 配了 Key | 环境变量 `OPSGUARD_API_KEY`（名字可配） |
| `rules` | `RulesBackend` | 本地 `c2/diagnose` + `c2/generate` | 永远 | 无（如实标注"离线规则模式"） |

`auto`（默认）：cloud（有 Key）→ rules（兜底），失败自动降级，降级原因放进 `fallback_from`。当前实际使用哪个后端 + 为什么，见 `status()["effective_detail"]` 人话说明。

## 调用

```python
import backends.factory as factory
r = factory.ask("DNS 指向 192.168.1.99 解析失败", override="auto")
print(r["text"], r["backend"], r["redaction_applied"])
```

## 新增后端（可插拔）

1. 新建模块，继承 `BaseBackend`，实现 `available` 属性与 `_chat(redacted_text, **opts)`；
2. 在 `factory._REGISTRY` 注册一个 mode 名；
3. 在 `status()` 的元组里加上它。

**契约铁律**：子类只接收已脱敏文本，绝不自己绕过 `ask()` 直接 `_chat()`；绝不把 Key 或映射表写进日志/请求体。
