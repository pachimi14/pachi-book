#!/usr/bin/env python3
"""点検ツールの回帰テスト：オーナーが直す前の版に点検をかけ、オーナーがあとで直した所をいくつ先に拾えたかを数える。

正解は作品リポジトリの research/tool-backtest/truth.json（オーナーの介入。作者の判断は除く）。
各話の base（直す前の版のコミット）を一時的な作業ツリーに出し、そこで check_all.py を回す。
台帳・ダメな例集・オーナーの目はその時点のものを使い、点検ツールと作品の機械点検（tools/work_checks.py・pachi.json）
だけを今のものにする（答えの漏れを防ぐ）。採点は LLM の判定（拾った／一部／外れ）。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/backtest.py                     # 全話を点検して採点
  python ../pachi-book/scripts/backtest.py --only EP020
  python ../pachi-book/scripts/backtest.py --grade-only        # 点検は回さず、前回の対応表を採点し直す
  python ../pachi-book/scripts/backtest.py --grade-files EP020=a.md,b.md   # ほかの点検の出力を採点（比較用）
出力: research/tool-backtest/result-<日付>.md と、各話の対応表 research/tool-backtest/runs/EPxxx-check.md
ツールを直したら回し、拾った数が減っていないかを見る。leak の付いた項目は、点検の指示文に答えが入っているので別に数える。
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

HERE = Path(__file__).resolve().parent
JUDGE = """あなたは採点係です。ある話の点検結果が、作者があとで直した所（正解の一覧）を先に指摘できていたかを判定します。

各正解について、点検結果の中に、同じ文（または同じ箇所）を挙げて、同じ向きの問題を言っている指摘があるかを見てください。
- 拾った：同じ箇所を挙げ、問題の向きも合っている
- 一部：同じ箇所を挙げているが、問題の向きが違う（例：作者は削ったのに、点検は説明を足せと言う）／近い箇所の別の問題
- 外れ：挙げていない
次の JSON だけを返してください。説明は要りません。
{"results": [{"id": "20-01", "verdict": "拾った|一部|外れ", "by": "点検結果のどの行か（短く。外れなら空）"}]}
"""


def judge(ep_items, report, model, effort):
    lines = "\n".join(f"- {it['id']}：「{it['quote']}」：{it['what']}" for it in ep_items)
    prompt = f"{JUDGE}{A.SEP}# 正解の一覧\n\n{lines}{A.SEP}# 点検結果\n\n{report}\n"
    text, err = A.run("claude", prompt, model, effort)
    if err:
        return None, err
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return {r["id"]: r for r in json.loads(m.group(0))["results"]}, None
    except Exception as e:  # noqa: BLE001
        return None, f"判定の JSON が読めない：{e}"


def run_check(ep, model, effort):
    """base の作業ツリーで check_all を回し、対応表の中身を返す。"""
    work = A.WORK
    tree = Path(os.environ.get("PACHI_BT_DIR", str(work.parent / ".pachi-backtest"))) / ep["episode"]
    if tree.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=work, capture_output=True)
        shutil.rmtree(tree, ignore_errors=True)
    tree.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "worktree", "add", "-q", "--detach", str(tree), ep["base"]], cwd=work,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, f"worktree：{r.stderr.strip()[:200]}"
    for rel in ("tools/work_checks.py", "pachi.json"):
        if (work / rel).is_file():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(work / rel, tree / rel)
    cmd = [sys.executable, str(HERE / "check_all.py"), ep["episode"], ep["version"], "--agent", "claude"]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    r = subprocess.run(cmd, cwd=tree, capture_output=True, text=True, encoding="utf-8")
    out = tree / "episodes" / ep["episode"] / "notes" / f"check-{ep['version']}.md"
    text = out.read_text(encoding="utf-8") if out.is_file() else None
    subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=work, capture_output=True)
    if text is None:
        return None, f"check_all 失敗：{(r.stdout + r.stderr).strip()[-300:]}"
    return text, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default="research/tool-backtest/truth.json")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--grade-only", action="store_true")
    ap.add_argument("--grade-files", nargs="*", help="EP020=a.md,b.md の形。その出力をつないで採点する")
    ap.add_argument("--label", default="check_all")
    A.add_model_args(ap)
    a = ap.parse_args()
    truth = json.loads((A.WORK / a.truth).read_text(encoding="utf-8"))
    eps = [e for e in truth["episodes"] if not a.only or e["episode"] in a.only]
    runs = A.WORK / "research" / "tool-backtest" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    given = dict(x.split("=", 1) for x in (a.grade_files or []))

    def one(ep):
        name = ep["episode"]
        if name in given:
            report = "\n\n".join((A.WORK / f).read_text(encoding="utf-8") for f in given[name].split(","))
        elif a.grade_only:
            p = runs / f"{name}-check.md"
            report = p.read_text(encoding="utf-8") if p.is_file() else None
            if report is None:
                return name, None, f"{p} がない"
        else:
            report, err = run_check(ep, a.model, a.effort)
            if err:
                return name, None, err
            A.write(runs / f"{name}-check.md", report)
        res, err = judge(ep["items"], report, a.model, a.effort)
        return name, res, err

    with ThreadPoolExecutor(len(eps)) as pool:
        results = list(pool.map(one, eps))

    rows, total = [], {"拾った": 0, "一部": 0, "外れ": 0, "n": 0, "leak_hit": 0, "leak_n": 0}
    for ep, (name, res, err) in zip(eps, results):
        if err:
            rows.append(f"## {name}\n\n失敗：{err}\n")
            continue
        hit = part = 0
        lines = []
        for it in ep["items"]:
            r = res.get(it["id"], {"verdict": "外れ", "by": ""})
            v = r["verdict"] if r["verdict"] in ("拾った", "一部", "外れ") else "外れ"
            leak = it.get("leak", False)
            if leak:
                total["leak_n"] += 1
                total["leak_hit"] += v == "拾った"
            else:
                total["n"] += 1
                total[v] += 1
                hit += v == "拾った"
                part += v == "一部"
            lines.append(f"| {it['id']} | {it['kind']} | {it['quote'][:24]} | {v}{'（leak）' if leak else ''} | {r.get('by', '')[:40]} |")
        rows.append(f"## {name}（拾った {hit}・一部 {part}）\n\n| ID | 種類 | 箇所 | 判定 | どの指摘 |\n|---|---|---|---|---|\n" + "\n".join(lines) + "\n")
    n = total["n"] or 1
    score = (total["拾った"] + 0.5 * total["一部"]) / n
    head = (f"# 回帰テスト {datetime.date.today()}（{a.label}）\n\n"
            f"- 対象：{', '.join(e['episode'] for e in eps)}（leak を除く {total['n']} 件）\n"
            f"- 拾った {total['拾った']}・一部 {total['一部']}・外れ {total['外れ']}　点（拾った＋一部×0.5）／件数 = {score:.0%}\n"
            f"- leak の項目：{total['leak_hit']}/{total['leak_n']} 拾った（参考）\n\n")
    out = A.WORK / "research" / "tool-backtest" / f"result-{datetime.date.today()}-{a.label}.md"
    print(A.write(out, head + "\n".join(rows)))
    print(head.strip())


if __name__ == "__main__":
    main()
