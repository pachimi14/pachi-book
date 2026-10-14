#!/usr/bin/env python3
"""決定との照合（機械。2026-10-14。research/protocol-v3-2026-10-14.md §4h-B）。

LLM の筋の点検が「決定との照合」としてやっていたことのうち、文字列で確かめられるものを機械に移す。
これで LLM の「決定との照合」は「誰が何を知るか」だけになり、「散文の運びと違う」「細部を削れ」の類の必須が出なくなる。

見るもの（その話のメモ blocks/*-memos.md の節から読む）：
  1. 見せ場の台詞：「- 見せ場の台詞」の欄（とその下の行）の「…」が本文にそのままあるか（記号と空白を除いて比べる）。無ければ ERROR
  2. 引き：「- 引き」の欄の文（／で区切る）が本文の最後の十行にあるか。無ければ ERROR
  3. 触れないこと：「- 検索語（触れない）：」の語が本文にあれば WARN
  4. 出る人物：「- 出る人物：」にない人物名（pachi.json names）が本文にあれば INFO
  5. 読者が知らない言葉の候補：本文のカタカナ語（3 字以上）で、前の採用版・SYNOPSIS・world・characters に一度も出ないもの → INFO
  6. 口調の候補：直前の地の文か呼びかけで相手がカナリア・ツグミ・友人と分かる主人公の台詞に「です／ます」→ INFO（意図した所もある）
  7. 台詞に必ず出る語（pachi.json must_say）：その人物の台詞に一度も出なければ INFO
  8. 場面の台詞の量：「◇場面N」で区切った場面に台詞が一つもない、または地の文が 12 行続く → ［警報］

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_decisions.py EP026 V4
check_all.py が機械の点検と一緒に回す。
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402
from check_reuse import normalize, adopted_episodes  # noqa: E402

KATAKANA = re.compile(r"[ァ-ヶー]{3,}")
DIALOGUE_OPEN = "「『〈【"


def memo_section(ep):
    """その話のメモの節（pachi.json chapter_plans のメモから。【旧 の節は飛ばす。欄のある節を優先）。"""
    found = []
    for p in A.memo_files():
        for sec in A._ep_sections(p.read_text(encoding="utf-8"), ep):
            if "【旧" in sec.splitlines()[0]:
                continue
            found.append(sec)
    with_fields = [s for s in found if re.search(r"^- (視点|型|出る人物)[：:]", s, re.M)]
    return (with_fields or found or [""])[0]


def field_block(sec, key):
    """「- key…：」の行と、その下の字下げ行をまとめて返す。"""
    lines = sec.splitlines()
    for i, l in enumerate(lines):
        if re.match(rf"^- {re.escape(key)}", l):
            block = [l]
            for nxt in lines[i + 1:]:
                if nxt.startswith("  "):
                    block.append(nxt)
                else:
                    break
            return "\n".join(block)
    return ""


def norm(s):
    return normalize(s)[0]


def check(ep, ver):
    text = A.episode_text(ep, ver)
    lines = text.splitlines()
    body = norm(text)
    sec = memo_section(ep)
    f = A.memo_fields(ep)
    cfg = A.config()
    names = cfg.get("names") or []
    out = []
    if not sec:
        return [f"INFO  {ep} のメモの節が blocks/*-memos.md にない（決定との照合は飛ばす）"]

    # 1. 見せ場の台詞
    block = re.sub(r"（[^（）]*）", "", field_block(sec, "見せ場の台詞"))   # （…）の注記の中の「」は決定ではない
    quotes = re.findall(r"「([^」]{2,})」", block)
    for q in quotes:
        if norm(q) not in body:
            out.append(f"ERROR 見せ場の台詞「{q}」が本文にない（メモの決定。言い回しを変えたなら、メモを直すかオーナーに聞く）")
    # 2. 引き
    hook = re.sub(r"（[^（）]*）", "", field_block(sec, "引き"))
    hook = re.sub(r"^- 引き[^：:]*[：:]\s*", "", hook)
    hook_sents = []
    for h in re.split(r"[／/]", hook):
        h = h.strip()
        if "。" in h:
            hook_sents.append(h.split("。")[0] + "。")   # 区切りの最初の一文だけが決定。あとは注記
    tail = norm("\n".join(lines[-10:]))
    for h in hook_sents:
        h = h.split("（")[0].strip()
        if h and norm(h) not in tail:
            out.append(f"ERROR 引きの文「{h}」が本文の最後の十行にない（メモの決定）")
    # 3. 触れないこと
    for key in f.get("検索語（触れない）") or []:
        where = [i for i, l in enumerate(lines, 1) if key in l]
        if where:
            out.append(f"WARN  {'・'.join(map(str, where[:5]))}行目：［触れない］「{key}」（メモ「触れないこと」。整合のための説明は足さない。オーナー決定）")
    # 4. 出る人物
    cast = list(f.get("出る人物") or [])
    if any("主人公" in c for c in cast):
        cast += ["ルナリア", "夜霧"]
    if cast:
        for n in names:
            if n in text and not any(n in c or c in n for c in cast):
                where = [i for i, l in enumerate(lines, 1) if n in l]
                out.append(f"INFO  {'・'.join(map(str, where[:3]))}行目：「{n}」はメモの「出る人物」にない（名前を出すだけなら可。登場しているなら事実の候補）")
    # 5. 読者が知らない言葉の候補
    n = int(ep[2:])
    known = "".join(t for _, t in adopted_episodes(n)) + A.doc("synopsis") + A.doc("world") + A.doc("characters") + "".join(names)
    seen = set()
    for i, l in enumerate(lines, 1):
        for w in KATAKANA.findall(l):
            if w in seen or w in known:
                continue
            seen.add(w)
            out.append(f"INFO  {i}行目：読者が知らない言葉の候補「{w}」（前の採用版・あらすじ・台帳に一度も出ない。常識で分かる語なら無視）")
    # 6. 口調の候補（相手がタメ口の人物の台詞に です／ます）
    casual = [nm for nm in ("カナリア", "ツグミ", "友人") if any(nm in c for c in cast)] if cast else ["カナリア", "ツグミ", "友人"]
    for i, l in enumerate(lines, 1):
        if not l.startswith("「"):
            continue
        if not re.search(r"(です|ます|ました|ません)[」。！？…]", l):
            continue
        ctx = "\n".join(lines[max(0, i - 7):i - 1])
        if not any(nm in ctx for nm in casual):
            continue
        if any(nm in ctx for nm in ("シエル", "シラユキ", "ナギ", "ホムラ", "ユイ", "司会", "協会", "客")):
            continue
        out.append(f"INFO  {i}行目：口調の候補 {l.strip()[:30]}（直前に {'/'.join(nm for nm in casual if nm in ctx)}。素で話す相手に丁寧語。意図した決定なら無視）")
    # 7. 台詞に必ず出る語
    for who, words in (cfg.get("must_say") or {}).items():
        if cast and not any(who in c or c in who for c in cast):
            continue
        short = who.replace("大学時代の", "")
        for w in words:
            hit = False
            for i, l in enumerate(lines, 1):
                if l.startswith("「") and w in l:
                    ctx = "\n".join(lines[max(0, i - 9):i - 1])
                    if short in ctx or who in ctx or not cast:
                        hit = True
                        break
            if not hit:
                out.append(f"INFO  {who}の台詞に「{w}」が一度も出ない（RULES の表。女性だと分かる形に、など）")
    # 8. 場面の台詞の量
    scene_mark = re.search(r"場面転換記号[：:]\s*`?([^`\s]+)`?", A.read("style.md") or "")
    mark = scene_mark.group(1) if scene_mark else "◇"
    scenes, cur, start = [], [], 1
    for i, l in enumerate(lines, 1):
        if re.fullmatch(re.escape(mark) + r"場面[0-9０-９]+", l.strip()):
            if cur:
                scenes.append((start, cur))
            cur, start = [], i
            continue
        cur.append(l)
    if cur:
        scenes.append((start, cur))
    if len(scenes) >= 2:
        for start, sc in scenes:
            dlg = sum(1 for l in sc if l.lstrip("　 ")[:1] in DIALOGUE_OPEN)
            if dlg == 0:
                out.append(f"WARN  {start}行目〜：［警報］この場面に台詞が一つもない（見る回で台詞が消える型。語りの仕事を増やすか、掛け合いを一つ）")
            run = best = 0
            for l in sc:
                if l.startswith("　"):
                    run += 1
                    best = max(best, run)
                elif l.strip():
                    run = 0
            if best >= 12:
                out.append(f"WARN  {start}行目〜：［警報］地の文が {best} 行続く場面（報告が続いていないか）")
    return out or ["OK（決定との照合：見せ場の台詞・引き・触れないこと・出る人物・知らない言葉・口調・台詞の量）"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    a = ap.parse_args()
    out = check(a.episode, a.version)
    print(f"決定との照合（機械） {a.episode} {a.version}")
    for l in out:
        print(l)
    return 1 if any(l.startswith("ERROR") for l in out) else 0


if __name__ == "__main__":
    sys.exit(main())
