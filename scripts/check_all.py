#!/usr/bin/env python3
"""本文の点検を一度に回し、一枚の対応表にまとめる（2026-10-01）。

回すもの（並行）：
  機械：check_episode.py（作品の tools/work_checks.py を含む）
  筋：check_logic.py（1回）
  声：check_voice.py（2回。ぶれを補う）
そのあと、まとめ役が重なりを一つにし、重い順に番号を振って notes/check-Vn.md に書く。
表の「対応」は書き手が埋める（直した／直さない：理由）。全部埋まるまでオーナーに渡さない。
（2026-10-01 の検証：ツールが拾ったのに直さずに渡した所があり、オーナーがあとで直していた）

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_all.py EP023 V2          # 点検して対応表を作る
  python ../pachi-book/scripts/check_all.py EP023 V2 --status # 対応が空の行を数える（0 でなければ終了コード 1）
初見読者レビュー（check_reader.py）は別。採用前の最後に一回回す。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402
import check_logic  # noqa: E402
import check_voice  # noqa: E402

MERGE = """あなたはこの連載の編集長です。一つの話に、別々の点検係が出した指摘を一枚の対応表にまとめます。
資料：機械の点検、筋の点検、声の点検（同じ係が2回。挙げる所が回ごとにぶれる）、今回の本文。

まとめ方：
- 同じ文・同じ問題を指す指摘は一つにまとめる。
- 本文に照らして間違っている指摘（本文に書いてあることを「ない」と言う、など）は落とす。
- 声の点検で一回にしか出ていない指摘は、本文に照らして当たっているものだけ残す。
- 機械の点検の WARN は、本文を見て直す価値のあるものだけ残す（台帳で決まった数字、意図した型は落とす）。
- 重い順に並べる：①事実・筋の食い違い ②読者が一度で詰まる ③AIっぽい文・ダメな例の型 ④足りない所・書きすぎ ⑤リズム・数字。
- 直した文は書かない。直す方向を一言だけ書く。
- 筋の点検の「確実」は、本文に照らして間違っていない限り全部残す。行の数で削らない（2026-10-01：25行で打ち切って当たりを落としていた）。

次の形式だけで答えてください。ツールは使わないでください。

| ID | 場所（本文を短く引用） | 種類 | 何がおかしいか | 直す方向 | 出どころ | 対応 |
|---|---|---|---|---|---|---|
| C01 | 「…」 | 事実 | … | … | 筋・声2回 | 未 |

種類は次のどれか：事実／つながり／指示語／話し手／立場／段階／人の動き／読者が知らない言葉／現場の細部／AIっぽい／ダメな例／比喩／緊張／足りない／書きすぎ／リズム／数字
出どころは「機械」「筋」「声1回」「声2回」の組み合わせ。対応の欄は全部「未」にする。
"""


def mechanical(ep, ver):
    script = Path(__file__).resolve().parent / "check_episode.py"
    r = subprocess.run([sys.executable, str(script), f"episodes/{ep}/{ver}.md"], capture_output=True, text=True,
                       encoding="utf-8", cwd=A.WORK)
    return (r.stdout + r.stderr).strip()


def status(ep, ver):
    p = A.notes_dir(ep) / f"check-{ver}.md"
    if not p.is_file():
        sys.exit(f"{p.relative_to(A.WORK)} がない（先に点検を回す）")
    rows = [l for l in p.read_text(encoding="utf-8").splitlines() if re.match(r"\|\s*C\d+", l)]
    open_rows = [l for l in rows if re.search(r"\|\s*未\s*\|?\s*$", l)]
    print(f"{p.relative_to(A.WORK)}：{len(rows)} 行、対応が空 {len(open_rows)} 行")
    for l in open_rows:
        print("  " + l[:80])
    sys.exit(1 if open_rows else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--status", action="store_true")
    A.add_model_args(ap)
    a = ap.parse_args()
    ep, ver = a.episode, a.version
    if a.status:
        status(ep, ver)
    name = A.agents(a.agent)[0]
    mech = mechanical(ep, ver)
    jobs = [(name, check_logic.prompts(ep, ver), "logic"),
            (name, check_voice.prompt(ep, ver), "voice-1"),
            (name, check_voice.prompt(ep, ver), "voice-2")]
    got = {}
    for tag, text, err in A.run_many(jobs, a.model, a.effort):
        if err:
            print(f"{tag}: {err}")
            text = f"（失敗：{err}）"
        got[tag] = text
        kind = "筋の点検" if tag == "logic" else "声の点検"
        out = A.notes_dir(ep) / (f"logic-{ver}-{name}.md" if tag == "logic" else f"{tag.replace('voice', 'voice-' + ver + '-' + name)}.md")
        A.write(out, f"# {kind} {ep} {ver}（{name} {tag}）\n\n{text}")
    merge_prompt = A.SEP.join([MERGE, A.section("機械の点検", mech), A.section("筋の点検", got["logic"]),
                               A.section("声の点検（1回目）", got["voice-1"]), A.section("声の点検（2回目）", got["voice-2"]),
                               A.section("今回の本文", A.episode_text(ep, ver))])
    table, err = A.run(name, merge_prompt, a.model, a.effort)
    if err:
        sys.exit(f"まとめ：{err}")
    out = A.notes_dir(ep) / f"check-{ver}.md"
    head = (f"# 点検の対応表 {ep} {ver}\n\n"
            "「対応」を書き手が埋める：直した（どう直したか一言）／直さない：理由。全部埋めてからオーナーに渡す。\n"
            f"確かめ方：`python ../pachi-book/scripts/check_all.py {ep} {ver} --status`\n"
            "直した版で点検をかけ直すときは、新しい版の番号で回す。\n\n")
    print(A.write(out, head + table + f"\n\n## 機械の点検（元の出力）\n\n```\n{mech}\n```"))


if __name__ == "__main__":
    main()
