#!/usr/bin/env python3
"""束を作る（2026-10-14。research/protocol-v3-2026-10-14.md §3）。

書き手に渡すものと点検に渡すものを、人が覚えて選ばずにスクリプトで一枚にする。束に入っていないものは読まない。

  python ../pachi-book/scripts/pack.py EP026 --writer          # 書き手の束 → episodes/EP026/notes/pack-writer.md
  python ../pachi-book/scripts/pack.py EP026 V4 --check        # 点検の束（筋・差分・採用前の点検が読むもの） → notes/pack-check-V4.md
  python ../pachi-book/scripts/pack.py EP026 --writer --stdout # 画面に出すだけ

書き手の束（順番どおり。目安 15,000 字）：
  1. 決まりごと一枚（pachi.json "rules"。例 blocks/RULES.md）
  2. 書き手の一枚（"write_brief"。例 blocks/WRITE-BRIEF.md）
  3. 同じ型の採用話を一本（メモの「型」→ "type_samples" の話。episodes/current/）
  4. 出る人物の台帳カード（"characters" の "card_heading" の節）＋ メモが指定する world の節
  5. その話の散文の節とメモの節（agent.episode_plan）、直前話の採用版
  6. 行・空行・表記の既定（skills/layout.md）と作品の上書き（style.md「行・空行・記法」「この作品固有の表記」）
入れないもの：工程の文書・HANDOFF・AGENTS・OWNER-EYE・BAD／GOOD-EXAMPLES・前の版の本文と対応表・LONG-ARCS・台帳の記録。

メモに要る欄（templates/work/blocks/BLOCK-MEMOS.md）：
  - 視点：主人公         - 型：現場／日常・会話／配信     - 出る人物：主人公／シエル／…     - world：お礼の日
  - 検索語（触れない）：…／…      - 検索語（使わない）：…／…
欄が無ければ、型は聞き返し、出る人物は全員のカード、world は無しで作る。
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

ENGINE = Path(__file__).resolve().parent.parent


def layout_sheet():
    """layout.md の既定と、作品 style.md の上書き（行・空行・記法／この作品固有の表記）を一枚に。"""
    layout = (ENGINE / "skills" / "layout.md").read_text(encoding="utf-8")
    style = A.read("style.md")
    keep = []
    for title, body in A._split_sections(style, 2):
        if title.startswith(("行・空行・記法", "この作品固有の表記", "読点", "文の運び", "視点")):
            keep.append(f"## {title}\n{body.strip()}")
    return layout.strip() + "\n\n# 作品の上書き（style.md）\n\n" + "\n\n".join(keep)


def sample_episode(ep, f):
    kind = f.get("型")
    table = A.config().get("type_samples") or {}
    if not kind:
        return None, "（メモに「- 型：」の欄がない。日常・会話／現場／配信 のどれかを書く）"
    sample = table.get(kind)
    if not sample:
        return None, f"（型「{kind}」の見本の話が pachi.json の type_samples にない）"
    if sample == ep:
        return sample, "（見本が自分自身）"
    p = A.WORK / "episodes" / "current" / f"{sample}.md"
    return sample, (p.read_text(encoding="utf-8") if p.is_file() else f"（{sample} の本文が episodes/current/ にない）")


def writer_pack(ep):
    f = A.memo_fields(ep)
    sample, sample_text = sample_episode(ep, f)
    parts = [
        A.section("1. 決まりごと一枚（RULES）", A.rules() or "（pachi.json に rules がない）"),
        A.section("2. 書き手の一枚（WRITE-BRIEF）", A.doc("write_brief") or "（pachi.json に write_brief がない）"),
        A.section(f"3. 同じ型の採用話（{f.get('型', '型は未指定')}：{sample or '—'}。形を読む。台詞・仕草・思い出は写さない）", sample_text),
        A.section("4a. 出る人物の台帳カード", A.cards(f.get("出る人物")) or "（カードがない）"),
    ]
    if f.get("world"):
        parts.append(A.section("4b. 世界（この話に関わる節）", A.world_sections(f["world"])))
    parts.append(A.section("5a. この話の散文のあらすじとメモ", A.episode_plan(ep) or "（散文もメモもない）"))
    parts.append(A.section("5b. 直前の話（採用版）", A.prev_episode(ep)))
    parts.append(A.section("6. 行・空行・表記（layout と作品の上書き）", layout_sheet()))
    head = (f"# 書き手の束 {ep}（pack.py --writer。これ以外は読まない）\n\n"
            "読む順は番号どおり。読んだら、全文を一本、新しい版 episodes/EPxxx/Vn.md に書く。各場面にメモにない発明を一つ。"
            "地の文の塊は報告で終わらない（2）。決まり（1）は守る。散文の運びは目安で、場面の中は自由。\n")
    return head + A.SEP + A.SEP.join(parts) + "\n"


def check_pack(ep, ver):
    import check_logic
    return (f"# 点検の束 {ep} {ver}（pack.py --check。筋・差分・採用前の点検が読むもの）\n"
            + A.SEP + check_logic.context(ep) + A.SEP + f"# 今回の本文\n\n{A.episode_text(ep, ver)}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version", nargs="?")
    ap.add_argument("--writer", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()
    if a.writer:
        text, out = writer_pack(a.episode), A.notes_dir(a.episode) / "pack-writer.md"
    elif a.check:
        if not a.version:
            sys.exit("--check には版（V4 など）が要る")
        text, out = check_pack(a.episode, a.version), A.notes_dir(a.episode) / f"pack-check-{a.version}.md"
    else:
        sys.exit("--writer か --check")
    if a.stdout:
        print(text)
        return
    print(A.write(out, text), f"（{len(re.sub(r'\s', '', text))} 字）")


if __name__ == "__main__":
    main()
