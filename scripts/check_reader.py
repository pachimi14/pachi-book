#!/usr/bin/env python3
"""初見読者レビュー：あらすじ＋前の話＋今回の話だけを渡し、読者としての感想をもらう。

旧 tools/reader_review.py（kyuketsu-mahou-syojo04、2026-09-30）を移した。旧 review.py（独立レビュー）の役目もここが引き継ぐ。
台帳・メモ・作者の意図は渡さない。採用前の最後に一回回す（2026-10-01：途中で何度も回さない）。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_reader.py EP018 V5
出力: episodes/EPxxx/notes/reader-Vn-<agent>.md（クラウドは claude だけ、ローカルは claude と codex）
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

PROMPT = """あなたは Web 小説サイトでこの連載を追っている一般の読者です。作者ではありません。
下に「これまでのあらすじ」（第1話から前の話の手前まで、ざっと覚えている程度）と、「前の話」「今回の話」の本文があります。ここまで読んできた読者として、今回の話を読んだ感想を正直に書いてください。
褒めるための感想は要りません。つまらなければ、つまらないと書いてください。

読み方の決まり（2026-10-01 オーナー。レビューが外れたため）：
- 感想は「今回の話」の本文だけについて書く。前の話の場面を今回の話のこととして引用しない。
- 【分からない】を付ける前に、あらすじと前の話に答えが書いていないか確かめる。書いてあるなら【分からない】にしない（一言ほしければ【思い出せない】）。連載を全部読んできた読者なら分かることは、分からないとしない。
- 一人称の語り手が変わったときは、あらすじと前の話に出てきた人物の中から誰かを考えてから判断する。

次の形式だけで答えてください。ツールは使わないでください。

## 面白かったところ
- 本文を短く引用して、なぜ面白かったか（なければ「なし」）

## 詰まったところ・意味が分からなかったところ
各項目の頭に、どちらかを付けてください。
【分からない】あらすじと前の話を読んでいても、一度で分からなかった
【思い出せない】昔の話のことだとは分かるが、一言思い出させてほしかった
- 本文を短く引用して、何が分からなかったか（誰が何をしているのか、なぜそうするのか、言葉の意味など。一度で分からなかったものは全部）

## 退屈だったところ
- 読み飛ばしたくなった場面

## 次の話を開きたいか
- 開く／たぶん開く／開かない のどれかと、その理由（引きの一行がどう効いたか）

## こうなっていたら、もっと読みたくなった
- 読者として「ここがこうだったら」と思ったことを、場面ごとに具体的に（詰まったところがどう書いてあれば一度で分かったか、退屈なところをどうすれば読めたか）。作者の意図は推測しなくてよい
- 引き：どんな終わり方なら、すぐ次の話を開いたか（例の一行があれば添える）

## ひとこと
- 読み終えた直後の感想を一、二行
"""

def prompt(ep, ver):
    n = int(ep[2:])
    return (f"{PROMPT}{A.SEP}# これまでのあらすじ\n\n{A.synopsis_before(n - 1) or '（なし）'}{A.SEP}"
            f"# 前の話\n\n{A.prev_episode(ep)}{A.SEP}# 今回の話\n\n{A.episode_text(ep, ver)}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    A.add_model_args(ap)
    a = ap.parse_args()
    p = prompt(a.episode, a.version)
    for name, text, err in A.run_many([(n, p, n) for n in A.agents(a.agent)], a.model, a.effort):
        if err:
            print(f"{name}: {err}（オーナーに報告する）")
            continue
        out = A.notes_dir(a.episode) / f"reader-{a.version}-{name}.md"
        print(A.write(out, f"# 初見読者レビュー {a.episode} {a.version}（{name}）\n\n{text}"))


if __name__ == "__main__":
    main()
