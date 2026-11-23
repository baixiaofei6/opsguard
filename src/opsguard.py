#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpsGuard 正式版 - 统一 CLI 入口 - Python 3.8+ 纯标准库.

一条命令覆盖三场景: diagnose(报错排障) / explain(报告解读) / fix(带回滚修复),
外加 rollback / audit / backend / doctor / integrate / selftest / astcheck / sanitize.
退出码: 0成功 1需确认未完成 2被AST拒绝 3回滚失败冻结 4参数错误 5后端不可用.
安全铁律: 修改类默认 dry-run + 默认 N; 生产真改需 --live 且显式 --confirm y.
本地模型后端已按用户 2026-11-23 决定彻底移除, 只保留 cloud + rules。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, os.path.join(HERE, "backends"), ROOT,
           os.path.join(ROOT, "c1"), os.path.join(ROOT, "c2"), os.path.join(ROOT, "c3")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config as _config
import keystore as _keystore
import pricing as _pricing
import backends.factory as factory
# 必须与 factory/cloud/rules 用同一个模块名(base), 否则同一个类被加载两次 ->
# cmd_explain 的 except BackendError 接不住 cloud._chat 抛的异常, traceback 漏到终端.
from base import BackendError
import diagnose as _diag
import generate as _gen
import ast_guard as _ast
import policy as _policy
import adapters.system as _adapter
import doctor as _doctor
import evidence as _evidence
import net_rules as _net

EXIT_OK, EXIT_CONFIRM, EXIT_DENY, EXIT_FROZEN, EXIT_ARGS, EXIT_BACKEND = 0, 1, 2, 3, 4, 5


def _out(obj):
    if isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2))


def _err(msg):
    sys.stderr.write(msg + "\n")


# ---------- 子命令 ----------
def cmd_diagnose(args, cfg):
    evidence = args.evidence
    if not evidence and args.sample:
        evidence = _diag.sample_evidence(args.sample)
    if not evidence:
        _err("需要 evidence 文本或 --sample {error,inspection,fix}")
        return EXIT_ARGS
    d = _diag.diagnose(evidence, args.scenario)
    _out({
        "summary": d.get("summary"),
        "scenario": args.scenario,
        "findings": d.get("findings", []),
        "note": "只读诊断, 未生成/未执行任何修改命令.",
    })
    return EXIT_OK


def cmd_explain(args, cfg):
    if not args.report or not os.path.isfile(args.report):
        _err("需要 --report <存在的报告文件>")
        return EXIT_ARGS
    with open(args.report, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    try:
        r = factory.ask(text, cfg, args.backend)
    except BackendError as e:
        _err(str(e))
        return EXIT_BACKEND
    _out({
        "backend": r["backend"],
        "fallback_from": r.get("fallback_from"),
        "redaction_applied": r["redaction_applied"],
        "mapping_count": r["mapping_count"],
        "answer": r["text"],
    })
    return EXIT_OK


def cmd_fix(args, cfg):
    """带回滚修复闭环. 默认 dry-run; --live 且 --confirm y 才真改系统/夹具."""
    sample = getattr(args, "sample", None)
    evidence = args.evidence or (_diag.sample_evidence(sample) if sample else _diag.sample_evidence(args.scenario))
    d = _diag.diagnose(evidence, args.scenario)
    proposals = _gen.generate(d, intent_override="mutating")
    if not proposals:
        _err("没有可修复项(诊断无 mutating 候选)")
        return EXIT_OK
    p = proposals[0]
    guard = _ast.validate(p["command"])
    decision = _policy.decide(guard, args.confirm)
    live = bool(args.live)
    result = {
        "finding": p["title"],
        "command": p["command"],
        "plain": p["plain_english"],
        "diff": p["diff"],
        "ast_verdict": guard.get("verdict"),
        "ast_reason": guard.get("reason"),
        "policy_decision": decision["decision"],
        "mode": "LIVE" if live else "DRY-RUN",
        "target": "real-system" if live else "sandbox-fixture",
    }
    if decision["decision"] == "deny":
        _out(result)
        return EXIT_DENY
    if decision["decision"] != "confirmed":
        _out(result)
        return EXIT_CONFIRM
    # 已显式确认
    if not live:
        result["note"] = "DRY-RUN: 未执行、未备份、未落盘。真改请加 --live --confirm y。"
        _out(result)
        return EXIT_OK
    # LIVE: 走参数化适配器(sandbox=False 真改; 但本 CLI 默认不给 --live 除非用户明确)
    try:
        ex = _adapter.change(
            kind=args.kind, target=args.target,
            values={"content": args.value} if args.kind == "file" else {args.key: args.value},
            confirm_answer=args.confirm, sandbox=not live,
            sandbox_root=args.sandbox_root, label=p["finding_id"],
            ast_verdict=guard.get("verdict"),
        )
    except Exception as e:
        _err("执行失败: %s" % str(e)[:150])
        return EXIT_FROZEN
    result["execution"] = ex
    if ex and ex.get("ok"):
        if args.rollback:
            rb = _adapter.rollback(ex["manifest"], sandbox=not live, sandbox_root=args.sandbox_root)
            result["rollback"] = rb
            if not rb or not rb.get("ok"):
                return EXIT_FROZEN
    _out(result)
    return EXIT_OK


def cmd_rollback(args, cfg):
    try:
        with open(args.manifest, "r", encoding="utf-8-sig") as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        _err("读取 manifest 失败: %s" % str(e)[:100])
        return EXIT_ARGS
    rb = _adapter.rollback(m, sandbox=not args.live, sandbox_root=args.sandbox_root)
    _out(rb)
    return EXIT_OK if rb and rb.get("ok") else EXIT_FROZEN


def cmd_audit(args, cfg):
    path = args.path
    if not path:
        path = os.path.join(ROOT, "c3", "audit", "audit.jsonl")
    if not os.path.isfile(path):
        _out({"entries": [], "note": "审计日志为空或不存在: " + path})
        return EXIT_OK
    entries = []
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    if args.last is not None:
        if args.last < 0:
            _err("--last 必须 >= 0（当前为 %d）" % args.last)
            return EXIT_ARGS
        entries = entries[-args.last:] if args.last else []
    _out({"count": len(entries), "entries": entries})
    return EXIT_OK


def cmd_backend(args, cfg):
    st = factory.status(cfg, args.set_backend)
    _out(st)
    return EXIT_OK


def _read_key_interactive(prompt="请输入 API Key（输入不显示）: "):
    """从 getpass 读 Key(不回显); 非 TTY 时退回 stdin 读一行并提示风险."""
    try:
        import getpass
        if sys.stdin.isatty():
            return getpass.getpass(prompt)
    except Exception:
        pass
    # 管道/非交互: 读一行, 不在终端回显我们自己打印(但管道输入本身不被 echo)
    line = sys.stdin.readline()
    return line.rstrip("\r\n") if line else ""


def _fetch_annotated_models(provider, key, base):
    """拉官方实时模型 + 标注计费(共用). 返回 (annotated|None, reason).

    只访问该 provider 一家; 失败返回 (None, reason), 不回显 Key.
    """
    models, reason = _keystore.fetch_models(provider, key, api_base=base)
    if not models:
        return None, reason
    return _pricing.annotate(provider, models), reason


def cmd_key(args, cfg):
    """API Key 管理: list/add/remove/suggest. Key 不明文回显."""
    action = args.key_action
    try:
        if action == "list":
            _out(_keystore.list_keys())
            return EXIT_OK
        if action == "suggest":
            # 只给 Key, 看建议(不落盘): 自动识别服务商 + 各家地址/默认模型.
            key = args.key_value or ""
            if not key and args.key_value_file:
                with open(args.key_value_file, "r", encoding="utf-8") as f:
                    key = f.read().strip()
            if not key:
                key = _read_key_interactive()
            prov, conf, reason = _keystore.guess_provider(key)
            out = {"guess": prov, "confidence": conf, "reason": reason,
                   "presets": _keystore.list_keys()["presets"]}
            if prov and prov in _keystore.PRESETS:
                out["will_use"] = _keystore.PRESETS[prov]
            _out(out)
            return EXIT_OK
        if action == "add":
            key = args.key_value
            if not key:
                if args.key_value_file:
                    with open(args.key_value_file, "r", encoding="utf-8") as f:
                        key = f.read().strip()
                else:
                    _err("提示: 为安全起见, 建议在交互 TUI 用 /key add 输入; CLI 管道输入如下——")
                    key = _read_key_interactive()
            provider = args.provider
            if not provider:
                # 用户只填了 Key: 自动识别服务商, 地址和模型自动带出.
                provider, conf, reason = _keystore.guess_provider(key)
                if not provider:
                    _err("仅凭 Key 无法确定服务商(%s)。请从下面选一个填到 key add 后面，"
                         "地址和模型会自动带出: %s" % (reason, ", ".join(sorted(_keystore.PRESETS))))
                    return EXIT_ARGS
                _out({"auto_detected": provider, "confidence": conf, "reason": reason})
            models = args.models.split(",") if args.models else None
            result = _keystore.set_key(provider, key, api_base=args.api_base, models=models)
            _out(result)
            # 用户诉求: 发 Key 后自动拉模型+标计费. --fetch-models 打开即用, 默认关(避免每次存 Key 都出网).
            if getattr(args, "fetch_models", False):
                base = args.api_base or result.get("api_base")
                ann, reason = _fetch_annotated_models(provider, key, base)
                if ann:
                    _out({"auto_fetched": True, "provider": provider, "api_base": base,
                          "models": [a["id"] for a in ann], "annotated": ann,
                          "pricing_note": "/models 只返回模型名不返回价格；计费来自官方价格页，实际以账单为准.",
                          "next": "model use <服务商> <模型> 选择执行模型"})
                    # 拉到的模型并入可选清单, 方便直接 use.
                    for a in ann:
                        try:
                            _keystore.add_model(provider, a["id"])
                        except _keystore.KeystoreError:
                            pass
                else:
                    _err("自动拉模型失败(%s)：已存好 Key，可稍后用 model fetch %s 重试。" % (reason, provider))
            return EXIT_OK
        if action == "remove":
            _out(_keystore.remove_key(args.provider))
            return EXIT_OK
    except (_keystore.KeystoreError, OSError) as e:
        _err(str(e))
        return EXIT_ARGS
    _err("未知 key 操作: %s" % action)
    return EXIT_ARGS


def cmd_model(args, cfg):
    """执行模型选择: list/add/remove/use."""
    action = args.model_action
    try:
        if action == "list":
            _out(_keystore.list_keys())
            return EXIT_OK
        if action == "add":
            _out(_keystore.add_model(args.provider, args.model, api_base=args.api_base))
            return EXIT_OK
        if action == "remove":
            _out(_keystore.remove_model(args.provider, args.model))
            return EXIT_OK
        if action == "use":
            _out(_keystore.use_model(args.provider, args.model))
            return EXIT_OK
        if action == "fetch":
            # 从官方 /models 动态拉模型(Codex CLI 做法), 只访问该 provider.
            data = _keystore.load()
            info = data["providers"].get(args.provider)
            key = info["key"] if info else (args.key_value or "")
            base = args.api_base or (info.get("api_base") if info else None)
            if not key:
                _err("请先 key add %s，或用 --key 临时提供(不明文回显)" % args.provider)
                return EXIT_ARGS
            models, reason = _keystore.fetch_models(args.provider, key, api_base=base)
            if not models:
                _err("拉取模型失败(%s)：可手动 model add %s <模型名>；预设模型见 key list。" % (reason, args.provider))
                return EXIT_BACKEND
            # 计费标注来自官方价格页整理(pricing.py); /models 本身不返回价格, 不编造.
            annotated = _pricing.annotate(args.provider, models)
            _out({"provider": args.provider, "api_base": base, "models": models,
                  "source": "GET {api_base}/models", "reason": reason,
                  "annotated": annotated,
                  "pricing_note": "/models 只返回模型名不返回价格；计费来自官方价格页，见 annotated[].source/label。"})
            if info:
                _out(_keystore.add_model(args.provider, models[0], path=None))
            return EXIT_OK
        if action == "prices":
            # 查本地核价表(不出网): 列该厂商已核实计费的模型; 不指定厂商则列全部.
            provider = getattr(args, "provider", None)
            if provider:
                info = _pricing.provider_info(provider)
                if not info:
                    _err("未收录 %s 的核价表；可用: %s" % (provider, ", ".join(sorted(_pricing.PRICE_TABLE))))
                    return EXIT_ARGS
                models = sorted(info["models"])
                ann = _pricing.annotate(provider, models)
                _out({"provider": provider, "source": info["source"], "verified": info["verified"],
                      "unit": info["unit"], "note": info.get("note", ""), "models": ann})
            else:
                _out({"verified": _pricing.VERIFIED,
                      "providers": {p: {"source": v["source"], "verified": v["verified"],
                                        "unit": v["unit"], "note": v.get("note", ""),
                                        "models": sorted(v["models"])}
                                    for p, v in _pricing.PRICE_TABLE.items()},
                      "note": "价格来自官方价格页人工核实; /models 不返回价格; 实际扣费以账单为准."})
            return EXIT_OK
    except (_keystore.KeystoreError, OSError) as e:
        _err(str(e))
        return EXIT_ARGS
    _err("未知 model 操作: %s" % action)
    return EXIT_ARGS


def cmd_doctor(args, cfg):
    rows = _doctor.check(cfg)
    _out(_doctor.render(rows))
    return EXIT_OK


def cmd_astcheck(args, cfg):
    r = _evidence.astcheck_demo()
    _out(r)
    return EXIT_OK if r["all_denied"] else EXIT_DENY


def cmd_sanitize(args, cfg):
    text = args.text or None
    r = _evidence.sanitize_demo(text)
    _out(r)
    return EXIT_OK if r["outbound_safe"] else EXIT_DENY


def cmd_selftest(args, cfg):
    r = _evidence.selftest_matrix()
    _out(r)
    # 有套件文件缺失 -> 后端不可用语义
    missing = [s["suite"] for s in r["suites"] if not s["available"]]
    if missing:
        _err("缺失测试套件: " + ", ".join(missing))
        return EXIT_BACKEND
    return EXIT_OK


def cmd_hashdemo(args, cfg):
    r = _evidence.rollback_hash_demo()
    ok = (r.get("rollback_ok") and r.get("assert_after_differs_before")
          and r.get("assert_restored_equals_before"))
    _out(r)
    return EXIT_OK if ok else EXIT_FROZEN


def cmd_netdiag(args, cfg):
    """断网排障: 证据文本 -> 命中根因卡片(16类决策树 + 知识库补充). 只读."""
    if args.top is not None and args.top < 1:
        _err("--top 必须 >= 1（当前为 %d）" % args.top)
        return EXIT_ARGS
    if args.catalog:
        _out(_net.rule_catalog())
        return EXIT_OK
    evidence = args.evidence or ("; ".join(args.symptom) if args.symptom else None)
    if not evidence:
        # 默认用覆盖多类根因的演示证据
        evidence = ("DNS 服务器不可达 名称解析失败; 网卡 link speed 0 media disconnected; "
                    "代理 127.0.0.1:7897 残留; DNS Client 服务 stopped")
    r = _net.diagnose_net(evidence, top_n=args.top)
    _out(r)
    return EXIT_OK


def cmd_integrate(args, cfg):
    """为既有项目加 --ai: 默认只生成补丁, 不写任务外文件(需 --apply 才写)."""
    target = args.target
    if not target or not os.path.isdir(target):
        _err("需要 --target <存在的既有项目目录>")
        return EXIT_ARGS
    patch = {
        "target": target,
        "change": "append '--ai' section to generated report only; do not alter main flow",
        "note": "默认仅生成补丁建议; 写回任务外文件需用户单独授权并加 --apply。",
        "patch_preview": "在报告渲染末尾追加一节: AI 解读(脱敏后出网/回填), 不改既有命令.",
    }
    if not args.apply:
        _out(patch)
        return EXIT_OK
    _err("--apply 需用户单独授权本次任务外写入; 当前未执行。")
    return EXIT_CONFIRM


class _Parser(argparse.ArgumentParser):
    """参数错误统一退出码 4, 避免与 AST 拒绝(2)撞码."""
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(4, "%s: error: %s\n" % (self.prog, message))


def build_parser():
    ap = _Parser(
        prog="opsguard",
        description="OpsGuard - 可证明安全的 Windows 运维 CLI（诊断/报告解读/带回滚修复）",
    )
    ap.add_argument("--config", help="指定配置文件路径")
    # 注: CLI 输出本就是纯文本/JSON, 无 ANSI 颜色; 彩色只在 --tui, 由终端自动处理,
    # 因此这里不提供 --no-color 假开关(避免让人以为有颜色可关)。
    sub = ap.add_subparsers(dest="cmd", parser_class=_Parser)

    d = sub.add_parser("diagnose", help="① 报错排障：只读诊断，给结论和建议")
    d.add_argument("--evidence", help="报错/巡检文本")
    d.add_argument("--sample", choices=["error", "inspection", "fix"], help="用内置样例证据")
    d.add_argument("--scenario", default="error", choices=["error", "inspection", "fix"])
    d.set_defaults(fn=cmd_diagnose)

    e = sub.add_parser("explain", help="② 报告解读：脱敏→AI后端→回填→展示")
    e.add_argument("--report", required=True, help="报告文件路径")
    e.add_argument("--backend", choices=["auto", "cloud", "rules"], help="覆盖后端选择")
    e.set_defaults(fn=cmd_explain)

    f = sub.add_parser("fix", help="③ 带回滚修复：诊断→AST→确认→备份→执行→哈希")
    f.add_argument("--evidence")
    f.add_argument("--sample", choices=["error", "inspection", "fix"], help="用内置样例证据")
    f.add_argument("--scenario", default="fix", choices=["error", "inspection", "fix"])
    f.add_argument("--confirm", help="人工确认: 仅 y/yes 视为确认(默认 N)")
    f.add_argument("--live", action="store_true", help="真改系统(需 --confirm y); 不加则只在夹具演练")
    f.add_argument("--kind", default="registry", choices=["dns", "service", "registry", "file"])
    f.add_argument("--target", default="HKCU:\\Software\\OpsGuardTest\\OpsGuardDemo")
    f.add_argument("--key", default="Demo")
    f.add_argument("--value", default="demo")
    f.add_argument("--sandbox-root", help="夹具根目录(默认 opsguard/sandbox)")
    f.add_argument("--rollback", action="store_true", help="执行后立即回滚并做三方哈希验证")
    f.set_defaults(fn=cmd_fix)

    r = sub.add_parser("rollback", help="按 manifest 独立回滚 + 三方哈希验证")
    r.add_argument("--manifest", required=True, help="manifest JSON 路径")
    r.add_argument("--live", action="store_true", help="回滚真实目标; 不加则回滚夹具")
    r.add_argument("--sandbox-root")
    r.set_defaults(fn=cmd_rollback)

    a = sub.add_parser("audit", help="查审计日志")
    a.add_argument("--path", help="审计日志路径(默认 c3/audit/audit.jsonl)")
    a.add_argument("--last", type=int, help="只看最后 N 条")
    a.set_defaults(fn=cmd_audit)

    b = sub.add_parser("backend", help="查看/选择 AI 后端状态")
    b.add_argument("--set", dest="set_backend", choices=["auto", "cloud", "rules"])
    b.set_defaults(fn=cmd_backend)

    k = sub.add_parser("key", help="管理 API Key（输入/删除/更改，脱敏显示）")
    ks = k.add_subparsers(dest="key_action", parser_class=_Parser)
    kl = ks.add_parser("list", help="列出已配置 Key（只显头4尾4）与可选服务商")
    kl.set_defaults(fn=cmd_key)
    kg = ks.add_parser("suggest", help="只给 Key 时自动识别服务商（不落盘，可先用它看建议）")
    kg.add_argument("--key", dest="key_value", help="Key 明文（不建议；推荐 stdin/TUI）")
    kg.add_argument("--key-file", dest="key_value_file", help="从文件读 Key")
    kg.set_defaults(fn=cmd_key)
    ka = ks.add_parser("add", help="新增或更改 Key；服务商可省略（能识别就自动配好地址与模型）")
    ka.add_argument("provider", nargs="?", default=None,
                    help="服务商名（openai/deepseek/dashscope/moonshot/zhipu 或自定义）；可省略=自动识别")
    ka.add_argument("--key", dest="key_value", help="Key 明文（不建议用，会进 shell 历史；推荐 TUI 或stdin）")
    ka.add_argument("--key-file", dest="key_value_file", help="从文件读 Key（文件用完请删）")
    ka.add_argument("--api-base", help="OpenAI 兼容接口地址（预设服务商可省略，自动带出）")
    ka.add_argument("--models", help="可选模型列表，逗号分隔（覆盖预设）")
    ka.add_argument("--fetch-models", action="store_true",
                    help="存好 Key 后立刻从官方拉实时模型并标注计费（会访问该厂商 /models）")
    ka.set_defaults(fn=cmd_key)
    kr = ks.add_parser("remove", help="删除某服务商的 Key")
    kr.add_argument("provider")
    kr.set_defaults(fn=cmd_key)

    mo = sub.add_parser("model", help="自由选择执行模型")
    ms = mo.add_subparsers(dest="model_action", parser_class=_Parser)
    ml = ms.add_parser("list", help="列出各服务商模型与当前选择")
    ml.set_defaults(fn=cmd_model)
    ma = ms.add_parser("add", help="给服务商增加一个可选模型")
    ma.add_argument("provider")
    ma.add_argument("model")
    ma.add_argument("--api-base", help="同时更新该服务商接口地址")
    ma.set_defaults(fn=cmd_model)
    mrm = ms.add_parser("remove", help="删除某服务商一个可选模型")
    mrm.add_argument("provider")
    mrm.add_argument("model")
    mrm.set_defaults(fn=cmd_model)
    mu = ms.add_parser("use", help="选择当前执行模型")
    mu.add_argument("provider")
    mu.add_argument("model")
    mu.set_defaults(fn=cmd_model)
    mf = ms.add_parser("fetch", help="从官方 {api_base}/models 拉实时模型并标注计费（Codex CLI 做法）")
    mf.add_argument("provider")
    mf.add_argument("--key", dest="key_value", help="临时 Key（一般不用：从已存 Key 读）")
    mf.add_argument("--api-base", help="覆盖接口地址")
    mf.set_defaults(fn=cmd_model)
    mp = ms.add_parser("prices", help="查官方核价表（本地、不出网）；标注每个模型计费")
    mp.add_argument("provider", nargs="?", default=None,
                    help="服务商名；省略则列出所有已收录厂商的核价表来源与模型")
    mp.set_defaults(fn=cmd_model)

    sub.add_parser("doctor", help="环境自检").set_defaults(fn=cmd_doctor)

    ac = sub.add_parser("astcheck", help="AST deny 侧演示: 混淆变体逐条拦截")
    ac.add_argument("--demo", action="store_true", help="用内置恶意样本演示(默认)")
    ac.set_defaults(fn=cmd_astcheck)

    sa = sub.add_parser("sanitize", help="脱敏证据: 出网 payload + 映射表")
    sa.add_argument("--demo", action="store_true", help="用内置样例演示(默认)")
    sa.add_argument("--text", help="自定义输入文本")
    sa.set_defaults(fn=cmd_sanitize)

    st = sub.add_parser("selftest", help="拦截矩阵: 黄金测试集用例数字汇总")
    st.set_defaults(fn=cmd_selftest)

    hd = sub.add_parser("hashdemo", help="回滚三方哈希完整演示(隔离夹具, 三值+断言)")
    hd.set_defaults(fn=cmd_hashdemo)

    nd = sub.add_parser("netdiag", help="断网排障: 16类根因决策树(只读, 本地规则无模型)")
    nd.add_argument("--evidence", help="断网现象/采集文本")
    nd.add_argument("--symptom", nargs="+", help="症状关键词(如 dns 不可达 网卡 禁用)")
    nd.add_argument("--catalog", action="store_true", help="列出全部规则卡")
    nd.add_argument("--top", type=int, default=5, help="返回前 N 张卡片(默认5)")
    nd.set_defaults(fn=cmd_netdiag)

    g = sub.add_parser("integrate", help="为既有项目生成 --ai 补丁(默认不写回)")
    g.add_argument("--target", help="既有项目目录")
    g.add_argument("--apply", action="store_true", help="写回(需单独授权)")
    g.set_defaults(fn=cmd_integrate)

    return ap


def main(argv=None):
    argv = list(argv) if argv is not None else sys.argv[1:]
    # --tui: 宇宙主题 logo 品牌头 + 像 Claude Code 那样持续交互的 REPL
    if argv and argv[0] == "--tui":
        import tui as _tui

        def _dispatch(tokens):
            if not tokens:
                return EXIT_ARGS
            sub = build_parser()
            a = sub.parse_args(tokens)
            c = _config.load(getattr(a, "config", None))
            fn = getattr(a, "fn", None)
            return fn(a, c) if fn else EXIT_ARGS

        cfg = _config.load(None)
        return _tui.run_repl(cfg, dispatcher=_dispatch)
    ap = build_parser()
    args = ap.parse_args(argv)
    cfg = _config.load(args.config)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return EXIT_ARGS
    try:
        return args.fn(args, cfg)
    except KeyboardInterrupt:
        _err("已取消")
        return EXIT_CONFIRM


if __name__ == "__main__":
    sys.exit(main())
