#!/usr/bin/env python3
"""市場の分析：取った作品（market_collect.py）の話ごとに印を付け、作品ごとに「話の組み方」を書き出す（2026-10-16）。

目的：あらすじの作り方（大枠・中枠・小枠）を、相談で決めずに人気作の実物から決める。
  - 話ごと（LLM。5 話ずつ、前の話までの状態を持ち回す）：型・事件・主人公が自分からすること・進んだ線（何から何へ、表れ方）・
    出る人物・引きの型・外の反応・日常回か・面白さの一行。本文は写さない（引用は 25 字まで）。
  - 作品ごと（LLM 1 回。印だけを渡す）：線の一覧と段、章の切り方、ブロックの回し、日常回の割合と位置、関係の梯子と表れ方、
    やりとりの変化の実例、引きの型の分布。
  - 機械：字数・台詞の行の割合・空行・配信やスレの印。

使い方（どこで実行してもよい。agent.py の CLI の設定を使う）：
  python ../pachi-book/scripts/market_analyze.py --corpus ~/corpus --out research/story-structure --max-episodes 60
  python ../pachi-book/scripts/market_analyze.py --corpus ~/corpus --out research/story-structure --only 2912051606854917513
  python ../pachi-book/scripts/market_analyze.py --corpus ~/corpus --out research/story-structure --synth-only   # 印が揃った作品の作品ごとのまとめだけ

出力：<out>/<workId>/labels.jsonl（話ごとの印）、state.json（持ち回した状態）、work.md（作品ごとのまとめ）、<out>/index.md（一覧）。
モデルの既定は sonnet / medium（印を付ける作業。点検の固定モデルとは別）。
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

LABEL_PROMPT = """あなたは連載 web 小説（カクヨム）の構成を調べる編集者です。下に、ある作品の連続した数話の本文と、前の話までの「状態」があります。
話ごとに印を付け、状態を更新してください。本文は写さないでください（引用は 25 字まで）。評価や感想は書かず、起きたことと形だけを書きます。

各話に付ける印（JSON）：
- n：話番号（本文の見出しのとおり）
- summary：何が起きたか（2 文以内）
- type：その話の主な型。"事件"（戦い・現場・出動・危機）／"日常・会話"（人と話す・暮らし・買い物・準備）／"外の反応"（配信コメント・掲示板・ニュース・他人の視点が話の中心）／"回想・設定"／"山場"（章やアークの決着）／"その他"
- event：事件（外から来た出来事）が何か。無ければ ""
- hero_act：主人公が自分から始めたこと（見る・待つ・受けるは入れない）。無ければ ""
- lines：この話で進んだ線。各要素 {"line": 線の名前, "from": 前の段（一行）, "to": 今の段（一行）, "shown_by": 読者にそれが分かる表れ方（呼び方が変わった・頼みごとの向き・誰が先に言ったか・秘密の範囲・世間の呼び名・数字、など。短い引用可）}
  線の名前は、状態の「線」にあるものを使う。新しい線が立ったら新しい名前を付ける（例：「世間の目」「〈人物名〉との距離」「力・正体」「敵・謎」「立場・所属」「生活」）。
- characters：出る人物（名前。初出なら末尾に "（初）"）
- hook：{"type": 最後の数行の型（"明かす"／"危機"／"決める"／"関係が動く"／"約束・予告"／"問いが残る"／"笑い"／"日常の締め"／"なし"）, "text": 最後の一文の要約（引用なら 25 字まで）}
- reaction：配信コメント・掲示板・SNS・ニュースの描写があるか（true/false）と、あればその働き（一行）
- slice_of_life：事件が無く、関係や暮らしだけで進む話か（true/false）
- fun：この話で読者が得るもの（一行。「〜が見られる」「〜の答えが出る」の形）
- repeat：前の話までにあった状況・やりとりの再演で、返事や立場が変わっているもの（あれば一行。無ければ ""）

状態（JSON。次の数話に渡す。短く保つ）：
- characters：{名前: {"role": 一行, "calls_hero": 主人公の呼び方, "hero_calls": 主人公からの呼び方, "distance": 今の関係の段（一行）}}（主要人物 8 人まで）
- lines：{線の名前: 今の段（一行）}
- recent：直前 3 話の summary
- chapter：今の章の名前（目次にあれば）

出力は次の JSON だけ（前後に文章を書かない）：
{"episodes": [ {...}, ... ], "state": {...}}
"""

SYNTH_PROMPT = """あなたは連載 web 小説の構成を調べる編集者です。下に、一つの作品の話ごとの印（JSON の行）と目次があります。本文はありません。
この作品の「話の組み方」を、次の見出しで書いてください。事実（話番号つき）だけを書き、良し悪しの評価は書きません。各節は箇条書きで、全体で 1,500 字以内。

## 線（作品を通して変わるもの）
線ごとに：名前／段の推移（何話で何から何へ。5〜8 段まで）／表れ方の種類（呼び方・頼みごとの向き・秘密の範囲・世間の呼び名・数字…）

## 章と山場
章の切れ目（目次と印から）／章ごとの話数／章の問いと答えの出た話／山場の間隔

## ブロックの回し（型の並び）
型（事件・日常・会話・外の反応・山場）がどんな順で並ぶか。よくある並び（3〜5 話）を 2〜3 個、話番号つきで。同じ型が連続する最長／外の反応の回の置き方（独立した回か、話の中の数行か）

## 日常回
事件の無い話の数と割合／どこに置かれているか（事件の直後・山場の前・章の頭…）／その話で進んだ線

## 関係の進展と表れ方
主な相手 2〜3 人について：段の推移（話番号）／各段が読者に分かった表れ方／同じ状況の再演で返事が変わった例（repeat の列から）

## 引き
引きの型の分布（型：回数）／同じ型の最長の連続／章の最後の話の引きの型

## 序盤（1〜3 話）
1 話・2 話・3 話で何を出し、何を出していないか
"""


def mechanical(text):
    body = text.split("\n\n", 1)[1] if "\n\n" in text else text
    lines = [l for l in body.splitlines()]
    nonblank = [l for l in lines if l.strip()]
    dialog = [l for l in nonblank if l.lstrip("　 ").startswith(("「", "『"))]
    board = [l for l in nonblank if l.lstrip("　 ").startswith(("〈", "＞＞", "【", "："))]
    chars = len(re.sub(r"\s", "", body))
    return {"chars": chars, "lines": len(nonblank), "dialog_ratio": round(len(dialog) / max(1, len(nonblank)), 2),
            "board_lines": len(board), "blank_ratio": round((len(lines) - len(nonblank)) / max(1, len(lines)), 2)}


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON がない")
    return json.loads(m.group(0))


def label_work(work_dir, out_dir, model, effort, chunk, max_episodes, log):
    meta = json.loads((work_dir / "meta.json").read_text(encoding="utf-8"))
    eps = sorted((work_dir / "episodes").glob("*.txt"))[:max_episodes]
    out_dir.mkdir(parents=True, exist_ok=True)
    lab_path, state_path = out_dir / "labels.jsonl", out_dir / "state.json"
    done = {}
    if lab_path.is_file():
        for l in lab_path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                try:
                    done[int(r["n"])] = r
                except (KeyError, TypeError, ValueError):
                    continue    # n の無い行は無視（その話は付け直す）
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {"characters": {}, "lines": {}, "recent": [], "chapter": ""}
    toc = "\n".join(f"{c['title'] or '（章なし）'}: {c['episodes'][0] if c['episodes'] else '-'}〜{c['episodes'][-1] if c['episodes'] else '-'}" for c in meta["chapters"])
    todo = [p for p in eps if int(p.stem) not in done]
    log(f"{meta['id']} {meta['title'][:30]}：{len(eps)} 話中 {len(done)} 済、{len(todo)} 話を付ける")
    for i in range(0, len(todo), chunk):
        batch = todo[i:i + chunk]
        texts = []
        mech = {}
        for p in batch:
            t = p.read_text(encoding="utf-8")
            n = int(p.stem)
            mech[n] = mechanical(t)
            texts.append(f"=== 第{n}話（ファイル {p.stem}）\n{t}")
        prompt = A.SEP.join([LABEL_PROMPT,
                             A.section("作品", f"題名：{meta['title']}\nキャッチ：{meta.get('catchphrase') or ''}\n目次の章：\n{toc}"),
                             A.section("前の話までの状態", json.dumps(state, ensure_ascii=False)),
                             A.section("本文（数話）", "\n\n".join(texts))]) + "\n"
        text, err = A.run("claude", prompt, model, effort)
        if err:
            log(f"  {meta['id']} 第{int(batch[0].stem)}話〜：{err}")
            return False
        try:
            data = parse_json(text)
        except Exception as ex:  # noqa: BLE001
            log(f"  {meta['id']} 第{int(batch[0].stem)}話〜：JSON が読めない（{ex}）")
            (out_dir / f"raw-{batch[0].stem}.txt").write_text(text, encoding="utf-8")
            return False
        with lab_path.open("a", encoding="utf-8") as f:
            got = [e for e in data.get("episodes", []) if isinstance(e, dict)]
            for k, e in enumerate(got):
                try:
                    n = int(e.get("n"))
                except (TypeError, ValueError):
                    n = int(batch[k].stem) if k < len(batch) else 0   # n が無ければ渡した順で補う
                    e["n"] = n
                e["mech"] = mech.get(n)
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        state = data.get("state", state)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  {meta['id']} 第{int(batch[0].stem)}〜{int(batch[-1].stem)}話 済")
    return True


def synth_work(work_dir, out_dir, model, effort, log):
    meta = json.loads((work_dir / "meta.json").read_text(encoding="utf-8"))
    lab_path = out_dir / "labels.jsonl"
    if not lab_path.is_file():
        return
    rows = [json.loads(l) for l in lab_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    toc = "\n".join(f"{c['title'] or '（章なし）'}: {c['episodes'][0] if c['episodes'] else '-'}〜{c['episodes'][-1] if c['episodes'] else '-'}" for c in meta["chapters"])
    compact = "\n".join(json.dumps({k: v for k, v in r.items() if k != "mech"}, ensure_ascii=False) for r in rows)
    prompt = A.SEP.join([SYNTH_PROMPT, A.section("作品", f"題名：{meta['title']}\n★{meta.get('totalReviewPoint')}　公開話数 {meta.get('publicEpisodeCount')}\n目次の章：\n{toc}"),
                         A.section(f"話ごとの印（{len(rows)} 話）", compact)]) + "\n"
    text, err = A.run("claude", prompt, model, effort)
    if err:
        log(f"  {meta['id']} まとめ：{err}")
        return
    head = f"# {meta['title']}\n\n★{meta.get('totalReviewPoint')}・公開 {meta.get('publishedAt', '')[:10]}・公開話数 {meta.get('publicEpisodeCount')}・印を付けた話 {len(rows)}\n\n"
    (out_dir / "work.md").write_text(head + text.strip() + "\n", encoding="utf-8")
    log(f"  {meta['id']} まとめ 済")


def index(corpus, out):
    rows = []
    for d in sorted(out.iterdir()):
        if not d.is_dir() or not (corpus / d.name / "meta.json").is_file():
            continue
        meta = json.loads((corpus / d.name / "meta.json").read_text(encoding="utf-8"))
        lab = d / "labels.jsonl"
        n = len(lab.read_text(encoding="utf-8").splitlines()) if lab.is_file() else 0
        rows.append(f"| {meta['title'][:40]} | {meta.get('totalReviewPoint')} | {meta.get('publicEpisodeCount')} | {n} | {'あり' if (d / 'work.md').is_file() else ''} | {d.name} |")
    (out / "index.md").write_text("# 市場の分析：作品の一覧\n\n| 題名 | ★ | 公開話数 | 印を付けた話 | まとめ | id |\n|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--max-episodes", type=int, default=60)
    ap.add_argument("--chunk", type=int, default=5)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--synth-only", action="store_true")
    ap.add_argument("--no-synth", action="store_true")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--synth-model", default="claude-opus-5-5")
    a = ap.parse_args()
    corpus, out = Path(a.corpus).expanduser(), Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    works = [d for d in sorted(corpus.iterdir()) if (d / "meta.json").is_file() and (not a.only or d.name in a.only)]

    def log(msg):
        print(msg, flush=True)

    def one(d):
        try:
            ok = True
            if not a.synth_only:
                ok = label_work(d, out / d.name, a.model, a.effort, a.chunk, a.max_episodes, log)
            if ok and not a.no_synth:
                synth_work(d, out / d.name, a.synth_model, "high", log)
        except Exception as ex:  # noqa: BLE001  一作の失敗で全部を止めない
            log(f"  {d.name}: 失敗 {type(ex).__name__}: {ex}")

    with ThreadPoolExecutor(max(1, a.workers)) as pool:
        list(pool.map(one, works))
    index(corpus, out)
    log(f"一覧：{out / 'index.md'}")


if __name__ == "__main__":
    main()
