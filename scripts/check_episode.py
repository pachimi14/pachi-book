#!/usr/bin/env python3
"""Mechanical checks for one Kakuyomu episode file. Short output only."""
import argparse
import importlib.util
import json
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
    ("AでもBでもない", r"(?<!とん)(?<!何)でも(?:なければ|なく)"),
    ("だけではない", r"(?:だけ|のみ)(?:では|じゃ)な"),
    ("決して〜ない", r"決して[^。\n]{0,40}な(?:い|かった)"),
    ("ただ〜だけだ", r"ただ[、]?[^。\n]{0,40}だけ(?:だ|である|だった)"),
]


def find_scene_mark(episode_file):
    """Read 場面転換記号 from the work's style.md (episodes/EPxxx/Vn.md -> work root)."""
    for parent in list(episode_file.resolve().parents)[:4]:
        style = parent / "style.md"
        if style.is_file():
            m = re.search(r"場面転換記号[：:]\s*`?([^`\s]+)`?", style.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
    return "◇"


def title_line_allowed(episode_file):
    """True if the work's style.md says the body starts with a title line (「本文の1行目にタイトル：あり」)."""
    for parent in list(episode_file.resolve().parents)[:4]:
        style = parent / "style.md"
        if style.is_file():
            return bool(re.search(r"本文の1行目にタイトル[：:]\s*あり", style.read_text(encoding="utf-8")))
    return False


def work_root(episode_file):
    for parent in list(episode_file.resolve().parents)[:4]:
        if (parent / "style.md").is_file() or (parent / "pachi.json").is_file():
            return parent
    return Path.cwd()


def fixed_numbers(root):
    p = root / "pachi.json"
    if p.is_file():
        return set(json.loads(p.read_text(encoding="utf-8")).get("fixed_numbers", []))
    return set()


NUM = re.compile(r"[一二三四五六七八九十百千万0-9０-９]+(秒|回|人目|人|年|枚|分|時間|メートル|キロ|か月|ヶ月|日|番|往復|本|倍)")


def prose_checks(lines, root):
    """機械で拾える文の癖（2026-09-30〜10-01 オーナーの指摘から。旧 voice_check の汎用部分）。"""
    warns = []
    run = []
    for i, l in enumerate(lines, 1):
        if not l.startswith("　"):
            run = []
            continue
        for sent in re.findall(r"[^。]+。", l.strip()):
            if sent.count("、") == 1 and len(sent) <= 22:
                run.append(i)
                if len(run) == 3:
                    warns.append(f"{run[0]}〜{i}行目：同じ刻みの読点が3文続く（読点のない文を混ぜる）")
            else:
                run = []
    fixed = fixed_numbers(root)
    for i, l in enumerate(lines, 1):
        if l.startswith(("第", "【", "〈")):
            continue
        for m in NUM.finditer(l):
            t = m.group(0)
            if t in ("一回", "一人", "一本", "一日") or t in fixed:
                continue
            warns.append(f"{i}行目：具体的な数字「{t}」（新しく足した数字なら、数えない言い方にする。台帳で決まった数字は pachi.json の fixed_numbers へ）")
    for i, l in enumerate(lines, 1):
        sents = re.findall(r"[^。」]+[。」]?", l.strip("「」『』　"))
        ends = [re.sub(r"[。」]", "", x)[-3:] for x in sents if len(x) > 3]
        if len([e for e in ends if re.search(r"(ました|でした)$", e)]) >= 2 and len(ends) <= 4:
            warns.append(f"{i}行目：語尾の重なり（ました・でした）")
    head = [i for i, l in enumerate(lines, 1) if re.match(r"^[「『]……", l)]
    if len(head) > 7:
        warns.append(f"「……」で始まる台詞が{len(head)}（基準話は1話3〜7）")
    dash = [i for i, l in enumerate(lines, 1) if l.startswith("　") and "――" in l]
    if len(dash) > 1:
        warns.append(f"地の文の「――」が{len(dash)}（行 {dash}）")
    return warns


def plugin_checks(root, path, lines):
    """作品ごとの癖の点検：作品ルートの tools/work_checks.py に checks(path, lines) があれば呼ぶ。"""
    plug = root / "tools" / "work_checks.py"
    if not plug.is_file():
        return [], ""
    spec = importlib.util.spec_from_file_location("work_checks", plug)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    warns = list(mod.checks(path, lines))
    summary = mod.summary(path, lines) if hasattr(mod, "summary") else ""
    return warns, summary


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

    scene_mark = find_scene_mark(a.file)
    has_title = bool(lines and re.match(r"^\s*第[0-9０-９一二三四五六七八九十百]+話", lines[0]))
    if title_line_allowed(a.file):
        if not has_title:
            warns.append("1行目に話タイトルがない（この作品は「第N話　サブタイトル」を1行目に書く）")
    elif has_title:
        warns.append("1行目に話タイトルがある（タイトルは notes/memo.md に書く）")

    # Board (掲示板) regions: from a post header "N：名前" until two blank lines.
    board = set()
    in_board, blanks = False, 0
    for i, l in enumerate(lines, 1):
        s0 = l.strip("　 ")
        if re.match(r"^[0-9０-９]+[：:]\S", s0):
            in_board = True
        if not s0:
            blanks += 1
            if blanks >= 2:
                in_board = False
            continue
        blanks = 0
        if in_board:
            board.add(i)

    narr_count = indented = 0
    for i, l in enumerate(lines, 1):
        if l.count("《") != l.count("》"):
            errors.append(f"{i}行目：《》の数が合わない")
        if re.search(r"[|｜][^《\n]*$", l):
            errors.append(f"{i}行目：|の後に《ルビ》がない")
        if not l.strip():
            continue
        if i == 1 and has_title:
            continue
        s = l.strip("　 ")
        head = s[:1]
        if i in board:
            if re.search(r"[!?]", l):
                errors.append(f"{i}行目：半角の!?がある（全角！？にする）")
            for name, pat in NEG_PATTERNS:
                for m in re.finditer(pat, l):
                    snippet = l[max(0, m.start() - 16):m.end() + 10].strip()
                    warns.append(f"{i}行目：掲示板の対句否定（{name}）…{snippet}… 打ち消す相手のレスがあるか確認")
            continue
        if re.search(r"[!?]", l):
            errors.append(f"{i}行目：半角の!?がある（全角！？にする）")
        if re.search(r"[！？](?![！？」』〉】）\s　]|$)", l):
            warns.append(f"{i}行目：！？の後に全角スペースがない")
        if re.search(r"。」", l):
            warns.append(f"{i}行目：台詞の末尾に句点がある")
        if head in "（(":
            warns.append(f"{i}行目：（）は使わない（心の声は地の文に）")
        if head not in "〈【" and re.search(r"[0-9０-９]", s):
            warns.append(f"{i}行目：算用数字（地の文・台詞は漢数字）")
        if len(s) > 120:
            warns.append(f"{i}行目：1行が{len(s)}字（120字以内）")
        if len(s) <= 12 and re.fullmatch(r"[^\w぀-ヿ一-鿿]+", s) and s not in ("……", "――") and not head in "「『〈【":
            if s != scene_mark:
                warns.append(f"{i}行目：場面転換記号が「{s}」（この作品は「{scene_mark}」）")
            elif not (i >= 2 and not lines[i - 2].strip() and i < len(lines) and not lines[i].strip()):
                warns.append(f"{i}行目：場面転換記号の前後に空行がない")
        is_dialogue = head in DIALOGUE_OPEN
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

    cond = [(i, l.strip()) for i, l in enumerate(lines, 1)
            if l.strip() and i not in board and l.lstrip("　 ")[:1] not in DIALOGUE_OPEN
            and re.search(r"なら(?![なずばね])[、は]?", l)]
    if len(cond) >= 3:
        for i, s in cond:
            warns.append(f"{i}行目：条件の型「〜なら」（地の文で{len(cond)}回）…{s[:24]}…")

    if narr_count and narr_count * 0.1 < indented < narr_count * 0.9:
        warns.append(f"地の文の字下げが混在（{indented}/{narr_count}行）")

    gaps, idx = [], [i for i, l in enumerate(lines) if l.strip()]
    for j in range(1, len(idx)):
        gap = idx[j] - idx[j - 1] - 1
        gaps.append(gap)
        if TIME_JUMP.search(lines[idx[j]]) and lines[idx[j - 1]].strip() != scene_mark and not (has_title and idx[j - 1] == 0):
            warns.append(f"{idx[j] + 1}行目：時間の飛びの前に場面転換記号「{scene_mark}」がない")

    # Rhythm of narration (see skills/layout.md 1b). Narration lines ending with 。 only.
    narr = [l.strip("　 ") for i, l in enumerate(lines, 1)
            if l.strip() and i not in board and l.lstrip("　 ")[:1] not in DIALOGUE_OPEN
            and l.strip("　 ") != scene_mark and l.rstrip().endswith("。")]
    rhythm = ""
    if len(narr) >= 30:
        sents = [x for l in narr for x in re.findall(r"[^。]+。", l)]
        spl = len(sents) / len(narr)
        short = sum(1 for l in narr if len(l) <= 10) / len(narr)
        cps = sum(l.count("、") for l in narr) / max(1, len(sents))
        subj = sum(1 for l in narr if re.match(r"^[^、。]{1,8}(?:が|は|も|を|に)、", l))
        rhythm = f"  文/行 {spl:.2f}  短い行 {short:.0%}  読点/文 {cps:.2f}"
        if spl < 1.2:
            warns.append(f"地の文が1文ごとに改行されている（1行あたり{spl:.2f}文。目安1.3前後。同じ流れの2文は1行に続ける）")
        if spl > 1.55:
            warns.append(f"地の文の1行に文を詰めすぎている（1行あたり{spl:.2f}文。目安1.3〜1.45。流れの切れ目で改行する）")
        if subj < 5:
            warns.append(f"「主語が、」型の読点が少ない（{subj}行。溜めの一拍が消えていないか確認）")
        if short > 0.2:
            warns.append(f"10字以下の短い行が多い（地の文の{short:.0%}。目安1割前後。溜めの一行は見せ場だけ）")
        if cps > 0.85:
            warns.append(f"読点が多い（1文あたり{cps:.2f}。目安0.6〜0.8）")
        if subj >= 20:
            warns.append(f"「主語が、」型の読点で始まる行が{subj}行（短い区切りの読点を外す）")

    root = work_root(a.file)
    warns += prose_checks(lines, root)
    extra, summary = plugin_checks(root, a.file, lines)
    warns += extra

    levels = {k: gaps.count(k) for k in sorted(set(gaps))}
    print(f"{a.file}  字数 {chars}  空行の段階 {levels}{rhythm}{summary}")
    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    if not errors and not warns:
        print("OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
