#!/usr/bin/env python3
"""筋の点検：一文ずつ、筋が通っているか・本当のことかを確かめる。

旧 tools/logic_check.py（kyuketsu-mahou-syojo04、2026-10-01）に、旧 scene_check の「理屈・段階」を統合した。
オーナーの直しの多くは文体ではなく筋だった（指示語の指す先がない、前の行とつながらない、台帳と食い違う、
誰の台詞か分からない、人の動きが不自然）。それを書いた側で先に拾う。

2026-10-02：その話の作者の決定（章のあらすじの節とメモの節。agent.episode_plan）を渡すようにした。
渡していなかったため、点検役は決めた筋や会話で決めた引きを知らず、古い BAD-EXAMPLES で「直す」を出し続け、
直し案がそれに合わせて筋から外れた（EP023）。読者として見る項目（指示語・つながり・読み・知らない言葉）では
作者の決定を使わず、決定との照合の項目（事実・立場・理屈・段階・BAD）でだけ使う。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_logic.py EP022 V2
  python ../pachi-book/scripts/check_logic.py EP022 V2 --old "元の文" --new "直した文"
      # チャットで出す直し案を、本文に差し込んだ形で点検する（差し込んだ所と前後三文だけ）
出力: 本文全体は episodes/EPxxx/notes/logic-Vn-<agent>-<回>.md。直し案は標準出力のみ。
通常は check_all.py から呼ばれる。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

CHECKS = """一文ずつ、次の十一を確かめてください。
1. 指示語：「あの」「その」「あいつ」「これ」などの指す先が、直前の数行の中にあるか。読者が一度で分かるか。
2. つながり：前の文・前の台詞から筋が通って続いているか。理由と結果が合っているか。話題の切り替えが強引でないか。
3. 事実：あらすじ・台帳・前の話と食い違っていないか。人物がいない場所にいる、知らないはずのことを知っている、名前や行事を取り違えている。
4. 話し手：誰の台詞か一度で分かるか。その人物の口調（口調カード・これまでの台詞）と合っているか。
5. 人の動き：その場の人たちの動きや反応が自然か（配信のコメントが全員同じ立場、など）。特別扱い（列を飛ばす、係が一人にだけ合図する）が起きていないか。
6. 先のない描写：あとで何も起きない繰り返し、意味のない誇張、根拠のない具体的な数字。
7. 読み・リズム：一度で読めるか。同じ語尾が続く報告調。短い文を三つ並べる細切れ。
8. 読者が知らない言葉：本文で初めて出る固有の言葉・事情。あらすじと前の話にないもの。
9. 立場：話している二人の立場で台詞が成り立つか。相手本人を三人称で呼んでいないか。お礼と頼みが打ち消し合っていないか。その人物がこの状況で本当にそれを言うか。
10. 理屈：主人公の考えや行動の筋が、掟・これまでの話・能力の決まり・この話の中で決まったこと（持ち場・約束・秘密の範囲）と合っているか。秘密を知らない相手に、秘密の中身を書いて送っていないか。
11. 段階：人物の関係や呼び方が今の段階に合っているか（まだ推しでない子を推しと呼ぶ、まだ知らないはずの事実を前提に話す）。

さらに、下の「オーナーが直した例（BAD-EXAMPLES）」の項目に当たる文がないか、項目を一つずつ当ててください。
台帳・あらすじ・前の話で確かめられないことを「根拠がない」と決めつけないでください（作者用の長期の骨格も渡しています）。

「この話の作者の決定（章のあらすじ・メモ）」の使い方（2026-10-02）。資料の性質が二つに分かれます。
- 読者として（1 指示語・2 つながり・7 読み・8 読者が知らない言葉）：読者は作者の決定を読んでいません。本文・前の話・これまでのあらすじだけで判断し、作者の決定で本文の穴を埋めないでください。
- 決定との照合（3 事実・9 立場・10 理屈・11 段階・BAD-EXAMPLES）：作者の決定に書いてある筋・台詞・引き・誰が何を知るか・人物の本当に気にしていることは、すでに決まっています。それ自体を「直す」理由にしないでください。BAD-EXAMPLES や台帳の古い記述が作者の決定とぶつかるときは、作者の決定のほうが新しい判断です（ぶつかっていることは「決定との照合」に一行書く）。
- 本文が作者の決定から外れていたら（決まった中身が抜けた、決まっていない情報・設定が足された、作者の決定で「話さない」とした秘密を話している）、それは必ず挙げてください。いちばん重い指摘です。
- 章のあらすじとメモが食い違っていたら、「決定との照合」にそのまま書いてください（どちらが正しいかは作者が決める）。"""

PROMPT_FULL = f"""あなたはこの連載の校閲者です。文体ではなく、筋と事実を見ます。
下に、これまでのあらすじ、台帳、オーナーの目、オーナーが直した例、前の話、この話の作者の決定（章のあらすじ・メモ）、今回の本文があります。

{CHECKS}

{A.OUTPUT_RULES}

次の形式だけで答えてください。ツールは使わないでください。

## 決定との照合
- 守れている／外れた：本文が作者の決定（章のあらすじ・メモ）から外れた所（なければ「なし」）。決定と BAD-EXAMPLES・台帳がぶつかる所、あらすじとメモの食い違いもここに

## 確実（読者が一度で詰まる・事実と食い違う。本文の順）
- 「本文を短く引用」：番号（1〜11 または BAD の見出し）：何がずれているか：直す方向（一言）

## 迷い（好みや程度の問題。最大5）
- 同じ形式

## 現場の細部（作者が体験していない場の細部に見えるもの）
- 「引用」：何の細部か（なければ「なし」）
"""

PROMPT_SNIPPET = f"""あなたはこの連載の校閲者です。文体ではなく、筋と事実を見ます。
作者が本文の一部を直そうとしています。下の「直したあとの本文」の【直した所】の前後だけを点検してください。
【直した所】の中の文と、その直前・直後の三文だけを挙げてください。それより離れた文の問題は挙げないでください。
特に、直した文が、この話の中ですでに決まっていること（誰がどこにいるか、誰が何を言ったか、人物の気持ちの向き）と食い違っていないかを、
その決まりの文を本文から引用して確かめてください。

{CHECKS}

次の形式だけで答えてください。ツールは使わないでください。

## 判定
- 通る／直す（一行で理由。「直す」は、読者が一度で詰まる・事実と食い違う・作者の決定から外れた、のどれかのときだけ。好みや程度の問題では「通る」にして、下に書く）

## 決定との照合
- 守れている／外れた：直した所が作者の決定（その場面の台詞・本当に気にしていること・誰が何を知るか）を残しているか。外れたなら何が抜けた／足されたか

## 引っかかった文
- 「引用」：番号：何がずれているか：ぶつかる本文の文（引用）
"""


def context(ep):
    n = int(ep[2:])
    return A.SEP.join([A.section("これまでのあらすじ", A.synopsis_before(n)), A.canon_context(),
                       A.section("主人公の掟・語り方", A.doc("voice_rules")), A.section("オーナーの目", A.doc("owner_eye")),
                       A.section("オーナーが直した例（BAD-EXAMPLES）", A.doc("bad_examples")),
                       A.section("前の話", A.prev_episode(ep)),
                       A.section("この話の作者の決定（章のあらすじ・メモ）", A.episode_plan(ep))])


def prompts(ep, ver, old=None, new=None):
    target = A.episode_text(ep, ver)
    if old is None:
        return f"{PROMPT_FULL}{A.SEP}{context(ep)}{A.SEP}# 今回の本文\n\n{target}\n"
    if old not in target:
        sys.exit("--old の文字列が本文に見つからない")
    target = target.replace(old, f"【直した所】{new}【ここまで】", 1)
    return f"{PROMPT_SNIPPET}{A.SEP}{context(ep)}{A.SEP}# 直したあとの本文\n\n{target}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--old")
    ap.add_argument("--new")
    ap.add_argument("--new-file")
    ap.add_argument("--runs", type=int, default=1)
    A.add_model_args(ap)
    a = ap.parse_args()
    snippet = a.old is not None
    new = a.new if a.new is not None else (Path(a.new_file).read_text(encoding="utf-8").rstrip("\n") if a.new_file else None)
    if snippet and new is None:
        sys.exit("--new か --new-file が要る")
    prompt = prompts(a.episode, a.version, a.old, new)
    jobs = [(n, prompt, (n, k)) for n in A.agents(a.agent) for k in range(1, a.runs + 1)]
    for (name, k), text, err in A.run_many(jobs, a.model, a.effort):
        if err:
            print(f"{name}: {err}")
        elif snippet:
            print(f"=== {name} {k}回目 ===\n{text}\n")
        else:
            out = A.notes_dir(a.episode) / f"logic-{a.version}-{name}-{k}.md"
            print(A.write(out, f"# 筋の点検 {a.episode} {a.version}（{name} {k}回目）\n\n{text}"))


if __name__ == "__main__":
    main()
