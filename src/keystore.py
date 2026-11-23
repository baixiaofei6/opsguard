# -*- coding: utf-8 -*-
"""OpsGuard 正式版 - 本地 API Key / 模型仓库 - Python 3.8+ 纯标准库.

职责: 让用户能在软件里"新增/删除/更改 API Key + 自由选择执行模型",
Key 只落在本机一个受保护文件, 绝不明文出现在: 命令输出 / 日志 / 交付清单 / 测试输出.

安全设计:
- 读外部输入只从 getpass / CLI 参数进; 显示一律 mask(只露头4尾4).
- 原子写(tmp + fsync + os.replace), 写完收紧文件权限(POSIX 0600 / Windows icacls 仅当前用户).
- 环境变量 OPSGUARD_API_KEY 优先级最高(兼容旧行为), 不因 keystore 存在而改变.
- 该文件加入 .gitignore, 交付清单与哈希校验都不纳入它.

数据格式(version 1):
{
  "version": 1,
  "providers": {
     "<provider>": {"api_base": "...", "key": "...", "models": ["m1", "m2"]}
  },
  "active": {"provider": "<provider>", "model": "<model>"}
}
"""
import json
import os
import re
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _default_path():
    """默认路径; 可用 OPSGUARD_KEYSTORE 环境变量覆盖(测试隔离/自定义存储位置)."""
    return os.environ.get("OPSGUARD_KEYSTORE") or os.path.join(_ROOT, ".keystore", "keys.json")


KEYSTORE_PATH = _default_path()

# 常见服务商预设: 仅给 api_base 与建议模型名, 不预置任何 Key.
# 数据来自各家官方文档(2026-11 核实), 详见 README「API 地址与模型来源」:
# - DeepSeek: https://api-docs.deepseek.com/zh-cn/  base_url=https://api.deepseek.com
#   官方现用 deepseek-flash / deepseek-v4-pro; 旧 deepseek-chat / deepseek-reasoner
#   已于 2026-07-24 停止使用(本文件旧版误用, 已更正).
# - 阿里云百炼 DashScope: https://dashscope.aliyuncs.com/compatible-mode/v1
# - Moonshot Kimi: https://platform.kimi.com/docs/get-api-key  base_url=https://api.moonshot.cn/v1
# - 智谱 GLM: https://docs.bigmodel.cn/cn/guide/develop/openai/introduction.md
# - OpenAI: https://api.openai.com/v1
# 注意: 模型名会随官方更新, 预设只是"默认值"; 用 fetch_models() 可从 /v1/models 拉实时列表.
PRESETS = {
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
        "key_hint": "sk-proj- 或 sk- 开头",
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "key_hint": "sk- 开头",
    },
    "dashscope": {
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "key_hint": "sk- 开头",
    },
    "moonshot": {
        "api_base": "https://api.moonshot.cn/v1",
        "models": ["kimi-k3.1-pro", "kimi-k3.1-pro-highspeed", "kimi-k2.5"],
        "key_hint": "sk- 开头",
    },
    "zhipu": {
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        # 免费档优先(实测 2026-11-23)：glm-4-flash/glm-4.7-flash 长期 0 元；
        # glm-4.6 等收费模型同一把 Key 会返回 429/余额不足, 不作为默认首选.
        "models": ["glm-4-flash", "glm-4.7-flash", "glm-4.6", "glm-4.5-air"],
        "key_hint": "形如 <id>.<secret>",
    },
}

# Key 前缀识别提示: 大多数 OpenAI 兼容服务商都用 sk- 前缀, 无法可靠区分, 不瞎猜.
# 仅能明确识别的才给高置信; 其余返回候选让用户选一次(选完地址/模型全自动).
def guess_provider(key, urlopen=None):
    """按 Key 格式推测服务商.

    返回 (provider|None, confidence, reason).
    - sk-proj- 开头: OpenAI(较明确).
    - 含且仅含一个 '.' 且两段都是较长 base64url: 智谱(格式特殊).
    - 其余 sk- 开头: 无法区分(DeepSeek/DashScope/Moonshot 都用 sk-), 返回 None + 说明.
    不发起网络请求; 不回显完整 Key.
    """
    s = str(key or "").strip()
    if not s:
        return None, "none", "Key 为空"
    if s.startswith("sk-proj-"):
        return "openai", "high", "sk-proj- 前缀是 OpenAI 项目 Key 格式"
    if s.startswith("sk-"):
        return None, "ambiguous", (
            "sk- 前缀在 DeepSeek/阿里云百炼/Moonshot/OpenAI 通用, 无法仅凭 Key 区分; "
            "请选择一次服务商, 地址和模型会自动带出"
        )
    if s.count(".") == 1 and len(s) > 20:
        left, right = s.split(".", 1)
        if left and right and re.match(r"^[A-Za-z0-9_-]+$", right):
            return "zhipu", "medium", "id.secret 两段格式符合智谱 Key"
    return None, "unknown", "无法识别 Key 格式, 请选择服务商(可用自定义填地址)"


def fetch_models(provider, key, api_base=None, urlopen=None, timeout=8):
    """从 OpenAI 兼容的 {api_base}/models 拉实时模型列表(成熟项目如 Codex CLI 做法).

    - 只访问用户已选定的那一家 provider(绝不拿 Key 去试别家, 避免泄漏).
    - urlopen 可注入用于 mock 测试; 生产用 urllib.request.urlopen.
    - 失败/格式异常一律返回 ([], reason), 不抛、不回显 Key、不打印 body.
    """
    base = api_base or PRESETS.get(provider, {}).get("api_base") or ""
    if not base:
        return [], "no_api_base"
    if urlopen is None:
        import urllib.request
        urlopen = urllib.request.urlopen
    url = base.rstrip("/") + "/models"
    try:
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            url, headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        data = json.loads(raw)
        ids = data.get("data") if isinstance(data, dict) else None
        if not isinstance(ids, list):
            return [], "bad_response"
        models = [d.get("id") for d in ids
                  if isinstance(d, dict) and isinstance(d.get("id"), str) and d["id"]]
        # 去重保序, 只留合法模型名字符
        models = [m for m in dict.fromkeys(models) if re.match(r"^[A-Za-z0-9_.:/-]{1,80}$", m)]
        return models, "ok" if models else "empty"
    except Exception:
        return [], "fetch_failed"  # 不回显异常体(可能含 Key/敏感信息)


_EMPTY = {"version": 1, "providers": {}, "active": {}}


class KeystoreError(Exception):
    pass


def mask(key):
    """脱敏显示: 只露头4尾4, 短串全遮蔽. 永不返回可用于请求的完整值."""
    s = str(key or "")
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return s[:4] + "***" + s[-4:]


def _normalize(data):
    """把任意读入的数据规范成合法结构, 非法退回空仓库(不崩)."""
    out = {"version": 1, "providers": {}, "active": {}}
    if not isinstance(data, dict):
        return out
    provs = data.get("providers")
    if isinstance(provs, dict):
        for name, info in provs.items():
            if not isinstance(name, str) or not isinstance(info, dict):
                continue
            key = info.get("key")
            if not isinstance(key, str) or not key:
                continue  # 无 Key 的条目不保留
            base = info.get("api_base") or ""
            models = info.get("models")
            if not isinstance(models, list):
                models = []
            models = [m for m in models if isinstance(m, str) and m]
            out["providers"][name] = {
                "api_base": str(base),
                "key": key,
                "models": models,
            }
    active = data.get("active")
    if isinstance(active, dict):
        p, m = active.get("provider"), active.get("model")
        if isinstance(p, str) and p in out["providers"] and isinstance(m, str) and m:
            out["active"] = {"provider": p, "model": m}
    if not out["active"] and out["providers"]:
        # 有 Key 但没指定 active: 用第一个 provider 的第一个 model(若有)
        p = sorted(out["providers"])[0]
        models = out["providers"][p]["models"]
        if models:
            out["active"] = {"provider": p, "model": models[0]}
    return out


def load(path=None):
    p = path or _default_path()
    if not os.path.isfile(p):
        return {"version": 1, "providers": {}, "active": {}}
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return {"version": 1, "providers": {}, "active": {}}
    return _normalize(data)


def _harden(path):
    """尽量收紧文件权限; 失败不影响功能(仅 best-effort, 绝不抛)."""
    try:
        if os.name == "posix":
            os.chmod(path, 0o600)
        elif os.name == "nt":
            # 注意: subprocess 不经过 cmd.exe, %USERNAME% 不会被展开 — 必须先取值.
            user = os.environ.get("USERNAME") or ""
            domain = os.environ.get("USERDOMAIN") or ""
            # 用 "DOMAIN\user" 精确限定到当前账户(本机账户也没问题: MACHINE\user).
            who = (domain + "\\" + user) if (domain and user) else user
            if who:
                subprocess.run(
                    ["icacls", path, "/inheritance:r", "/grant:r", who + ":F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=15,
                )
    except Exception:
        pass


def save(data, path=None):
    """原子写 + 收紧权限. 返回实际写入路径."""
    p = path or _default_path()
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    clean = _normalize(data)
    # 同目录临时文件 -> os.replace 原子替换
    fd, tmp = tempfile.mkstemp(prefix=".keys-", suffix=".tmp", dir=d or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    _harden(p)
    return p


def _validate_provider(name):
    if not isinstance(name, str) or not re.match(r"^[A-Za-z0-9_.-]{1,40}$", name):
        raise KeystoreError("服务商名称只能用字母/数字/点/下划线/连字符(1-40字符)")


def _validate_key(key):
    if not isinstance(key, str) or not key.strip():
        raise KeystoreError("Key 不能为空")
    if len(key) > 512:
        raise KeystoreError("Key 过长(>512字符)")
    if "\n" in key or "\r" in key:
        raise KeystoreError("Key 不能包含换行")


def _validate_base(base):
    if not isinstance(base, str) or not base.startswith(("http://", "https://")):
        raise KeystoreError("api_base 必须是 http:// 或 https:// 开头")
    if len(base) > 300:
        raise KeystoreError("api_base 过长(>300字符)")


def _validate_model(model):
    if not isinstance(model, str) or not re.match(r"^[A-Za-z0-9_.:/-]{1,80}$", model):
        raise KeystoreError("模型名只能用字母/数字/点/下划线/冒号/斜杠/连字符(1-80字符)")


def set_key(provider, key, api_base=None, models=None, path=None):
    """新增或更改某服务商的 Key. 首次新增自动套用预设 api_base/models.

    返回脱敏后的摘要(不含完整 Key).
    """
    _validate_provider(provider)
    _validate_key(key)
    data = load(path)
    preset = PRESETS.get(provider, {"api_base": "", "models": []})
    base = api_base if api_base is not None else preset["api_base"]
    if base:
        _validate_base(base)
    if models is not None:
        if not isinstance(models, list) or any(not isinstance(m, str) for m in models):
            raise KeystoreError("models 必须是字符串列表")
        for m in models:
            _validate_model(m)
        models = list(dict.fromkeys(models))  # 去重保序
    else:
        models = list(preset["models"])
    is_new = provider not in data["providers"]
    data["providers"][provider] = {
        "api_base": base or "",
        "key": key.strip(),
        "models": models,
    }
    # 新增且当前无 active -> 自动选中该服务商首个模型
    if not data["active"] and models:
        data["active"] = {"provider": provider, "model": models[0]}
    save(data, path)
    return {
        "provider": provider,
        "api_base": base or "",
        "key_masked": mask(key),
        "models": models,
        "action": "added" if is_new else "updated",
        "active": dict(data["active"]),
        "note": "Key 已本机保存(文件权限已收紧为仅当前用户可读)并脱敏显示; 不会进入日志/命令输出/交付清单.",
    }


def remove_key(provider, path=None):
    """删除某服务商的 Key. 若删的是当前 active, 自动切到剩余第一个模型或清空."""
    _validate_provider(provider)
    data = load(path)
    if provider not in data["providers"]:
        raise KeystoreError("服务商 '%s' 未配置 Key" % provider)
    del data["providers"][provider]
    if data["active"].get("provider") == provider:
        data["active"] = {}
        if data["providers"]:
            p = sorted(data["providers"])[0]
            models = data["providers"][p]["models"]
            if models:
                data["active"] = {"provider": p, "model": models[0]}
    save(data, path)
    return {
        "provider": provider,
        "action": "removed",
        "active": dict(data["active"]),
        "note": "Key 已从本机删除.",
    }


def add_model(provider, model, api_base=None, path=None):
    """给某服务商增加一个可选模型名(便于自由选择)."""
    _validate_provider(provider)
    _validate_model(model)
    data = load(path)
    if provider not in data["providers"]:
        raise KeystoreError("服务商 '%s' 未配置 Key, 请先 key add" % provider)
    if api_base is not None:
        _validate_base(api_base)
        data["providers"][provider]["api_base"] = api_base
    models = data["providers"][provider]["models"]
    if model not in models:
        models.append(model)
    save(data, path)
    return {"provider": provider, "model": model, "models": list(models),
            "active": dict(data["active"])}


def remove_model(provider, model, path=None):
    """删某服务商一个模型名; 若是当前 active, 自动切到剩余第一个."""
    _validate_provider(provider)
    data = load(path)
    if provider not in data["providers"]:
        raise KeystoreError("服务商 '%s' 未配置 Key" % provider)
    models = data["providers"][provider]["models"]
    if model not in models:
        raise KeystoreError("模型 '%s' 不在服务商 '%s' 列表" % (model, provider))
    models.remove(model)
    if data["active"].get("provider") == provider and data["active"].get("model") == model:
        data["active"] = {}
        if models:
            data["active"] = {"provider": provider, "model": models[0]}
        else:
            others = [p for p in sorted(data["providers"]) if p != provider]
            if others:
                p = others[0]
                ms = data["providers"][p]["models"]
                if ms:
                    data["active"] = {"provider": p, "model": ms[0]}
    save(data, path)
    return {"provider": provider, "model": model, "models": list(models),
            "active": dict(data["active"])}


def use_model(provider, model, path=None):
    """选择当前执行模型(provider + model)."""
    _validate_provider(provider)
    _validate_model(model)
    data = load(path)
    if provider not in data["providers"]:
        raise KeystoreError("服务商 '%s' 未配置 Key, 请先 key add" % provider)
    if model not in data["providers"][provider]["models"]:
        raise KeystoreError("模型 '%s' 不在服务商 '%s' 列表, 请先 model add" % (model, provider))
    data["active"] = {"provider": provider, "model": model}
    save(data, path)
    return {"active": dict(data["active"]), "note": "已切换执行模型."}


def list_keys(path=None):
    """列出所有 Key(脱敏)与模型, 标明当前 active. 绝不含完整 Key."""
    data = load(path)
    items = []
    for p in sorted(data["providers"]):
        info = data["providers"][p]
        is_active = (data["active"].get("provider") == p)
        items.append({
            "provider": p,
            "api_base": info["api_base"],
            "key_masked": mask(info["key"]),
            "models": list(info["models"]),
            "active_model": data["active"].get("model") if is_active else None,
        })
    return {
        "providers": items,
        "active": dict(data["active"]),
        "presets": sorted(PRESETS),
        "note": "Key 只显示头4尾4; 完整值永不输出/不入日志.",
    }


def resolve(cfg=None, path=None):
    """给 CloudBackend 用: 解析出 {api_base, key, model, source}.

    优先级(用户要"软件里自由选模型", 故 keystore 的完整三元组为权威):
      1) keystore 有 active 且 model 存在 -> 该 provider 的 api_base/key + 选中的 model 一起用
         (三元组整体取自同一处, 避免 env key 混搭别家 api_base/model);
      2) 否则环境变量 Key(旧行为兼容) -> cfg.api_base + env key + cfg.cloud_model;
      3) 否则空(云端不可用, auto 会降级 rules).
    """
    cfg = cfg or {}
    env_name = cfg.get("api_key_env") or "OPSGUARD_API_KEY"
    env_key = os.environ.get(env_name, "") or ""
    data = load(path)
    active = data.get("active") or {}
    p = active.get("provider")
    m = active.get("model")
    # 1) 软件内明确选择的完整三元组优先
    if p and m and p in data["providers"]:
        info = data["providers"][p]
        if info.get("key"):
            return {"api_base": info.get("api_base") or cfg.get("api_base") or "https://api.openai.com/v1",
                    "key": info["key"], "model": m, "source": "keystore:" + p}
    # 1b) 只有一个 provider 且它有 Key(即使没显式选模型): 兜底用它, 模型取配置默认,
    #     避免"自定义服务商无预设模型"时 Key 存了却显示云端不可用.
    if not p and len(data["providers"]) == 1:
        only = next(iter(data["providers"]))
        info = data["providers"][only]
        if info.get("key"):
            model = (info["models"][0] if info.get("models")
                     else cfg.get("cloud_model") or "gpt-4o-mini")
            return {"api_base": info.get("api_base") or cfg.get("api_base") or "https://api.openai.com/v1",
                    "key": info["key"], "model": model, "source": "keystore:" + only}
    # 2) 环境变量兜底(旧行为)
    if env_key:
        base = cfg.get("api_base") or "https://api.openai.com/v1"
        model = m or cfg.get("cloud_model") or "gpt-4o-mini"
        return {"api_base": base, "key": env_key, "model": model,
                "source": "env:" + env_name}
    # 3) 空
    return {"api_base": cfg.get("api_base") or "https://api.openai.com/v1",
            "key": "", "model": cfg.get("cloud_model") or "gpt-4o-mini",
            "source": "none"}


def status_line(path=None):
    """给 doctor 用的一行人话(不含完整 Key)."""
    data = load(path)
    if data["active"]:
        a = data["active"]
        info = data["providers"].get(a["provider"], {})
        return "keystore: %s / %s (key %s)" % (
            a["provider"], a["model"], mask(info.get("key", "")))
    if os.path.isfile(path or _default_path()):
        return "keystore: 有 Key 但未选模型 (用 model use 选择)"
    return "keystore: 空 (用 key add 添加)"


if __name__ == "__main__":
    print(json.dumps(list_keys(), ensure_ascii=False, indent=2))
