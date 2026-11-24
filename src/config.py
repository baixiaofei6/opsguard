"""OpsGuard 正式版 - 配置管理 - Python 3.8+ 纯标准库.

职责: 统一读取配置(opsguard.config.json) + 环境变量覆盖; 敏感值只从环境变量读,
绝不写进配置文件/日志. 提供默认配置, 缺字段自动补, 支持 --config 指定路径.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(HERE, "opsguard.config.json")

DEFAULTS = {
    "backend": "auto",                       # auto | cloud | rules
    "api_base": "https://api.openai.com/v1",
    "api_key_env": "OPSGUARD_API_KEY",       # 环境变量名, 不存 Key 本体
    "log_path": "logs/opsguard.log",
    "confirm_default": "no",                 # 恒为 no; 仅为显式记录, 不作为可跳过开关
    "timeout_sec": 30,
    "ai_confirm_mode": "manual",             # AI 修复执行: manual 每次确认 / auto 信任模式免逐次问
}


def load(path=None):
    """读配置; 缺文件/缺字段用默认值补. 返回 dict(不含任何 Key 明文)."""
    p = path or DEFAULT_CONFIG_PATH
    cfg = dict(DEFAULTS)
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in DEFAULTS:
                        cfg[k] = v
        except (ValueError, OSError):
            pass  # 配置损坏退回默认, 不崩
    return cfg


def api_key(cfg):
    """从环境变量读 Key 本体; 没有返回空串. 绝不以任何形式写入配置文件。"""
    env_name = cfg.get("api_key_env") or DEFAULTS["api_key_env"]
    return os.environ.get(env_name, "") or ""


def save(cfg, path=None):
    """把配置写回 json(只写白名单字段). 返回 (ok, msg). 不写任何 Key 明文."""
    p = path or DEFAULT_CONFIG_PATH
    data = dict(cfg)
    # 只落白名单字段, 防止调用方误塞敏感值进配置.
    safe = {}
    for k in DEFAULTS:
        if k in data:
            safe[k] = data[k]
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(safe, f, ensure_ascii=False, indent=2)
        return True, ""
    except (OSError, ValueError) as e:
        return False, str(e)[:120]


def effective_backend(cfg, override=None):
    """决定实际后端; override 优先于配置; 仅允许 auto/cloud/rules, 非法退回 auto。"""
    val = override or cfg.get("backend") or "auto"
    return val if val in ("auto", "cloud", "rules") else "auto"


def root_dir():
    """opsguard 根目录 (src 的父目录)."""
    return os.path.dirname(HERE)


if __name__ == "__main__":
    import sys
    c = load(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps({"backend": effective_backend(c), "api_key_set": bool(api_key(c))}, ensure_ascii=False))
