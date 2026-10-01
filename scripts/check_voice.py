#!/usr/bin/env python3
"""声の点検：良い例とダメな例を並べて渡し、本文の場面ごとに「どちらに近いか」を判定させる。

旧 tools/voice_review.py（kyuketsu-mahou-syojo04、2026-09-30）に、旧 scene_check の「比喩・緊張」と、
「足りない所」（主人公の内心・場面の描写が足りず、オーナーが足した所）を統合した。
一回ごとのぶれが大きい（2026-10-01 の検証で、同じ版でも挙げる文が変わった）ので、既定で2回回す。
二回の重なりは check_all.py がまとめる。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_voice.py EP018 V10
出力: episodes/EPxxx/notes/voice-Vn-<agent>-<回>.md
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

PROMPT = f"""あなたはこの連載の編集者です。作者の文の癖を直す係です。
下に資料があります。
1. 良い例：この作品で、読者とオーナーが「面白い」と言った場面の抜き出し。主人公は本気で、本気の向きがファンの側にずれている。見たものに、心の中で実況・考察・ツッコミを入れる。
2. ダメな例：オーナーが「面白くない」「AIっぽい」と直した文と、直したあとの文の組。
3. 主人公の掟・語り方、オーナーの目。
4. 今回の本文。

今回の本文を場面ごとに読み、次を見てください。
- AIっぽい文：オーナーが一番嫌う型です。一つ残らず挙げてください。
  AならX、BはYと並べて二つ目で落とす対句／気持ちを「覚悟」「言葉を持つ」のような抽象語で外から名づける文／
  「どこを探しても見つからなかった」のような否定の強調の決まり文句／段落や場面の最後を格言・結論・感想の要約で閉じる文／
  人物を一言で評して閉じる文（「〜は、言ったことを全部やる人だ」）。
- ダメな例に近い文：主人公がカメラになっている、説明の一文、昔と今の対比、など。
- 比喩：その場で絵が浮かぶ近さか。作りすぎ・普通は言わない言い回しになっていないか。
- 緊張：この瞬間に主人公が本当に気にしていること（怖いこと、嬉しいこと、隠したいこと）が書けているか。表面の冗談や「ファンらしい一言」で埋めていないか。
- 足りない所：主人公の内心や、その場の人の様子が足りず、読者が置いていかれる所。大事な人との場面（久しぶりに会う人、推しとの初めての握手など）を数行で流していないか。
- 書きすぎ：主人公の心配・説明が重なって、同じ気持ちを二度書いている所。

{A.OUTPUT_RULES}

次の形式だけで答えてください。ツールは使わないでください。褒めるための評価は要りません。

## AIっぽい文（全部）
- 「本文を引用」：どの型か：直す方向（一言）

## ダメな例に近い文・比喩
- 「本文を引用」：どの種類か：直す方向（一言）

## 緊張・足りない所・書きすぎ
- 場面（冒頭の数語）：緊張／足りない／書きすぎ：何が抜けているか・重なっているか（一行）

## 場面ごとの判定
- 場面（冒頭の数語）：良い例に近い／ダメな例に近い／どちらとも言えない：理由を一行

## 一番よかった場面
- 本文を引用して一つ
"""


def prompt(ep, ver):
    return A.SEP.join([PROMPT, A.section("1. 良い例", A.doc("good_examples")),
                       A.section("2. ダメな例", A.doc("bad_examples")),
                       A.section("3. 主人公の掟・語り方", A.doc("voice_rules")), A.section("3. オーナーの目", A.doc("owner_eye")),
                       A.section("4. 今回の本文", A.episode_text(ep, ver))]) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--runs", type=int, default=2)
    A.add_model_args(ap)
    a = ap.parse_args()
    p = prompt(a.episode, a.version)
    jobs = [(n, p, (n, k)) for n in A.agents(a.agent) for k in range(1, a.runs + 1)]
    for (name, k), text, err in A.run_many(jobs, a.model, a.effort):
        if err:
            print(f"{name}: {err}")
            continue
        out = A.notes_dir(a.episode) / f"voice-{a.version}-{name}-{k}.md"
        print(A.write(out, f"# 声の点検 {a.episode} {a.version}（{name} {k}回目）\n\n{text}"))


if __name__ == "__main__":
    main()
