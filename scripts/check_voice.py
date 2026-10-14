#!/usr/bin/env python3
"""声の点検（2026-10-14 組み替え）：AIっぽい文・書きすぎ・言葉と物・数字・説明の五つだけを、初稿の点検で 1 回見る（オーナーが読む前）。場面の良し悪しは見ない（○△× で決まる）。

旧：良い例とダメな例を並べて渡し、本文の場面ごとに「どちらに近いか」を判定させる。

旧 tools/voice_review.py（kyuketsu-mahou-syojo04、2026-09-30）に、旧 scene_check の「比喩・緊張」と、
「足りない所」（主人公の内心・場面の描写が足りず、オーナーが足した所）を統合した。
一回ごとのぶれが大きい（2026-10-01 の検証で、同じ版でも挙げる文が変わった）ので、既定で2回回す。
二回の重なりは check_all.py がまとめる。
2026-10-13：良い例集（第1章の一言集）とダメな例集（99KB）を外し、WRITE-BRIEF と直前の採用話を渡す。
良い例集が第1章の反応を「良い」と教えるので繰り返しを正解と判定し、ダメな例集は過去の型しか拾えなかった（原因の切り分け）。
オーナーの直しの組は、同じ型の場面のものを --bad-examples で渡すときだけ。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_voice.py EP018 V10
出力: episodes/EPxxx/notes/voice-Vn-<agent>-<回>.md
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

PROMPT = f"""あなたはこの連載の編集者です。作者の文の癖を直す係です（2026-10-14 組み替え。見るのは四つだけ。1 回だけ回す）。
下に資料があります。
1. 書き手の一枚（WRITE-BRIEF）：地の文の仕事と形。この作品の「良い」はここで決まる。
2. 決まりごと一枚（RULES）と、出る人物のカード。
3. 直前の話（採用版）：今の段階の語り方。今回の本文はこれの続きとして読む。
4. 今回の本文。

今回の本文を読み、次の五つだけを見てください。場面の良し悪し・面白さ・地の文の仕事の量は見ません（面白さはオーナーが場面に ○△× を付けて決めます。それを点検で削らない）。
この点検は、オーナーが読む前の初稿に回します（2026-10-14 オーナー「私が読む前に直っていてほしいもの」）。
- AIっぽい文：AならX、BはYと並べて二つ目で落とす対句／気持ちを「覚悟」「言葉を持つ」のような抽象語で外から名づける文／
  「どこを探しても見つからなかった」のような否定の強調の決まり文句／段落や場面の最後を格言・一般論・抽象のまとめで閉じる文／
  人物を一言で評して閉じる文（「〜は、言ったことを全部やる人だ」）／「〜ということだ」「〜の出方だ」のような意味づけの一文。
  挙げないもの：段落の最後の「具体の評価」の短い一文（我ながら苦しい。たぶん逆効果だった。嬉しくない。字面が最悪だ。）。これは語り手の声で、EP001〜012 の段落はほぼこの形で閉じている。
  機械が拾う型（対句否定・否定の強調・抽象語の名づけ）は挙げなくてよい。型にない新しいものだけ。
- 書きすぎ：同じ気持ち・同じ説明を二度書いている所（言い回しの重なりは機械が見る。意味の重なりだけ）。
- 言葉と物：数え方・単位・動詞がその物の絵に合っているか（血を「一本」と数える、霧を「置く」など）。比喩がその場で絵になるか。
- 数字：新しく足した具体の数字で、台帳にないもの（機械が拾うので、機械が見落とす言い方だけ）。
- 説明：読者が常識で補えることを言っている文。物や人の居場所の確認（「ヴァレンスが襟の後ろへ移った」）、理由の説明（なぜ知っているか）、段取り。
  その文がなくても読者が困らないなら挙げる。あとで効く仕込みの一文と区別がつかないときは「仕込みなら残す」と添える（2026-10-14 オーナー「整合のために余計な説明を足すのは AI の悪いところの典型」）。

{A.OUTPUT_RULES}

次の形式だけで答えてください。ツールは使わないでください。褒めるための評価は要りません。引っかかりがなければ表の行を書かず「なし」とだけ書く。

## 声（参考。本文の順）
| ID | 場所（本文を短く引用） | 種類 | 何がおかしいか | 今の文 | 案A | 案B | 推奨 |
|---|---|---|---|---|---|---|---|
| V01 | 「…」 | AIっぽい | … | 「…」 | 「…」 | 「…」 | A：理由を一言 |

種類は AIっぽい／書きすぎ／言葉と物／数字／説明 のどれか。案は「削る」だけにしない（その場で思ったことへの言い換えを一つは出す）。
"""


def prompt(ep, ver, bad_examples=None):
    """束（2026-10-14）：WRITE-BRIEF・RULES とカード（A.canon_context）・直前話・本文。CH-01-voice・OWNER-EYE・FAN-LINE-AIM・BAD-EXAMPLES は渡さない。"""
    return A.SEP.join([PROMPT, A.section("1. 書き手の一枚（WRITE-BRIEF）", A.doc("write_brief")),
                       A.section("2. 決まりごと一枚と出る人物のカード", A.canon_context(ep)),
                       A.section("3. 直前の話（採用版）", A.prev_episode(ep)),
                       A.section("4. 今回の本文", A.episode_text(ep, ver))]) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--runs", type=int, default=1)   # 2026-10-14：2 回のぶれ補正はまとめ役の LLM を要らせていた。1 回
    ap.add_argument("--bad-examples", help="（廃止。2026-10-14 オーナー。BAD-EXAMPLES は使わない。互換のため残す）")
    A.add_model_args(ap)
    a = ap.parse_args()
    p = prompt(a.episode, a.version, a.bad_examples)
    jobs = [(n, p, (n, k)) for n in A.agents(a.agent) for k in range(1, a.runs + 1)]
    for (name, k), text, err in A.run_many(jobs, a.model, a.effort):
        if err:
            print(f"{name}: {err}")
            continue
        out = A.notes_dir(a.episode) / f"voice-{a.version}-{name}-{k}.md"
        print(A.write(out, f"# 声の点検 {a.episode} {a.version}（{name} {k}回目）\n\n{text}"))


if __name__ == "__main__":
    main()
