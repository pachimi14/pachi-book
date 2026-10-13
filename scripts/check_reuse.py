#!/usr/bin/env python3
"""再演の点検（機械。2026-10-13）：今回の本文の言い回しが、前の話の採用版に何回出ているかを数える。

なぜ：点検役に渡すのは直前の一話とあらすじだけなので、五話前と同じ仕草・言い回しが出ても比べる材料がなく、
「くどい」「EP001 と同じ反応」は LLM の点検をすり抜けていた（2026-10-13 の原因の切り分け）。
オーナーの決まり（2026-10-10）「前の話の仕草・言い回し・思い出は採用版を grep して 2 回以上なら使わない」をそのまま機械にした。

見るもの：
  1. 言い回しの重なり：今回の本文の文字列（記号と空白を除いて min 字以上）が、前の話の採用版にそのまま出ている所。
     2 話以上に出ていれば［再演］（直す）、1 話なら［既出］（参考。働きが同じなら外す）。
  2. 材料の台帳（blocks/MOTIFS.md）：「検索語」の列がある表で、状態が「封印」の材料の検索語が本文にあれば［封印］（直す）、
     「転換点でだけ」なら［転換点］（働きが変わる案か、オーナーに回数と働きを添えて聞く）。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_reuse.py EP025 V1              # 前の話（EP001〜024）の採用版と比べる
  python ../pachi-book/scripts/check_reuse.py EP025 V1 --min 10     # 重なりとみなす長さ（既定 8 字）
  python ../pachi-book/scripts/check_reuse.py EP025 V1 --all        # あとの話の採用版とも比べる
除外：pachi.json の "names"（人物名）を除いて 5 字に満たない重なり（「ヴァレンスが言う」のような地の文の札）と、
"reuse_ignore" に当たる重なりは出さない。
check_all.py が機械の点検と一緒に回し、［再演］［封印］は対応表の必須に入る。
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

PUNCT = re.compile(r"[\s　、。，．・…―?？!！「」『』〈〉《》【】（）()［］\[\]〔〕―—～〜:：;；\"'“”‘’]")
ADOPTED = re.compile(r"^- 採用版：V(\d+)", re.M)


def normalize(line):
    """記号と空白を除いた文字列と、その各文字の元の位置。"""
    chars, pos = [], []
    for i, ch in enumerate(line):
        if not PUNCT.match(ch):
            chars.append(ch)
            pos.append(i)
    return "".join(chars), pos


def adopted_episodes(target_n, include_later=False):
    """採用版が記録されている話の (EPxxx, 本文)。"""
    out = []
    for summ in sorted((A.WORK / "episodes").glob("EP*/notes/summary.md")):
        ep = summ.parent.parent.name
        n = int(ep[2:])
        if n == target_n or (n > target_n and not include_later):
            continue
        m = ADOPTED.search(summ.read_text(encoding="utf-8"))
        if not m:
            continue
        p = summ.parent.parent / f"V{m.group(1)}.md"
        if p.is_file():
            out.append((ep, p.read_text(encoding="utf-8")))
    return out


def trivial(run, names, ignore):
    """人物名を除くと短い（地の文の札）か、除外の語に当たるか。"""
    if any(ig and ig in run for ig in ignore):
        return True
    rest = run
    for nm in names:
        rest = rest.replace(nm, "")
    return len(rest) < 5


def overlaps(target_lines, corpus, k, ignore, names=()):
    """[(行番号, 重なった文字列, {EP}), ...]。同じ文字列は一つにまとめる。"""
    index = {}
    for ep, text in corpus:
        body, _ = normalize(text)
        for i in range(len(body) - k + 1):
            index.setdefault(body[i:i + k], set()).add(ep)
    found = {}
    for ln, line in enumerate(target_lines, 1):
        body, pos = normalize(line)
        i = 0
        while i <= len(body) - k:
            if body[i:i + k] not in index:
                i += 1
                continue
            j = i
            while j + k <= len(body) and body[j:j + k] in index:
                j += 1
            run = body[i:j + k - 1]
            # 走った範囲の全文が実際に出ている話だけ数える（別々の重なりがつながることがあるため）
            eps = {ep for ep, text in corpus if run in normalize(text)[0]}
            if not eps:   # つながった範囲が一話にも丸ごと出ていなければ、前半の窓だけに縮める
                run = body[i:i + k]
                eps = set(index[run])
                j = i + 1
            if not trivial(run, names, ignore):
                key = run
                if key in found:
                    found[key][2] |= eps
                else:
                    found[key] = [ln, run, set(eps)]
            i = j + k - 1
    return sorted(found.values(), key=lambda r: (-len(r[2]), r[0]))


def motif_hits(text):
    """材料の台帳の「検索語」列を本文に当てる。[(印, 材料, 検索語, 状態, 行番号)]。"""
    motifs = A.read(A.config().get("motifs") or "blocks/MOTIFS.md")
    if not motifs:
        return []
    lines = text.splitlines()
    hits, cols = [], None
    for raw in motifs.splitlines():
        if not raw.startswith("|"):
            cols = None
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if cols is None:
            cols = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        if "検索語" not in cols or "状態" not in cols:
            continue
        row = dict(zip(cols, cells))
        state, keys = row.get("状態", ""), row.get("検索語", "")
        if not keys or keys in ("—", "-", "なし"):
            continue
        mark = "封印" if state.startswith("封印") else ("転換点" if state.startswith("転換点") else None)
        if not mark:
            continue
        for key in [k.strip() for k in re.split(r"[／/]", keys) if k.strip()]:
            where = [i for i, l in enumerate(lines, 1) if key in l]
            if where:
                hits.append((mark, cells[0], key, state, where))
    return hits


def report(ep, ver, k=8, include_later=False, path=None):
    text = Path(path).read_text(encoding="utf-8") if path else A.episode_text(ep, ver)
    target_lines = text.splitlines()
    n = int(ep[2:])
    corpus = adopted_episodes(n, include_later)
    cfg = A.config()
    ignore, names = cfg.get("reuse_ignore") or [], cfg.get("names") or []
    out = []
    runs = overlaps(target_lines, corpus, k, ignore, names)
    again = [r for r in runs if len(r[2]) >= 2]
    once = [r for r in runs if len(r[2]) == 1]
    out.append(f"再演の点検 {ep} {ver}  比べた採用版 {len(corpus)} 話  ［再演］{len(again)}  ［既出］{len(once)}  （{k} 字以上の重なり）")
    for ln, run, eps in again:
        out.append(f"WARN  {ln}行目：［再演］「{run}」（{'・'.join(sorted(eps))} の採用版にも同じ言い回し。2 回以上なら使わない〈2026-10-10 オーナー〉。働きを変えるか別の言い方に）")
    for ln, run, eps in once:
        out.append(f"INFO  {ln}行目：［既出］「{run}」（{'・'.join(sorted(eps))} に同じ言い回し。働きが同じなら外す）")
    for mark, name, key, state, where in motif_hits(text):
        lines = "・".join(str(w) for w in where[:5]) + ("…" if len(where) > 5 else "")
        if mark == "封印":
            out.append(f"WARN  {lines}行目：［封印］「{key}」＝台帳の材料「{name}」（{state}）。働きが同じなら外す。事実として触れるだけなら残して理由を書く")
        else:
            out.append(f"INFO  {lines}行目：［転換点］「{key}」＝台帳の材料「{name}」（{state}）。働きが変わる場面か、回数と働きを添えてオーナーに聞く")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--min", type=int, default=8, help="重なりとみなす長さ（記号を除いた字数。既定 8）")
    ap.add_argument("--all", action="store_true", help="あとの話の採用版とも比べる")
    ap.add_argument("--path", help="本文のパス（版の番号の代わりに）")
    a = ap.parse_args()
    print(report(a.episode, a.version, a.min, a.all, a.path))


if __name__ == "__main__":
    main()
