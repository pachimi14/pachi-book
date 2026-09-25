#!/usr/bin/env python3
"""Adopt an episode version: copy episodes/EPxxx/Vn.md to current/EPxxx.md byte-for-byte."""
import hashlib
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: promote.py <作品リポジトリ> EP001 V2")
    work, ep, ver = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    src = work / "episodes" / ep / f"{ver}.md"
    if not src.is_file():
        sys.exit(f"not found: {src}")
    dst = work / "current" / f"{ep}.md"
    dst.parent.mkdir(exist_ok=True)
    shutil.copyfile(src, dst)
    ok = sha(src) == sha(dst)
    print(f"{src} -> {dst}  sha256 {sha(dst)[:16]}  {'一致' if ok else '不一致'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
