#!/usr/bin/env python3
"""List open foreshadowing entries from works/<work>/foreshadow.md."""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CLOSED = {"回収済", "破棄"}


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: threads.py <作品リポジトリ> [--all]")
    path = Path(sys.argv[1]) / "foreshadow.md"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].startswith("F"):
            continue
        rows.append(cells)
    show_all = "--all" in sys.argv
    open_rows = [r for r in rows if r[2] not in CLOSED]
    for r in (rows if show_all else open_rows):
        print(" | ".join(r))
    print(f"未回収 {len(open_rows)} / 全 {len(rows)}")


if __name__ == "__main__":
    main()
