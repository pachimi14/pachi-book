#!/usr/bin/env python3
"""物語上のまとまり（推定ブロック）：話ごとの印から、作品ごとに「短期の期待を作り、報酬を届け、次の状態へ移る」まとまりを推定する（2026-10-16）。

作者が意図した境界は分からないので、境界ごとに信頼度（高／中／低）と根拠を残す。
固定窓（3・4・5 話）は統計用で、market_export.py が機械で付ける。こちらは別物。4 話ずつ切ったものを正式なブロックとは呼ばない。

  python ../pachi-book/scripts/market_blocks.py --out research/story-structure [--only <id>] [--model claude-sonnet-5-5 --effort medium]

出力：<out>/<id>/blocks.json  [{start, end, kind, expectation, reward, state_change, boundary_confidence, boundary_reason}]
LLM は作品ごとに一回（印だけを渡す。本文は渡さない）。
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

PROMPT = """あなたは連載 web 小説の構成を調べる編集者です。下に、一つの作品の話ごとの印（JSON の行。本文はありません）と、目次の章があります。
話の並びを「物語上のまとまり」に分けてください。まとまりとは、3〜5 話ほどで「短期の期待を作り（問いや危機や約束）、報酬を届け（答え・決着・関係の段が上がる）、次の状態へ移る」単位です。
長さは固定しません（2 話や 7 話のまとまりがあってよい）。作者が意図した境界は分からないので、境界ごとに信頼度と根拠を書いてください。
- 高：事件の発生から短期の決着までが印で追え、次の話で状態が明らかに変わる
- 中：期待と報酬は追えるが、どちらの話で切れるか二通りある
- 低：日常・会話が続き、まとまりの切れ目が印からは分からない（便宜上の区切り）
章の見出しがある作品では、章の境界を越えるまとまりは作らないでください。

出力は次の JSON だけ（前後に文章を書かない）：
{"blocks": [
  {"start": 1, "end": 4, "kind": "事件の発生〜短期決着／関係の進展／外の反応の回／日常の積み上げ／山場と余波 のどれか",
   "expectation": "このまとまりで作られる短期の期待（一行）", "reward": "届いた報酬（一行）", "state_change": "次の状態へ何が移ったか（一行）",
   "boundary_confidence": "高／中／低", "boundary_reason": "根拠（一行。話番号を含める）"}
]}
"""


def infer(d, model, effort, log):
    lab = d / "labels.jsonl"
    bj = d / "blocks.json"
    if not lab.is_file() or (bj.is_file() and bj.stat().st_mtime > lab.stat().st_mtime):
        return   # 印が増えていなければ作り直さない
    rows = sorted((json.loads(l) for l in lab.read_text(encoding="utf-8").splitlines() if l.strip()), key=lambda r: int(r.get("n", 0)) if str(r.get("n", "")).isdigit() else 0)
    if len(rows) < 3:
        return
    compact = "\n".join(json.dumps({k: v for k, v in r.items() if k in ("n", "type", "summary", "event", "hero_act", "lines", "hook", "slice_of_life", "fun")}, ensure_ascii=False) for r in rows)
    toc = ""
    state = d / "state.json"
    if state.is_file():
        toc = (json.loads(state.read_text(encoding="utf-8")) or {}).get("chapter") or ""
    prompt = A.SEP.join([PROMPT, A.section("目次の章（分かる範囲）", toc or "（章の情報なし）"), A.section(f"話ごとの印（{len(rows)} 話）", compact)]) + "\n"
    text, err = A.run("claude", prompt, model, effort)
    if err:
        log(f"  {d.name}: {err}")
        return
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0))
    except Exception as ex:  # noqa: BLE001
        log(f"  {d.name}: JSON が読めない（{ex}）")
        (d / "blocks-raw.txt").write_text(text, encoding="utf-8")
        return
    (d / "blocks.json").write_text(json.dumps(data.get("blocks", []), ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  {d.name}: まとまり {len(data.get('blocks', []))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--effort", default="medium")
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    dirs = [d for d in sorted(out.iterdir()) if d.is_dir() and (d / "labels.jsonl").is_file() and (not a.only or d.name in a.only)]

    def log(m):
        print(m, flush=True)

    with ThreadPoolExecutor(max(1, a.workers)) as pool:
        list(pool.map(lambda d: infer(d, a.model, a.effort, log), dirs))


if __name__ == "__main__":
    main()
