"""OpsGuard MCP 薄层 - stdio JSON-RPC - 纯标准库 python3.8+.

只暴露只读诊断工具 opsguard_diagnose; 绝不执行修改(执行回 CLI 人工确认).
协议: 每行一个 JSON-RPC 2.0 请求/响应(stdio), methods: initialize / tools/list / tools/call.
"""
import json
import sys

import sys as _sys
import os
_M = os.path.dirname(os.path.abspath(__file__))            # src/mcp
_S = os.path.dirname(_M)                                   # src
_R = os.path.dirname(_S)                                   # opsguard
for _p in (_S, os.path.join(_R, "c2")):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
import diagnose as _diag   # noqa: E402  (c2 诊断引擎)

TOOLS = [{
    "name": "opsguard_diagnose",
    "description": "只读诊断: 输入报错/巡检文本, 返回结构化结论与建议; 不执行任何修改.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "evidence": {"type": "string", "description": "报错文本或巡检结果"},
            "scenario": {"type": "string", "enum": ["error", "inspection", "fix"], "default": "error"},
        },
        "required": ["evidence"],
    },
}]


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": "2024-11-05",
                           "serverInfo": {"name": "opsguard", "version": "0.2.0"},
                           "capabilities": {"tools": {}}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        if name != "opsguard_diagnose":
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": "unknown tool: " + str(name)}}
        args = params.get("arguments") or {}
        evidence = args.get("evidence", "")
        scenario = args.get("scenario", "error")
        d = _diag.diagnose(evidence, scenario)
        text = d.get("summary", "") + "\n" + "\n".join(
            "- %s: %s" % (f["title"], f["explanation"]) for f in d.get("findings", []))
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": text}], "isError": False}}
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": "unknown method: " + str(method)}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(req)
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
