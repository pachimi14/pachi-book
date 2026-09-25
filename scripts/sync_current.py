#!/usr/bin/env python3
"""Copy the newest version of every episode to episodes/current/EPxxx.md (for reading straight through).

Usage (from the work repository root):
    python ../pachi-book/scripts/sync_current.py

episodes/current/ always holds the latest Vn of each episode, adopted or not.
Adoption is recorded separately in episodes/EPxxx/summary.md ("採用版：Vn").
"""
import hashlib
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    episodes = work / "episodes"
    current = episodes / "current"
    current.mkdir(parents=True, exist_ok=True)
    ok = True
    for ep in sorted(p for p in episodes.glob("EP[0-9]*") if p.is_dir()):
        versions = sorted(ep.glob("V*.md"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
        if not versions:
            continue
        latest = versions[-1]
        dst = current / f"{ep.name}.md"
        changed = not dst.is_file() or sha(dst) != sha(latest)
        if changed:
            shutil.copyfile(latest, dst)
        same = sha(dst) == sha(latest)
        ok &= same
        summary = ep / "summary.md"
        adopted = re.search(r"採用版[：:]\s*(V\d+)", summary.read_text(encoding="utf-8")) if summary.is_file() else None
        state = f"採用 {adopted.group(1)}" if adopted else "未採用"
        print(f"{ep.name}: {latest.name}{'（更新）' if changed else ''}  {state}{'' if same else '  不一致'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
