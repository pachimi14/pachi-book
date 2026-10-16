#!/usr/bin/env python3
"""①市場分析の結果を、②候補生成・③候補選別が読む共通の形に書き出す（2026-10-16。形は docs/market-data-format.md）。

  python ../pachi-book/scripts/market_export.py --corpus ~/corpus --out research/story-structure [--own research/story-structure/own --own-corpus ~/own]

出力（<out>/export/）：
  works.jsonl     作品ごと 1 行（階層＝章の表、組、★・PV の系列と限界、作品ごとのまとめ work.md の有無）
  episodes.jsonl  話ごと 1 行（階層・展開前の状態・出来事・読者報酬・実現方法・展開後の状態・既出との関係・市場実績）
  fun-types.md    面白さの型の一覧（あれば写す）
無い項目は null。"pending" に、まだ取っていない項目の名前を入れる。既存の印は取り直さない。
"""
import argparse
import json
from pathlib import Path

PENDING_EPISODE = ["reward.types（面白さの型の番号。fun の一行を型に当てる追加の分析）",
                   "delivery.kind（報酬の実現方法の分類：場面／反応／描写。shown_by と reaction.role から後で付ける）",
                   "relation_to_prior.callbacks（既出展開との関係。再演（repeat）以外はまだ無い）",
                   "position.block_inferred（market_blocks.py がまだ回っていない作品では null）"]


def load_jsonl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.is_file() else []


def chapter_of(meta, n):
    for i, c in enumerate(meta.get("chapters") or [], 1):
        eps = c.get("episodes") or []
        if eps and eps[0] <= n <= eps[-1]:
            return {"index": i, "title": c.get("title") or None, "range": [eps[0], eps[-1]]}
    return None


def block_of(blocks, n):
    """推定ブロック（market_blocks.py）。境界の信頼度を持つ。無ければ null。"""
    for i, b in enumerate(blocks or [], 1):
        try:
            if int(b["start"]) <= n <= int(b["end"]):
                return {"index": i, "range": [int(b["start"]), int(b["end"])], "kind": b.get("kind"),
                        "expectation": b.get("expectation"), "reward": b.get("reward"), "state_change": b.get("state_change"),
                        "boundary_confidence": b.get("boundary_confidence"), "boundary_reason": b.get("boundary_reason")}
        except (KeyError, TypeError, ValueError):
            continue
    return None


def market_of(track, n, meta):
    if not track:
        return {"observed": False, "limits": ["ランキング（上位 500／300）に載った日が無く、★・PV の系列が無い"]}
    det = track.get("detail") or {}
    eps = {e["order"]: e for e in det.get("episodes") or []}
    e1 = eps.get(1, {}).get("pv")
    e = eps.get(n, {})
    es = {int(k): v for k, v in (track.get("episode_stars") or {}).items()}
    stars_at = es.get(max((k for k in es if k <= n), default=None)) if es else None
    pub = next((x.get("publishedAt") for x in meta.get("episodes", []) if x.get("n") == n), None)
    limits = ["★は、ランキングに載った日の値を「その日の最新話」に写したもの（日単位。話単位の因果ではない）",
              "話ごとの PV は取得日の一回の写真。公開から日が浅い話ほど低く出る",
              "★・PV と展開の因果は検証していない（同じ日に公開された他の話・外部の露出と混ざる）"]
    return {"observed": True, "pv": e.get("pv"), "pv_rel_ep1": (round(e["pv"] / e1, 3) if e.get("pv") and e1 else None),
            "pv_snapshot_date": det.get("date"), "episode_published_at": pub, "stars_at_episode": stars_at,
            "stars_window_rate": None, "limits": limits}


def export_work(wid, corpus_dir, label_dir, groups, own=False):
    meta = json.loads((corpus_dir / "meta.json").read_text(encoding="utf-8"))
    track = json.loads((corpus_dir / "track.json").read_text(encoding="utf-8")) if (corpus_dir / "track.json").is_file() else None
    labels = sorted((r for r in load_jsonl(label_dir / "labels.jsonl") if str(r.get("n", "")).isdigit()), key=lambda r: int(r["n"]))
    blocks = json.loads((label_dir / "blocks.json").read_text(encoding="utf-8")) if (label_dir / "blocks.json").is_file() else None
    g = "本作" if own else (groups.get(wid) or {}).get("group")
    work = {"id": wid, "title": meta.get("title"), "group": g, "tags": meta.get("tags"), "published_at": meta.get("publishedAt"),
            "stars": meta.get("totalReviewPoint"), "episode_count": meta.get("publicEpisodeCount"),
            "hierarchy": {"chapters": meta.get("chapters"), "blocks_inferred": blocks,
                          "note": "blocks_inferred は印からの推定（境界に信頼度）。固定窓は episodes.position.windows。4 話で切ったものを正式なブロックとは呼ばない"},
            "market": ({"daily_points": len(track.get("daily") or {}), "episode_stars": track.get("episode_stars"),
                        "pv_snapshot_date": (track.get("detail") or {}).get("date"),
                        "limits": ["ランキングに載った日だけ", "話ごとの PV は一回の写真", "因果は未検証"]} if track else None),
            "growth_0914_1001": {k: (groups.get(wid) or {}).get(k) for k in ("stars_0914", "stars_1001", "rel")} if groups.get(wid) else None,
            "synthesis_md": str((label_dir / "work.md").resolve()) if (label_dir / "work.md").is_file() else None,
            "labeled_episodes": len(labels)}
    eps = []
    prev_after = None
    for r in labels:
        n = int(r["n"])
        lines = r.get("lines") or []
        after = {"lines": [{"line": l.get("line"), "to": l.get("to"), "shown_by": l.get("shown_by")} for l in lines],
                 "characters": r.get("characters")}
        before = {"lines": [{"line": l.get("line"), "from": l.get("from")} for l in lines],
                  "carried_from_previous": prev_after}
        rp = r.get("reaction")
        eps.append({
            "work_id": wid, "group": g,
            "position": {"n": n, "title": r.get("title"), "chapter": chapter_of(meta, n),
                         "windows": {"w3": (n - 1) // 3 + 1, "w4": (n - 1) // 4 + 1, "w5": (n - 1) // 5 + 1},   # 固定窓（統計用。物語のまとまりではない）
                         "block_inferred": block_of(blocks, n)},
            "before": before,
            "event": {"type": r.get("type"), "summary": r.get("summary"), "event": r.get("event"), "hero_act": r.get("hero_act")},
            "reward": {"fun": r.get("fun"), "types": None, "hook": r.get("hook"),
                       "reaction": rp if isinstance(rp, dict) else {"present": bool(rp), "role": None},
                       "slice_of_life": r.get("slice_of_life")},
            "delivery": {"kind": None, "shown_by": [l.get("shown_by") for l in lines if l.get("shown_by")],
                         "mech": r.get("mech")},
            "after": after,
            "relation_to_prior": {"repeat": r.get("repeat") or None, "callbacks": None},
            "market": market_of(track, n, meta),
            "pending": PENDING_EPISODE,
        })
        prev_after = {"lines": after["lines"]}
    return work, eps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--own", default=None)
    ap.add_argument("--own-corpus", default=None)
    a = ap.parse_args()
    corpus, out = Path(a.corpus).expanduser(), Path(a.out).expanduser()
    ex = out / "export"
    ex.mkdir(parents=True, exist_ok=True)
    groups = json.loads((out / "groups.json").read_text(encoding="utf-8")) if (out / "groups.json").is_file() else {}
    works, episodes = [], []
    for d in sorted(out.iterdir()):
        if d.is_dir() and (d / "labels.jsonl").is_file() and (corpus / d.name / "meta.json").is_file():
            w, e = export_work(d.name, corpus / d.name, d, groups)
            works.append(w)
            episodes += e
    if a.own and a.own_corpus:
        for d in sorted(Path(a.own).expanduser().iterdir()):
            oc = Path(a.own_corpus).expanduser() / d.name
            if d.is_dir() and (d / "labels.jsonl").is_file() and (oc / "meta.json").is_file():
                w, e = export_work(d.name, oc, d, groups, own=True)
                works.append(w)
                episodes += e
    (ex / "works.jsonl").write_text("\n".join(json.dumps(w, ensure_ascii=False) for w in works) + "\n", encoding="utf-8")
    (ex / "episodes.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in episodes) + "\n", encoding="utf-8")
    if (out / "FUN-TYPES.md").is_file():
        (ex / "fun-types.md").write_text((out / "FUN-TYPES.md").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"works {len(works)}、episodes {len(episodes)} → {ex}")


if __name__ == "__main__":
    main()
