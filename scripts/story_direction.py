#!/usr/bin/env python3
"""ストーリーテラー：次の章（以降）の展開の方向を、市場の実績と作品のこれまでの流れから提案する（2026-10-01）。

方向だけを出す。あらすじや本文は書かない。オーナーが案から選び、そのあと章のあらすじ（templates/work/chapters/STORY.md）を書く。
オーナーは出されたものを見てから判断するので、出すものの質を上げるための役。

渡すもの：
  作品：concept.md、arc.md、preferences.md、長期の骨格、話ごとのあらすじ、章の計画・あらすじ（chapters/ と pachi.json の chapter_plans）
  市場：pachi.json の market（作品リポジトリに写した市場の調べ。例 research/market/development-patterns.md）
使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/story_direction.py --target "第3章以降"
  python ../pachi-book/scripts/story_direction.py --target "第3章" --note "関西編に入る前提で"
出力: chapters/DIRECTION-<日付>.md
"""
import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

PROMPT = """あなたはこの連載のストーリーテラー（物語の方向を決める編集者）です。
作者は出された案を見てから判断します。あなたの仕事は、作者が選びやすい、根拠のある「次の章の方向」の案を出すことです。
あらすじや本文は書きません。方向だけを出します。

下に、作品の核・作者の好み・長期の骨格・これまでのあらすじ・章の計画と、カクヨムの同じ系統の作品の実績（伸びた作品の展開の型）があります。

次の順で書いてください。

## 1. 今作の現状（10行以内）
- これまでの章で、どんな展開をしてきたか（舞台・関係・正体の明かし方・敵・読者へのご褒美の種類）。
- 市場の型に照らして、今作がすでにやっていること／まだやっていないこと。
- 長期の骨格で予定している大きな出来事（作者の決めたこと）と、その時期。

## 2. 方向の案（2〜3個）
各案に：
- 名前（一行）
- この章（ここから）で何をするか：3〜5行
- 読者が受け取るご褒美：何で笑い、何で報われ、何が気になって次を開くか
- 市場の型との対応：どの型か、似た展開で伸びた作品名と、その話数のあたり
- 今作の流れから見た理由：張ってある伏線・長期の骨格・前の章の終わり方とのつながり
- 危ない所：読者が離れやすい型（停滞・同じ舞台の繰り返し・売りの停止など）や、今作の売り・作者の好みとぶつかる所
- 章の長さの目安と、章の最後の場面の候補

案どうしは、はっきり違う方向にしてください（舞台を替えるか／関係を深めるか／正体の明かしを進めるか、など）。
長期の骨格で作者が決めていることは崩さず、その上で、どの順で・どの見せ方でやるかの違いを出してください。

## 3. どの案にも共通して入れるとよいこと（3〜5個）
市場の型から、今作がまだ使っていないもの。

## 4. 作者に決めてほしいこと（二択で、多くて5つ）
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="次の章", help="例：第3章以降")
    ap.add_argument("--note", default="", help="作者からの前提（任意）")
    A.add_model_args(ap)
    a = ap.parse_args()
    cfg = A.config()
    plans = sorted((A.WORK / "chapters").glob("*.md")) + [A.WORK / p for p in cfg.get("chapter_plans", [])]
    plan_text = A.SEP.join(f"# 章の計画・あらすじ（{p.relative_to(A.WORK)}）\n\n{p.read_text(encoding='utf-8')}"
                           for p in plans if p.is_file() and not p.name.startswith("DIRECTION"))
    market = A.SEP.join(f"# 市場の調べ（{m}）\n\n{A.read(m)}" for m in cfg.get("market", []) if A.read(m))
    if not market:
        print("警告：pachi.json の market に市場の調べがない。作品の資料だけで提案する。")
    goal = cfg.get("goal", "")
    sch = cfg.get("schedule")
    if sch:
        goal += (f"\n公開の予定：{sch.get('start')} 公開開始、初日 {sch.get('first_day')} 話、以降毎日 {sch.get('per_day')} 話（{sch.get('note', '')}）。"
                 "目標の期間に、どの話まで公開されるかを計算して、どの章が目標に効くかを書く")
    prompt = A.SEP.join([PROMPT + f"\n対象：{a.target}\n作品の目標：{goal or 'なし'}（目標があるときは、各案がその目標にどう効くか、市場の条件のどれを満たすかを書く）\n作者からの前提：{a.note or 'なし'}",
                         A.section("作品の核", A.read("concept.md")), A.section("章の並び", A.read("arc.md")),
                         A.section("作者の好み", A.read("preferences.md")), A.section("長期の骨格（作者用）", A.doc("long_arcs")),
                         A.section("これまでのあらすじ", A.doc("synopsis")), plan_text, market]) + "\n"
    name = A.agents(a.agent)[0]
    text, err = A.run(name, prompt, a.model, a.effort or "xhigh")
    if err:
        sys.exit(err)
    out = A.WORK / "chapters" / f"DIRECTION-{datetime.date.today()}.md"
    out.parent.mkdir(exist_ok=True)
    print(A.write(out, f"# 展開の方向の案（{a.target}。{datetime.date.today()}）\n\n"
                       f"ストーリーテラー（../pachi-book/scripts/story_direction.py）の提案。作者が選んでから章のあらすじを書く。\n\n{text}"))


if __name__ == "__main__":
    main()
