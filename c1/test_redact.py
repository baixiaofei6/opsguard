"""OpsGuard C1 · 脱敏层黄金测试（标准库 unittest，零新增依赖）。

运行：python -m unittest discover -s C:/Users/Administrator/.dsh/im/opsguard/c1 -p "test_*.py" -v
"""
import hashlib
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import redact
import demo_ai

ROOT = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(ROOT), "samples")


class TestRFC1918(unittest.TestCase):
    def test_rfc1918_hits(self):
        r = redact.Redactor()
        text = "10.0.0.1 10.255.255.255 172.16.0.1 172.31.255.254 192.168.0.1 192.168.255.255"
        out = r.redact(text)
        for token in ["10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.254",
                      "192.168.0.1", "192.168.255.255"]:
            self.assertNotIn(token, out)
        self.assertEqual(len(r.mapping_table()), 6)

    def test_rfc1918_misses_and_boundaries(self):
        r = redact.Redactor()
        text = ("8.8.8.8 172.15.0.1 172.32.0.1 192.169.0.1 192.168.256.1 "
                "10.0.0.256 110.0.0.1 10.0.0.1.5 1.10.0.0.1")
        out = r.redact(text)
        # 只有被点号数字边界正确包围的 10.0.0.1（在 110.0.0.1 内不是独立 token）不应误伤
        self.assertEqual(out, text, "非 RFC1918 / 越界八位组 / 边界内子串均不应被替换")

    def test_octet_validation(self):
        r = redact.Redactor()
        self.assertNotIn("[IP_1]", r.redact("192.168.1.256"))
        self.assertIn("[IP_1]", r.redact("192.168.1.255"))


class TestMAC(unittest.TestCase):
    def test_mac_variants(self):
        r = redact.Redactor()
        text = "AA:BB:CC:DD:EE:FF 00-1a-2b-3c-4d-5e AABB.CCDD.EEFF"
        out = r.redact(text)
        self.assertNotIn("AA:BB:CC:DD:EE:FF", out)
        self.assertNotIn("00-1a-2b-3c-4d-5e", out)
        self.assertNotIn("AABB.CCDD.EEFF", out)
        self.assertEqual(sum(1 for k in r.mapping_table() if k.startswith("[MAC_")), 3)

    def test_mac_not_version_string(self):
        r = redact.Redactor()
        text = "version 1.2.3.4.5.6 build"
        self.assertEqual(r.redact(text), text)


class TestHostExact(unittest.TestCase):
    def test_exact_table_and_length_desc(self):
        r = redact.Redactor(["WIN-CLIENT-17", "win-client-17.office.local"])
        text = ("WIN-CLIENT-17 win-client-17.office.local "
                "WIN-CLIENT-17X not-win-client-17")
        out = r.redact(text)
        self.assertIn("[HOST_1]", out)
        self.assertIn("[HOST_2]", out)
        self.assertIn("WIN-CLIENT-17X", out)      # 更长的主机名/后缀不应误伤
        self.assertIn("not-win-client-17", out)

    def test_no_host_table_no_false_positive(self):
        r = redact.Redactor([])
        text = "SERVER-UNKNOWN 出现在文本中"
        self.assertEqual(r.redact(text), text)


class TestRoundTrip(unittest.TestCase):
    CASES = [
        ("单 IP", ["HOST-A"], "server HOST-A at 10.1.2.3"),
        ("同值多次", [], "10.0.0.5 -> dns, 10.0.0.5 -> gateway, again 10.0.0.5"),
        ("混合文本", ["WIN-OPS-01"],
         "host WIN-OPS-01 10.0.0.5 mac AA-BB-CC-DD-EE-FF fqdn WIN-OPS-01.corp.local"),
        ("多 MAC 变体", [], "aa:bb:cc:dd:ee:ff and 00-11-22-33-44-55 and AAAA.BBBB.CCCC"),
        ("多段 RFC1918", [], "a=172.16.5.4 b=192.168.10.1 c=10.9.8.7"),
        ("无敏感值", [], "纯文本 normal text 12345"),
    ]

    def test_roundtrip_ge_5(self):
        self.assertGreaterEqual(len(self.CASES), 5)
        for name, hosts, text in self.CASES:
            with self.subTest(name):
                r = redact.Redactor(hosts)
                red = r.redact(text)
                self.assertEqual(r.restore(red), text)

    def test_deterministic_mapping(self):
        r = redact.Redactor(["H"])
        out = r.redact("10.2.3.4 H 10.2.3.4 AA-BB-CC-DD-EE-FF H 10.2.3.4")
        self.assertEqual(out.count("[IP_1]"), 3)
        self.assertEqual(out.count("[HOST_1]"), 2)
        self.assertEqual(out.count("[MAC_1]"), 1)
        self.assertEqual(r.mapping_table()["[IP_1]"], "10.2.3.4")
        self.assertEqual(r.mapping_table()["[HOST_1]"], "H")
        # 第二次 redact 同值仍复用同一占位符
        self.assertIn("[IP_1]", r.redact("again 10.2.3.4"))


class TestOutboundGate(unittest.TestCase):
    def test_outbound_payload_no_raw_values(self):
        raw = ("host WIN-SECRET ip 10.77.88.99 mac DE:AD:BE:EF:00:01 "
               "fqdn WIN-SECRET.corp.local also 10.77.88.99 and DE:AD:BE:EF:00:01")
        payload, r = redact.prepare_outbound(raw, ["WIN-SECRET.corp.local", "WIN-SECRET"])
        for token in ["WIN-SECRET", "10.77.88.99", "DE:AD:BE:EF:00:01"]:
            self.assertNotIn(token, payload)
        self.assertIn("[IP_1]", payload)
        self.assertIn("[MAC_1]", payload)
        self.assertIn("[HOST_1]", payload)
        self.assertIn("[HOST_2]", payload)
        self.assertEqual(r.restore(payload), raw)

    def test_mapping_table_local_only(self):
        raw = "10.1.1.1 on AA-BB-CC-DD-EE-FF host WIN-X"
        payload, r = redact.prepare_outbound(raw, ["WIN-X"])
        mapping = r.mapping_table()
        self.assertEqual(set(mapping.values()), {"10.1.1.1", "AA-BB-CC-DD-EE-FF", "WIN-X"})
        for secret in mapping.values():
            self.assertNotIn(secret, payload)

    def test_no_key_degrade_and_demo_chain(self):
        # demo 无 Key：不报错、不发起网络；脱敏管线产出占位符 payload，回填还原展示。
        raw, data, theme = demo_ai.load_sample(os.path.join(SAMPLES, "sample-lan-ops-scan.html"))
        evidence = demo_ai.extract_evidence(data)
        payload, lines, r = demo_ai.prepare_payload(evidence)
        self.assertEqual(theme, "light")
        for host in evidence["hosts"]:
            self.assertNotIn(host, payload)
        for f in evidence["findings"]:
            for token in (f["detail"], f["suggest"]):
                for m in re.findall(r"(?:10|172|192).d+.d+.d+", token):
                    self.assertNotIn(m, payload)
        result = demo_ai.local_rules(lines, evidence)
        self.assertIn("离线规则模式", result["summary"])
        section = demo_ai.build_section(result, evidence, theme, r, payload)
        self.assertIn('id="opsguard-ai"', section)
        self.assertIn('class="og-cards"', section)
        self.assertIn('[需确认]', section)
        self.assertIn('class="og-diff"', section)
        # 回填后展示原值
        self.assertIn("10.10.0.53", section)

    def test_no_network_imports_in_demo(self):
        p = os.path.join(ROOT, "demo_ai.py")
        with open(p, "r", encoding="utf-8") as fh:
            src = fh.read()
        for banned in ["import socket", "import urllib", "import http.client", "requests"]:
            self.assertNotIn(banned, src)

    def test_demo_runs_and_samples_unchanged(self):
        def sha(path):
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        sample_files = [
            os.path.join(SAMPLES, "sample-lan-ops-scan.html"),
            os.path.join(SAMPLES, "sample-windeploy.html"),
        ]
        before = [sha(p) for p in sample_files]
        cp = subprocess.run([sys.executable, os.path.join(ROOT, "demo_ai.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        after = [sha(p) for p in sample_files]
        self.assertEqual(before, after, "demo 运行后 samples/ 原件哈希必须不变")
        for name in ["sample-lan-ops-scan.ai.html", "sample-windeploy.ai.html"]:
            dest = os.path.join(ROOT, "out", name)
            self.assertTrue(os.path.exists(dest))
            with open(dest, "r", encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn('id="opsguard-ai"', content)
            self.assertIn("[IP_1]", content)
            self.assertIn("样本，非真实项目产物", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
