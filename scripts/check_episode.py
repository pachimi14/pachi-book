#!/usr/bin/env python3
"""Mechanical checks for one Kakuyomu episode file. Short output only."""
import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TIME_JUMP = re.compile(r"^[　 ]*(翌[日朝週晩]|次の日|その夜|その日の(?:夜|夕方|朝)|数[日時分週][^。\n]{0,4}後|何日か後|しばらくして|同じ頃|その頃|後日)")
DIALOGUE_OPEN = "「『（(〈【"

# Contrastive negation ("Aではない。Bだ" family). See skills/japanese-prose.md section 1.
NEG_PATTERNS = [
    ("否定＋断定", r"(?<!場合)(?<!どころ)(?<!わけ)(?<!の)(?<!ん)(?:では|じゃ)(?:ない|なかった|ありません|ねえ|ねぇ)(?!か|だろ|でしょ|かな|のか|けど|が|し|と)"),
    ("わけではない", r"わけ(?:では|じゃ)(?:ない|なかった|なく)"),
    ("のではない", r"(?:の|ん)(?:では|じゃ)(?:ない|なかった)(?!か|だろ|でしょ)"),
    ("AではなくB", r"(?:では|じゃ)なく(?!な|ても)"),
    ("AというよりB", r"という(?:より|よりも|よりは)"),
    ("AでもBでもない", r"でも(?:なければ|なく)"),
    ("だけではない", r"(?:だけ|のみ)(?:では|じゃ)な"),
    ("決して〜ない", r"決して[^。\n]{0,40}な(?:い|かった)"),
    ("ただ〜だけだ", r"ただ[、]?[^。\n]{0,40}だけ(?:だ|である|だった)"),
]


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

    narr_count = indented = 0
    for i, l in enumerate(lines, 1):
        if l.count("《") != l.count("》"):
            errors.append(f"{i}行目：《》の数が合わない")
        if re.search(r"[|｜][^《\n]*$", l):
            errors.append(f"{i}行目：|の後に《ルビ》がない")
        if not l.strip():
            continue
        is_dialogue = l.lstrip("　 ")[:1] in DIALOGUE_OPEN
        if not is_dialogue:
            narr_count += 1
            indented += l[:1] in "　 "
        for name, pat in NEG_PATTERNS:
            for m in re.finditer(pat, l):
                snippet = l[max(0, m.start() - 16):m.end() + 10].strip()
                if is_dialogue:
                    warns.append(f"{i}行目：台詞の対句否定（{name}）…{snippet}… 直前に打ち消す発言があるか確認")
                else:
                    errors.append(f"{i}行目：地の文の対句否定（{name}）…{snippet}… Bを直接書く")

    if narr_count and narr_count * 0.1 < indented < narr_count * 0.9:
        warns.append(f"地の文の字下げが混在（{indented}/{narr_count}行）")

    gaps, idx = [], [i for i, l in enumerate(lines) if l.strip()]
    for j in range(1, len(idx)):
        gap = idx[j] - idx[j - 1] - 1
        gaps.append(gap)
        if TIME_JUMP.search(lines[idx[j]]) and gap < 2:
            warns.append(f"{idx[j] + 1}行目：時間の飛びの前が空行{gap}（強い区切りを検討）")

    levels = {k: gaps.count(k) for k in sorted(set(gaps))}
    print(f"{a.file}  字数 {chars}  空行の段階 {levels}")
    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    if not errors and not warns:
        print("OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
