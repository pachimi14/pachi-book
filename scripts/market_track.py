#!/usr/bin/env python3
"""★・フォロワー・PV の時系列を「データで楽しむカクヨム」（rank-kakuyomu.click。データは CC BY 4.0）の API から取る（2026-10-16）。

何のために：★が「どの話数まで」付き続けたかを見る。合計の★だけでは、序盤で稼ぎきって残り 100 話は微増、という作品を見分けられない（2026-10-16 オーナー）。
  - 日ごとのランキング（日間総合 500・日間現代ファンタジー 300・週間現代ファンタジー 300）から、載った作品の ★・フォロワー・総 PV・1 話目 PV を日付ごとに拾う。
  - 作品ごとの詳細（載っていた最新の日）から、話ごとの PV（読者がどの話で減るか）を取る。
  - 公開日の目次（market_collect.py の meta.json）と合わせ、★の日次を「その日の最新話」に写す → 話数ごとの★の増え方。

  python ../pachi-book/scripts/market_track.py --corpus ~/corpus            # corpus にある作品全部
  python ../pachi-book/scripts/market_track.py --corpus ~/corpus --only <id> ...

保存：<corpus>/_rank/<date>-<period>-<genre>.json（生のランキング。あるものは取り直さない）、<corpus>/<id>/track.json（日次の系列・話ごとの PV・話数ごとの★）。
1 秒に 1 回以下。
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://rank-kakuyomu.click/api/v1"
UA = "pachi-book-research (contact via GitHub pachimi14/pachi-book)"
DELAY = 1.1
LISTS = [("daily", "general"), ("daily", "action"), ("weekly", "action")]


def get_json(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return None if e.code == 404 else {"_error": f"{e.code}"}
    except Exception as ex:  # noqa: BLE001
        return {"_error": str(ex)}
    if not body.lstrip().startswith("{"):
        return None
    return json.loads(body)


def fetch_lists(corpus, dates, log):
    rank_dir = corpus / "_rank"
    rank_dir.mkdir(exist_ok=True)
    for d in dates:
        for period, genre in LISTS:
            p = rank_dir / f"{d}-{period}-{genre}.json"
            if p.is_file():
                continue
            data = get_json(f"/dates/{d}/rankings/{period}/{genre}")
            time.sleep(DELAY)
            if not data or "_error" in data:
                log(f"  {d} {period}/{genre}: {data.get('_error') if data else 'なし'}")
                p.write_text("{}", encoding="utf-8")
                continue
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        log(f"  {d} 済")


def series_from_lists(corpus, ids):
    """作品ごとの日次：{id: {date: {stars, followers, total_pv, first_episode_pv, star_delta, ranks:{...}}}}"""
    out = {i: {} for i in ids}
    for p in sorted((corpus / "_rank").glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not data or "rankings" not in data:
            continue
        date, rest = p.stem[:10], p.stem[11:]          # 2026-10-15-daily-action
        period, genre = rest.split("-", 1)
        for r in data["rankings"]:
            wid = str(r.get("work_id"))
            if wid not in out:
                continue
            row = out[wid].setdefault(date, {"ranks": {}})
            for k in ("stars", "followers", "total_pv", "first_episode_pv", "star_delta", "follower_delta"):
                if r.get(k) is not None and k not in row:
                    row[k] = r[k]
            row["ranks"][f"{period}/{genre}"] = r.get("rank")
    return out


def episode_stars(meta, daily):
    """日次の★を、その日の最新話の番号に写す。{n: stars_at_that_day（最後の日）}。公開日の順で。"""
    eps = sorted(meta["episodes"], key=lambda e: e["publishedAt"])
    pub = [(e["publishedAt"][:10], e["n"]) for e in eps]
    out = {}
    for date in sorted(daily):
        s = daily[date].get("stars")
        if s is None:
            continue
        n = 0
        for d, k in pub:
            if d <= date:
                n = max(n, k)
        out[n] = s
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--no-lists", action="store_true", help="ランキングの日次を取り直さない")
    a = ap.parse_args()
    corpus = Path(a.corpus).expanduser()

    def log(m):
        print(m, flush=True)

    ids = [d.name for d in sorted(corpus.iterdir()) if (d / "meta.json").is_file() and (not a.only or d.name in a.only)]
    dates_doc = get_json("/dates")
    if not dates_doc:
        sys.exit("日付一覧が取れない")
    dates = dates_doc["available_dates"]
    log(f"日付 {len(dates)}（{dates[0]}〜{dates[-1]}）、作品 {len(ids)}")
    if not a.no_lists:
        fetch_lists(corpus, dates, log)
    series = series_from_lists(corpus, ids)
    for wid in ids:
        meta = json.loads((corpus / wid / "meta.json").read_text(encoding="utf-8"))
        daily = series.get(wid, {})
        track_p = corpus / wid / "track.json"
        track = json.loads(track_p.read_text(encoding="utf-8")) if track_p.is_file() else {}
        # 詳細（話ごとの PV）：載っていた最新の日から。取れていなければ取る
        if "detail" not in track:
            for d in sorted(daily, reverse=True):
                det = get_json(f"/dates/{d}/works/{wid}")
                time.sleep(DELAY)
                if det and "_error" not in det:
                    hist = get_json(f"/dates/{d}/work-histories/{wid}/30d")
                    time.sleep(DELAY)
                    track["detail"] = {"date": d, "profile": det.get("profile"), "accesses": det.get("accesses"),
                                       "episodes": [{k: e.get(k) for k in ("order", "title", "published_at", "pv")} for e in det.get("episodes", [])],
                                       "rankings": det.get("rankings"), "history_30d": (hist or {}).get("days")}
                    break
            if "detail" not in track:
                track["detail"] = None
        track["daily"] = daily
        track["episode_stars"] = episode_stars(meta, daily)
        track_p.write_text(json.dumps(track, ensure_ascii=False, indent=1), encoding="utf-8")
        es = track["episode_stars"]
        span = f"話{min(es)}〜{max(es)}：★{es[min(es)]}→{es[max(es)]}" if es else "ランキングに載った日なし"
        det = track.get("detail")
        pv = f"、話ごとの PV {len(det['episodes'])} 話（{det['date']}）" if det else "、詳細なし"
        log(f"{wid} {meta['title'][:28]}：日次 {len(daily)} 日、{span}{pv}")


if __name__ == "__main__":
    main()
