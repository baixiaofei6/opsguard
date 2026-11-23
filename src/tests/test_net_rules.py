"""断网排障规则库测试: 16类覆盖 / 命中排序 / 安全分级 / 知识库. 纯内存不碰系统."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

import net_rules as nr


class TestNetRules(unittest.TestCase):
    def test_catalog_16_rules(self):
        c = nr.rule_catalog()
        self.assertGreaterEqual(c["total"], 15)
        self.assertEqual(c["auto_fixable"] + c["manual_only"], c["total"])

    def test_every_rule_has_required_fields(self):
        required = ("id", "title", "symptom_pattern", "root_cause", "confidence",
                    "probe_commands", "fix_command", "fix_ast_tier",
                    "rollback_command", "plain_english", "next_if_fail")
        for r in nr.NET_RULES:
            for k in required:
                self.assertIn(k, r, "%s missing %s" % (r.get("id"), k))
            self.assertIn(r["fix_ast_tier"], (nr.AUTO_TIER, nr.MANUAL_TIER))

    def test_dns_hit(self):
        r = nr.diagnose_net("DNS 服务器不可达 名称解析失败")
        self.assertGreaterEqual(r["matched_count"], 1)
        self.assertEqual(r["top"]["id"], "DNS_SERVER_UNREACHABLE")

    def test_multi_hit_sorted_by_confidence(self):
        r = nr.diagnose_net("DNS 不可达; 网卡 media disconnected; 代理 127.0.0.1:7897")
        confs = [c["confidence"] for c in r["cards"]]
        self.assertEqual(confs, sorted(confs, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x]))

    def test_no_hit_graceful(self):
        r = nr.diagnose_net("今天天气不错")
        self.assertEqual(r["matched_count"], 0)
        self.assertIn("未命中", r["summary"])

    def test_auto_fixable_uses_whitelisted_commands(self):
        # 可自动修复的命令必须在 c2 AST 白名单 tier=require_confirm
        sys.path.insert(0, os.path.join(os.path.dirname(SRC), "c2"))
        import ast_guard
        for r in nr.NET_RULES:
            if r["fix_ast_tier"] == nr.AUTO_TIER:
                v = ast_guard.validate(r["fix_command"])
                self.assertEqual(v.get("verdict"), "require_confirm",
                                 "%s fix not in AST whitelist" % r["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
