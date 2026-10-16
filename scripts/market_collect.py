#!/usr/bin/env python3
"""市場の収集：カクヨムの作品の目次と本文を、調べのために手元へ取る（2026-10-16）。

目的は分析（展開・関係・引きの型・話の組み方）で、本文を書き手に渡したり写したりするためではない。
取った本文はリポジトリに入れない（著作物。既定の保存先は作業フォルダの外）。1 秒に 1 回以下で取る（robots.txt の Crawl-delay）。

  python ../pachi-book/scripts/market_collect.py --out ~/corpus 2912051606854917513 2912051606811828023
  python ../pachi-book/scripts/market_collect.py --out ~/corpus --ids ids.txt --max-episodes 60

保存：<out>/<workId>/meta.json（題名・キャッチ・公開日・★・話数・字数・章と各話の題名と公開日）、episodes/NNN.txt（1 行目に題名、2 行目に公開日、空行、本文。空行は保つ）。
あるものは取り直さない。
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

UA = "pachi-book-research (contact via GitHub pachimi14/pachi-book)"
DELAY = 1.2


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def next_data(h):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', h, re.S)
    return json.loads(m.group(1)) if m else None


def work_meta(work_id):
    h = get(f"https://kakuyomu.jp/works/{work_id}")
    d = next_data(h)
    ap = d["props"]["pageProps"]["__APOLLO_STATE__"]
    work = ap.get(f"Work:{work_id}")
    if not work:
        sys.exit(f"{work_id}: Work が見つからない")
    tags = []
    for k in ("tagLabels", "tags"):
        v = work.get(k)
        if isinstance(v, list):
            tags = [t if isinstance(t, str) else t.get("name", "") for t in v]
    chapters = []
    episodes = []
    n = 0
    for k, v in ap.items():
        if isinstance(v, dict) and v.get("__typename") == "TableOfContentsChapter":
            ch = v.get("chapter")
            ch_title = ""
            if isinstance(ch, dict) and "__ref" in ch:
                ch_title = (ap.get(ch["__ref"]) or {}).get("title", "")
            elif isinstance(ch, dict):
                ch_title = ch.get("title", "")
            eps = []
            for ref in v.get("episodeUnions", []):
                e = ap.get(ref.get("__ref", ""))
                if not e or e.get("__typename") != "Episode":
                    continue
                n += 1
                row = {"n": n, "id": e["id"], "title": e.get("title", ""), "publishedAt": e.get("publishedAt", "")}
                eps.append(row["n"])
                episodes.append(row)
            chapters.append({"title": ch_title, "episodes": eps})
    meta = {
        "id": work_id, "title": work.get("title"), "catchphrase": work.get("catchphrase"),
        "introduction": work.get("introduction"), "publishedAt": work.get("publishedAt"),
        "lastEpisodePublishedAt": work.get("lastEpisodePublishedAt"),
        "totalReviewPoint": work.get("totalReviewPoint"), "publicEpisodeCount": work.get("publicEpisodeCount"),
        "totalCharacterCount": work.get("totalCharacterCount"), "serialStatus": work.get("serialStatus"),
        "genre": work.get("genre"), "tags": tags, "chapters": chapters, "episodes": episodes,
        "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return meta


P = re.compile(r'<p id="p\d+"(?: class="(blank)")?>(.*?)</p>', re.S)


def episode_text(work_id, ep_id):
    h = get(f"https://kakuyomu.jp/works/{work_id}/episodes/{ep_id}")
    body = h.split('class="widget-episodeBody', 1)
    if len(body) < 2:
        return None
    lines = []
    for blank, inner in P.findall(body[1]):
        if blank:
            lines.append("")
            continue
        t = re.sub(r"<rp>.*?</rp>", "", inner)
        t = re.sub(r"<ruby>(.*?)<rt>(.*?)</rt></ruby>", r"|\1《\2》", t)
        t = re.sub(r"<br\s*/?>", "\n", t)
        t = re.sub(r"<[^>]+>", "", t)
        lines.append(html.unescape(t))
    return "\n".join(lines).strip("\n") + "\n"


def collect(work_id, out, max_episodes):
    d = out / work_id
    d.mkdir(parents=True, exist_ok=True)
    mp = d / "meta.json"
    if mp.is_file():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    else:
        meta = work_meta(work_id)
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(DELAY)
    print(f"{work_id} {meta['title'][:40]} 話数 {len(meta['episodes'])} ★{meta['totalReviewPoint']}")
    ed = d / "episodes"
    ed.mkdir(exist_ok=True)
    for e in meta["episodes"][:max_episodes]:
        p = ed / f"{e['n']:03d}.txt"
        if p.is_file():
            continue
        text = episode_text(work_id, e["id"])
        if text is None:
            print(f"  {e['n']:03d} 本文が取れない（{e['id']}）")
        else:
            p.write_text(f"{e['title']}\n{e['publishedAt']}\n\n{text}", encoding="utf-8")
        time.sleep(DELAY)
    print(f"  取れた話 {len(list(ed.glob('*.txt')))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--ids", dest="ids_file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-episodes", type=int, default=60)
    a = ap.parse_args()
    ids = list(a.ids)
    if a.ids_file:
        ids += [l.split()[0] for l in Path(a.ids_file).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    out = Path(a.out).expanduser()
    for i in ids:
        try:
            collect(i, out, a.max_episodes)
        except Exception as ex:  # noqa: BLE001
            print(f"{i}: 失敗 {ex}")


if __name__ == "__main__":
    main()
