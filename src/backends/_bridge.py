"""把已验证的 c1/c2 模块挂到 sys.path, 供正式版复用(不复制、不重写)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _sub in ("", "c1", "c2"):
    _p = os.path.join(ROOT, _sub) if _sub else ROOT
    if _p not in sys.path:
        sys.path.insert(0, _p)
