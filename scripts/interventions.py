#!/usr/bin/env python3
"""オーナーの介入を数える（2026-10-01）。システムの改善が効いたかを、話ごとの介入の件数で見る。

オーナーの指摘で本文やメモを直したコミットには、件名の末尾に分類を付ける：
  (owner:A) 作者の判断（筋・設定・配置・引きを決める／変える。減らす対象ではない）
  (owner:B) 筋の整合ミス（決まっている事実・立場・時系列と食い違い）
  (owner:C) 現場の知識（作者が体験していない場の細部）
  (owner:D) 文の欠陥（AIっぽい文、説明の一行、読点、話し手、口調、指示語）
  (owner:E) 直し案の外れ（同じ所を2回以上直した、2回目以降）
  (owner:F) 不足（内心・場面が足りず足した）
  (owner)   分類なし（古い形。数えるが「?」に入れる）
一つのコミットに複数あるときは (owner:D,D,B) のように並べる。件名に話番号（EPxxx）を入れる。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/interventions.py                 # 話ごとの表
  python ../pachi-book/scripts/interventions.py --since 2026-10-02
採用のとき、その話の行を notes/summary.md に写す（finalize-episode）。
"""
import argparse
import re
import subprocess
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

KINDS = "ABCDEF?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    ap.add_argument("--rev", default="HEAD")
    a = ap.parse_args()
    cmd = ["git", "log", a.rev, "--format=%s"]
    if a.since:
        cmd.append(f"--since={a.since}")
    subjects = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    table = defaultdict(lambda: defaultdict(int))
    for s in subjects:
        tags = re.findall(r"\(owner(?::([A-F?,\s]+))?\)", s)
        if not tags:
            continue
        eps = sorted(set(re.findall(r"EP\d{3}", s))) or ["(話なし)"]
        for t in tags:
            kinds = [k.strip() for k in t.split(",") if k.strip()] if t else ["?"]
            for ep in eps:
                for k in kinds:
                    table[ep][k] += 1
    if not table:
        print("(owner) の付いたコミットがない")
        return
    print("| 話 | " + " | ".join(KINDS) + " | 計 | A以外 |")
    print("|---|" + "---|" * (len(KINDS) + 2))
    for ep in sorted(table):
        row = table[ep]
        tot = sum(row.values())
        print(f"| {ep} | " + " | ".join(str(row.get(k, 0)) for k in KINDS) + f" | {tot} | {tot - row.get('A', 0)} |")


if __name__ == "__main__":
    main()
