#!/usr/bin/env python3
"""★と PV の時系列のまとめ（機械）：market_track.py の track.json から、作品ごとに「★が何話目まで付いたか」「読者が何話目で減るか」を表にする（2026-10-16）。

  python ../pachi-book/scripts/market_track_report.py --corpus ~/corpus [--extra ~/own] > research/story-structure/TRACK.md

列：
- ★の半分／8 割が付いた話数：ランキングに載っていた期間の最新の★を 100 として、その半分・8 割に達した日の「最新話の番号」。小さいほど序盤で稼ぎきっている。
- 話の窓ごとの★：その窓に公開された話の期間に増えた★（1 話あたり）。
- 残り：1 話目の PV を 100 とした、n 話目の PV。50 を切る話＝半分の読者が降りた話。
- 直近 7 日の★／日：今も伸びているか。
"""
import argparse
import json
import statistics
from pathlib import Path

MILESTONES = (10, 20, 30, 50, 100)
WINDOWS = ((1, 10), (11, 30), (31, 60), (61, 100))


def retention(eps):
    if not eps or not eps[0].get("pv"):
        return {}, None, None
    pv1 = eps[0]["pv"]
    by = {e["order"]: e["pv"] for e in eps if e.get("pv") is not None}
    rel = {n: round(100 * by[n] / pv1) for n in (2, 5, 10, 20, 30, 50, 100) if n in by}
    half = next((n for n in sorted(by) if n > 1 and by[n] < 0.5 * pv1), None)
    third = next((n for n in sorted(by) if n > 1 and by[n] < 0.3 * pv1), None)
    return rel, half, third


def star_curve(es):
    """es: {話番号: ★}（観測できた日の最新話ごと）。"""
    if not es:
        return None
    ks = sorted(es)
    last = es[ks[-1]]
    first_n, first_s = ks[0], es[ks[0]]
    half = next((k for k in ks if es[k] >= 0.5 * last), None)
    p80 = next((k for k in ks if es[k] >= 0.8 * last), None)
    wins = {}
    for lo, hi in WINDOWS:
        inside = [k for k in ks if lo <= k <= hi]
        if len(inside) >= 2:
            gained = es[inside[-1]] - es[inside[0]]
            wins[f"{lo}〜{hi}"] = round(gained / max(1, inside[-1] - inside[0]))
    miles = {m: es[max(k for k in ks if k <= m)] for m in MILESTONES if any(k <= m for k in ks)}
    return {"range": (first_n, ks[-1]), "first": first_s, "last": last, "half": half, "p80": p80, "windows": wins, "miles": miles}


def recent_rate(daily):
    ds = sorted(daily)
    pts = [(d, daily[d]["stars"]) for d in ds if daily[d].get("stars") is not None]
    if len(pts) < 2:
        return None
    tail = pts[-8:]
    days = (len(tail) - 1) or 1
    return round((tail[-1][1] - tail[0][1]) / days, 1), tail[-1][0]


def row(work_dir, groups):
    meta = json.loads((work_dir / "meta.json").read_text(encoding="utf-8"))
    tp = work_dir / "track.json"
    if not tp.is_file():
        return None
    t = json.loads(tp.read_text(encoding="utf-8"))
    es = {int(k): v for k, v in (t.get("episode_stars") or {}).items() if int(k) > 0}
    sc = star_curve(es)
    det = t.get("detail") or {}
    rel, half, third = retention(det.get("episodes") or [])
    rr = recent_rate(t.get("daily") or {})
    g = (groups.get(work_dir.name) or {}).get("group", "")
    return {"id": work_dir.name, "title": meta["title"][:26], "group": g, "stars": meta.get("totalReviewPoint"),
            "eps": meta.get("publicEpisodeCount"), "pub": (meta.get("publishedAt") or "")[:10], "sc": sc, "rel": rel,
            "half": half, "third": third, "rr": rr}


def fmt_sc(sc):
    if not sc:
        return "—", "—", "—", "—"
    w = sc["windows"]
    return (f"{sc['range'][0]}〜{sc['range'][1]}話（★{sc['first']}→{sc['last']}）", str(sc["half"] or "—"), str(sc["p80"] or "—"),
            "／".join(f"{k}:{v}" for k, v in w.items()) or "—")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--extra", default=None, help="比べたい作品の corpus（自作など）")
    ap.add_argument("--groups", default=None)
    a = ap.parse_args()
    corpus = Path(a.corpus).expanduser()
    groups = json.loads(Path(a.groups).read_text(encoding="utf-8")) if a.groups and Path(a.groups).is_file() else {}
    rows = [r for d in sorted(corpus.iterdir()) if d.is_dir() and (d / "meta.json").is_file() and (r := row(d, groups))]
    extra = []
    if a.extra:
        extra = [r for d in sorted(Path(a.extra).expanduser().iterdir()) if d.is_dir() and (d / "meta.json").is_file() and (r := row(d, groups))]
        for r in extra:
            r["group"] = "本作"
    rows.sort(key=lambda r: -(r["stars"] or 0))
    print("# ★と PV の時系列（データで楽しむカクヨム。ランキングに載った日だけ）\n")
    print("## ★が何話目まで付いたか\n")
    print("| 作品 | 組 | ★ | 話数 | 観測できた範囲 | ★の半分が付いた話 | 8 割が付いた話 | 窓ごとの★／話（1〜10／11〜30／31〜60／61〜100） | 直近 7 日の★／日 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in extra + rows:
        if not r["sc"]:
            continue
        rng, half, p80, wins = fmt_sc(r["sc"])
        rr = f"{r['rr'][0]}（{r['rr'][1][5:]}）" if r["rr"] else "—"
        print(f"| {r['title']} | {r['group']} | {r['stars']} | {r['eps']} | {rng} | {half} | {p80} | {wins} | {rr} |")
    print("\n## 読者が何話目で減るか（1 話目の PV＝100）\n")
    print("| 作品 | 組 | ★ | 2話 | 5話 | 10話 | 20話 | 30話 | 50話 | 100話 | 50 を切る話 | 30 を切る話 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in extra + rows:
        if not r["rel"]:
            continue
        c = [str(r["rel"].get(n, "—")) for n in (2, 5, 10, 20, 30, 50, 100)]
        print(f"| {r['title']} | {r['group']} | {r['stars']} | " + " | ".join(c) + f" | {r['half'] or '—'} | {r['third'] or '—'} |")
    # 組ごとの中央値
    print("\n## 組ごとの中央値\n")
    by = {}
    for r in rows:
        if r["rel"]:
            by.setdefault(r["group"], []).append(r)
    print("| 組 | 作品数 | 10話の残り | 20話の残り | 30話の残り | 50話の残り | ★の 8 割が付いた話 |")
    print("|---|---|---|---|---|---|---|")
    for g, rs in by.items():
        def med(key):
            v = [r["rel"][key] for r in rs if key in r["rel"]]
            return f"{statistics.median(v):.0f}（{len(v)}）" if v else "—"
        p80 = [r["sc"]["p80"] for r in rs if r["sc"] and r["sc"]["p80"]]
        print(f"| {g} | {len(rs)} | {med(10)} | {med(20)} | {med(30)} | {med(50)} | {statistics.median(p80):.0f} |" if p80 else f"| {g} | {len(rs)} | {med(10)} | {med(20)} | {med(30)} | {med(50)} | — |")


if __name__ == "__main__":
    main()
