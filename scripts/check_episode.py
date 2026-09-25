#!/usr/bin/env python3
"""Mechanical checks for one Kakuyomu episode file. Short output only."""
import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TIME_JUMP = re.compile(r"^[　 ]*(翌[日朝週晩]|次の日|その夜|その日の(?:夜|夕方|朝)|数[日時分週][^。\n]{0,4}後|何日か後|しばらくして|同じ頃|その頃|後日)")
# Contrastive-negation family; counted in narration only (see style.md).
A_PATTERNS = [r"ではなく(?!な)", r"じゃなく(?!な)", r"わけ(?:じゃ|では)な", r"(?:の|ん)(?:じゃ|では)な(?:い|かった)[。、」』]",
              r"という(?:より|よりも)", r"(?:では|じゃ)な(?:い|かった)。[^。\n]{1,40}(?:だ|である|のだ)。",
              r"決して[^。\n]{0,100}な(?:い|かった)", r"ただ[、]?[^。\n]{0,100}だけ(?:だ|である|だった)", r"(?:だけ|のみ)(?:じゃ|では)な"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--min", type=int, default=3000)
    ap.add_argument("--max", type=int, default=5000)
    a = ap.parse_args()
    text = a.file.read_text(encoding="utf-8-sig")
    lines = text.split("\n")
    errors, warns = [], []

    chars = len(re.sub(r"\s", "", text))
    if not a.min <= chars <= a.max:
        warns.append(f"字数 {chars}（目安 {a.min}〜{a.max}）")

    if re.search(r"(?<!…)…(?!…)", re.sub("……", "", text)):
        errors.append("三点リーダが奇数個の箇所がある（……を使う）")
    if re.search(r"(?<!―)―(?!―)", re.sub("――", "", text)):
        errors.append("ダッシュが奇数個の箇所がある（――を使う）")
    if re.search(r"(?m)^#{1,6}\s|\*\*|^[-*]\s", text):
        errors.append("Markdown記法が本文にある")
    for i, l in enumerate(lines, 1):
        if l.count("《") != l.count("》"):
            errors.append(f"{i}行目：《》の数が合わない")
        if re.search(r"[|｜][^《\n]*$", l):
            errors.append(f"{i}行目：|の後に《ルビ》がない")

    narr = [l for l in lines if l.strip() and l.lstrip("　 ")[:1] not in "「『（(〈【"]
    indented = sum(1 for l in narr if l[:1] in "　 ")
    if narr and 0 < indented < len(narr) * 0.9 and indented > len(narr) * 0.1:
        warns.append(f"地の文の字下げが混在（{indented}/{len(narr)}行）")

    gaps, idx = [], [i for i, l in enumerate(lines) if l.strip()]
    for j in range(1, len(idx)):
        gap = idx[j] - idx[j - 1] - 1
        gaps.append(gap)
        if TIME_JUMP.search(lines[idx[j]]) and gap < 2:
            warns.append(f"{idx[j] + 1}行目：時間の飛びの前が空行{gap}（強い区切りを検討）")

    prose = "\n".join(narr)
    a_count = sum(len(re.findall(p, prose)) for p in A_PATTERNS)
    density = round(a_count * 3500 / chars, 2) if chars else 0
    if density >= 3.8:
        warns.append(f"対句否定が多い（地の文 {density}/3500字）")

    levels = {k: gaps.count(k) for k in sorted(set(gaps))}
    print(f"{a.file}  字数 {chars}  空行の段階 {levels}  対句否定 {density}/3500字")
    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    if not errors and not warns:
        print("OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
