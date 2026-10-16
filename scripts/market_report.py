#!/usr/bin/env python3
"""市場の分析のまとめ（機械）：market_analyze.py の話ごとの印を作品横断で数える（2026-10-16）。

  python ../pachi-book/scripts/market_report.py --corpus ~/corpus --out research/story-structure > research/story-structure/STATS.md

数えるもの（話の位置 1〜10／11〜30／31〜60／61〜100 で分ける）：
- 型の割合、型の並び（3 話の並びの上位）、同じ型の最長の連続
- 日常回（slice_of_life）の割合と、直前・直後の型
- 一話で進む線の本数の分布、線の種類の割合
- 引きの型の分布、同じ型の連続
- 外の反応（配信コメント・掲示板）がある話の割合
- 字数・台詞の行の割合（中央値）
- 章の長さ（目次の章の話数）
"""
import argparse
import collections
import json
import statistics
from pathlib import Path

BANDS = [(1, 10), (11, 30), (31, 60), (61, 100)]


def band(n):
    for lo, hi in BANDS:
        if lo <= n <= hi:
            return f"{lo}〜{hi}"
    return "101〜"


def line_kind(name):
    if "距離" in name or "関係" in name:
        return "関係"
    for k in ("世間", "力・正体", "正体", "敵", "謎", "立場", "所属", "生活", "帰還", "救助"):
        if k in name:
            return {"世間": "世間の目", "正体": "力・正体", "謎": "敵・謎", "所属": "立場・所属", "帰還": "目的", "救助": "目的"}.get(k, k)
    return "その他"


def group_summary(works, groups):
    """組ごとの要約（1〜30 話に限る。★が付く範囲を比べるため）。"""
    import statistics as st
    agg = {}
    for meta, rows in works:
        g = (groups.get(meta["id"]) or {}).get("group") or "（組なし）"
        a = agg.setdefault(g, {"works": 0, "n": 0, "sol": 0, "event": 0, "daily": 0, "react": 0, "act": 0, "lines3": 0,
                                "hook": collections.Counter(), "chars": [], "dial": [], "same_hook": 0, "repeat": 0})
        a["works"] += 1
        prev_h = None
        for r in rows:
            if int(r.get("n", 0)) > 30:
                continue
            a["n"] += 1
            a["sol"] += bool(r.get("slice_of_life"))
            a["event"] += r.get("type") == "事件"
            a["daily"] += r.get("type") == "日常・会話"
            rp = r.get("reaction")
            a["react"] += bool(rp.get("present") if isinstance(rp, dict) else rp)
            a["act"] += bool((r.get("hero_act") or "").strip())
            a["lines3"] += len(r.get("lines") or []) >= 3
            h = (r.get("hook") or {}).get("type", "なし")
            a["hook"][h] += 1
            a["same_hook"] += (h == prev_h)
            prev_h = h
            a["repeat"] += bool((r.get("repeat") or "").strip())
            m = r.get("mech") or {}
            if m.get("chars"):
                a["chars"].append(m["chars"])
                a["dial"].append(m.get("dialog_ratio", 0))
    print("## 組ごとの要約（1〜30 話だけ。★が付く範囲）\n")
    print("| 組 | 作品 | 話 | 事件の回 | 日常・会話の回 | 日常回（事件なし） | 外の反応あり | 自分から動く | 線 3 本以上 | 再演で返事が変わる | 引きが前の話と同じ型 | 引き：日常の締め | 引き：危機 | 引き：約束・予告 | 引き：笑い | 字数 | 台詞の行 |")
    print("|---|" + "---|" * 16)
    for g, a in sorted(agg.items(), key=lambda kv: -kv[1]["works"]):
        n = a["n"] or 1
        hk = a["hook"]
        print(f"| {g} | {a['works']} | {a['n']} | {pct(a['event'], n)} | {pct(a['daily'], n)} | {pct(a['sol'], n)} | {pct(a['react'], n)} | {pct(a['act'], n)} | {pct(a['lines3'], n)} | {pct(a['repeat'], n)} | {pct(a['same_hook'], n)} | "
              f"{pct(hk['日常の締め'], n)} | {pct(hk['危機'], n)} | {pct(hk['約束・予告'] + hk['予告・約束'] + hk['予告'], n)} | {pct(hk['笑い'], n)} | "
              f"{int(st.median(a['chars'])) if a['chars'] else '-'} | {st.median(a['dial']):.2f} |" if a["dial"] else f"| {g} | {a['works']} | {a['n']} | — |")
    print()


def pct(c, total):
    return f"{100 * c / total:.0f}%" if total else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--groups", default=None, help="groups.json（作品ごとの組）。あれば組ごとの要約表を先頭に出す")
    ap.add_argument("--extra", default=None, help="比べたい作品の corpus（自作など。印は <out>/own/ にある前提）")
    a = ap.parse_args()
    corpus, out = Path(a.corpus).expanduser(), Path(a.out).expanduser()
    groups = json.loads(Path(a.groups).read_text(encoding="utf-8")) if a.groups and Path(a.groups).is_file() else {}
    works = []
    for d in sorted(out.iterdir()):
        lab = d / "labels.jsonl"
        meta_p = corpus / d.name / "meta.json"
        if not lab.is_file() or not meta_p.is_file():
            continue
        rows = sorted((json.loads(l) for l in lab.read_text(encoding="utf-8").splitlines() if l.strip()), key=lambda r: int(r.get("n", 0)))
        works.append((json.loads(meta_p.read_text(encoding="utf-8")), rows))
    if a.extra:
        ex = Path(a.extra).expanduser()
        for d in sorted(ex.iterdir()):
            lab = out / "own" / d.name / "labels.jsonl"
            if (d / "meta.json").is_file() and lab.is_file():
                rows = sorted((json.loads(l) for l in lab.read_text(encoding="utf-8").splitlines() if l.strip()), key=lambda r: int(r.get("n", 0)))
                works.append((json.loads((d / "meta.json").read_text(encoding="utf-8")), rows))
                groups[d.name] = {"group": "本作"}
    print(f"# 作品横断の数え上げ（{len(works)} 作、{sum(len(r) for _, r in works)} 話）\n")
    if groups:
        group_summary(works, groups)

    # 型の割合（位置ごと）
    types = collections.defaultdict(collections.Counter)
    sol = collections.defaultdict(lambda: [0, 0])
    nlines = collections.Counter()
    kinds = collections.Counter()
    hooks = collections.defaultdict(collections.Counter)
    react = collections.defaultdict(lambda: [0, 0])
    chars = collections.defaultdict(list)
    dial = collections.defaultdict(list)
    triples = collections.Counter()
    hero_act = collections.defaultdict(lambda: [0, 0])
    sol_ctx = collections.Counter()
    runs_type, runs_hook = [], []
    for meta, rows in works:
        prev_t, run_t, prev_h, run_h = None, 0, None, 0
        for i, r in enumerate(rows):
            n = int(r.get("n", i + 1))
            b = band(n)
            t = r.get("type", "その他")
            types[b][t] += 1
            s = bool(r.get("slice_of_life"))
            sol[b][0] += s
            sol[b][1] += 1
            if s:
                before = rows[i - 1].get("type") if i > 0 else "—"
                after = rows[i + 1].get("type") if i + 1 < len(rows) else "—"
                sol_ctx[f"前：{before} → 後：{after}"] += 1
            ls = r.get("lines") or []
            nlines[min(len(ls), 4)] += 1
            for l in ls:
                kinds[line_kind(l.get("line", ""))] += 1
            h = (r.get("hook") or {}).get("type", "なし")
            hooks[b][h] += 1
            rp = r.get("reaction")
            present = rp.get("present") if isinstance(rp, dict) else bool(rp)
            react[b][0] += bool(present)
            react[b][1] += 1
            ha = bool((r.get("hero_act") or "").strip())
            hero_act[b][0] += ha
            hero_act[b][1] += 1
            m = r.get("mech") or {}
            if m.get("chars"):
                chars[b].append(m["chars"])
                dial[b].append(m.get("dialog_ratio", 0))
            if i >= 2:
                triples[" → ".join(x.get("type", "?") for x in rows[i - 2:i + 1])] += 1
            if t == prev_t:
                run_t += 1
            else:
                if prev_t:
                    runs_type.append((run_t, prev_t))
                prev_t, run_t = t, 1
            if h == prev_h:
                run_h += 1
            else:
                if prev_h:
                    runs_hook.append((run_h, prev_h))
                prev_h, run_h = h, 1
        runs_type.append((run_t, prev_t))
        runs_hook.append((run_h, prev_h))

    def table(title, counters):
        print(f"## {title}\n")
        keys = sorted({k for c in counters.values() for k in c})
        print("| 位置 | " + " | ".join(keys) + " | 話数 |")
        print("|---|" + "---|" * (len(keys) + 1))
        for b, c in counters.items():
            tot = sum(c.values())
            print(f"| {b} | " + " | ".join(pct(c[k], tot) for k in keys) + f" | {tot} |")
        print()

    table("型の割合（話の位置ごと）", dict(sorted(types.items())))
    print("## 型の並び（3 話。上位 12）\n")
    for k, v in triples.most_common(12):
        print(f"- {k}：{v}")
    print()
    print("## 同じ型の連続（最長 5 件）\n")
    for n, t in sorted(runs_type, reverse=True)[:5]:
        print(f"- {t} が {n} 話")
    print()
    print("## 日常回（事件が無い話）\n")
    print("| 位置 | 日常回 | 話数 | 割合 |\n|---|---|---|---|")
    for b, (s, tot) in sorted(sol.items()):
        print(f"| {b} | {s} | {tot} | {pct(s, tot)} |")
    print("\n前後の型（上位 8）：")
    for k, v in sol_ctx.most_common(8):
        print(f"- {k}：{v}")
    print()
    print("## 一話で進む線の本数\n")
    tot = sum(nlines.values())
    print("| 本数 | 話数 | 割合 |\n|---|---|---|")
    for k in sorted(nlines):
        print(f"| {k if k < 4 else '4 以上'} | {nlines[k]} | {pct(nlines[k], tot)} |")
    print("\n線の種類（進んだ回数）：")
    for k, v in kinds.most_common():
        print(f"- {k}：{v}")
    print()
    table("引きの型（話の位置ごと）", dict(sorted(hooks.items())))
    print("## 同じ引きの型の連続（最長 5 件）\n")
    for n, t in sorted(runs_hook, reverse=True)[:5]:
        print(f"- {t} が {n} 話")
    print()
    print("## 外の反応（配信コメント・掲示板・ニュース）がある話・主人公が自分から動く話\n")
    print("| 位置 | 外の反応あり | 自分から動く | 話数 |\n|---|---|---|---|")
    for b in sorted(react):
        print(f"| {b} | {pct(react[b][0], react[b][1])} | {pct(hero_act[b][0], hero_act[b][1])} | {react[b][1]} |")
    print()
    print("## 字数と台詞の行の割合（中央値）\n")
    print("| 位置 | 字数 | 台詞の行 |\n|---|---|---|")
    for b in sorted(chars):
        if chars[b]:
            print(f"| {b} | {int(statistics.median(chars[b]))} | {statistics.median(dial[b]):.2f} |")
    print()
    print("## 章の長さ（目次に章がある作品）\n")
    lens = []
    for meta, _ in works:
        chs = [len(c["episodes"]) for c in meta.get("chapters", []) if c.get("title")]
        if chs:
            lens.extend(chs)
            print(f"- {meta['title'][:30]}：{chs}")
    if lens:
        print(f"\n章の話数：中央値 {statistics.median(lens)}、最小 {min(lens)}、最大 {max(lens)}（{len(lens)} 章）")


if __name__ == "__main__":
    main()
