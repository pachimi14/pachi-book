#!/usr/bin/env python3
"""面白さの型の番号付け：各話の fun（読者が得るもの）の一行を、FUN-TYPES.md の型（1〜2 個）に当てる（2026-10-16）。

  python ../pachi-book/scripts/market_fun_assign.py --out research/story-structure-2026-10 [--extra-own research/story-structure-2026-10/own] [--model claude-sonnet-5-5 --effort low]

出力：<id>/fun_types.json {話番号: [型番号]}（0＝どれにも当たらない）。済んだ作品は飛ばす（印が新しければ作り直す）。
最後に <out>/FUN-TYPES-COUNTS.md（型 × 組 × 位置の数。LLM なし）。数は印の上の数で、面白さの質や因果は示さない。
LLM は作品ごとに一回（型の定義と fun の一行だけを渡す。本文は渡さない）。
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

PROMPT = """下に「面白さの型」の一覧（番号・名前・定義）と、一つの作品の話ごとの「この話で読者が得るもの」の一行があります。
各話の一行を、当てはまる型の番号に当ててください。主なもの 1 つ、はっきり二つ重なるときだけ 2 つ。どれにも当たらなければ 0。
出力は一話一行で「話番号<TAB>番号,番号」だけ（前後に文章を書かない）。
"""


def types_of(fun_md):
    out, cur = [], None
    for l in fun_md.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^### (\d+)\. (.+)", l)
        if m:
            cur = [int(m.group(1)), m.group(2).strip(), ""]
            out.append(cur)
        elif cur and "定義" in l and not cur[2]:
            cur[2] = re.sub(r"^.*定義\**[：:]", "", l).strip()
    return out


def rows_of(d):
    rows = []
    for l in (d / "labels.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            if str(r.get("n", "")).isdigit() and (r.get("fun") or "").strip():
                rows.append((int(r["n"]), r["fun"].strip().replace("\n", " ")))
    return sorted(set(rows))


def assign(d, types_txt, valid, model, effort, log):
    lab, fj = d / "labels.jsonl", d / "fun_types.json"
    if fj.is_file() and fj.stat().st_mtime > lab.stat().st_mtime:
        return
    rows = rows_of(d)
    if not rows:
        return
    body = "\n".join(f"{n}\t{f}" for n, f in rows)
    text, err = A.run("claude", A.SEP.join([PROMPT, A.section("面白さの型", types_txt), A.section(f"話ごとの一行（{len(rows)} 話）", body)]) + "\n", model, effort)
    if err:
        log(f"  {d.name}: {err}")
        return
    res = {}
    for l in text.splitlines():
        m = re.match(r"^\s*(\d+)\s*[\t ]\s*([\d,，、 ]+)\s*$", l)
        if m:
            nums = [int(x) for x in re.split(r"[,，、 ]+", m.group(2).strip()) if x.isdigit()]
            res[m.group(1)] = [x for x in nums if x in valid][:2] or [0]
    miss = len(rows) - len(res)
    fj.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    log(f"  {d.name}: {len(res)} 話" + (f"（{miss} 話は答えが無い）" if miss else ""))


def counts(out, dirs, groups, own_root, types):
    band = lambda n: "1〜10" if n <= 10 else "11〜30" if n <= 30 else "31〜"  # noqa: E731
    c = defaultdict(Counter)   # (組, 位置) → 型
    tot = Counter()
    for d in dirs:
        fj = d / "fun_types.json"
        if not fj.is_file():
            continue
        g = "本作" if own_root and str(d).startswith(str(own_root)) else (groups.get(d.name) or {}).get("group", "？")
        g = {"魔法少女タグの人気作（追跡の外）": "魔法少女"}.get(g, g)
        for n, ts in json.loads(fj.read_text(encoding="utf-8")).items():
            tot[(g, band(int(n)))] += 1
            for t in ts:
                c[(g, band(int(n)))][t] += 1
    keys = sorted(tot, key=lambda k: (k[0], ["1〜10", "11〜30", "31〜"].index(k[1])))
    head = "| 型 | " + " | ".join(f"{g} {b}（{tot[(g, b)]}話）" for g, b in keys) + " |"
    lines = [f"# 面白さの型の出方（{sum(tot.values())} 話。market_fun_assign.py）", "",
             "各欄は、その組・位置の話のうち、その型に当てられた話の割合（%）。一話に二つ当たることがあるので縦の和は 100 を超える。",
             "限界：fun の一行（LLM の印）を、さらに LLM で型に当てたもの。型の当て方の誤りを含む。★・PV との因果は示さない。組の話数が少ない欄（本作・魔法少女の 31〜 など）はぶれが大きい。", "",
             head, "|" + "---|" * (len(keys) + 1)]
    for num, name, _ in types + [[0, "どれにも当たらない", ""]]:
        lines.append(f"| {num}. {name} | " + " | ".join(f"{100 * c[k][num] / tot[k]:.0f}" if tot[k] else "-" for k in keys) + " |")
    (out / "FUN-TYPES-COUNTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out / "FUN-TYPES-COUNTS.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra-own", default=None)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--counts-only", action="store_true")
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    types = types_of(out / "FUN-TYPES.md")
    types_txt = "\n".join(f"{n}. {name}：{df}" for n, name, df in types)
    valid = {n for n, _, _ in types} | {0}
    dirs = [d for d in sorted(out.iterdir()) if d.is_dir() and (d / "labels.jsonl").is_file()]
    own_root = Path(a.extra_own).expanduser() if a.extra_own else None
    if own_root:
        dirs += [d for d in sorted(own_root.iterdir()) if d.is_dir() and (d / "labels.jsonl").is_file()]

    def log(m):
        print(m, flush=True)

    if not a.counts_only:
        with ThreadPoolExecutor(max(1, a.workers)) as pool:
            list(pool.map(lambda d: assign(d, types_txt, valid, a.model, a.effort, log), dirs))
    groups = json.loads((out / "groups.json").read_text(encoding="utf-8")) if (out / "groups.json").is_file() else {}
    counts(out, dirs, groups, own_root, types)


if __name__ == "__main__":
    main()
