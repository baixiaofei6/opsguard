"""MCP 薄层测试: 协议握手 / 只读工具清单 / 工具调用. 本地安装器已按用户决定移除."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)


class TestMCP(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(SRC, "mcp"))
        global server
        import server as server

    def test_initialize(self):
        r = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(r["result"]["protocolVersion"], "2024-11-05")

    def test_tools_list_only_readonly(self):
        r = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in r["result"]["tools"]]
        self.assertEqual(names, ["opsguard_diagnose"])

    def test_diagnose_tool_returns_text(self):
        r = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "opsguard_diagnose",
                                      "arguments": {"evidence": "DNS unreachable", "scenario": "error"}}})
        self.assertFalse(r["result"]["isError"])
        self.assertIn("text", r["result"]["content"][0])

    def test_unknown_tool_error(self):
        r = server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                           "params": {"name": "opsguard_fix"}})
        self.assertIn("error", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
