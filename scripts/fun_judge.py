#!/usr/bin/env python3
"""面白さの判定役の試験（2026-10-13）：オーナーが判断する前に判定役の答えを記録し、あとでオーナーの判断と比べる。

経緯：「LLM はオーナーの版を選べない（10 回中 5 回）」（research/fix-experiment、2026-10-01）は、話まるごとの組 5 つ、
判定役に渡したのは第1章の一言集だけ、組には筋の直しも混ざっていた。n=5 で資料も偏っていたので、根拠として弱い。
一方、展開の判定役（plot_judge）はオーナーが直した展開 30 問で 73〜82% 当てた。面白さを機械で当てられるかは、
新しい工程の単位（一行の案・場面の ○△×・初稿二本）で測り直す。

決まり（答えの漏れを防ぐ）：
- 判定はオーナーが印を付ける「前」に回し、出力をコミットしてからオーナーに渡す。印が付いたあとに回しても試験にならない
  （付いていたら止まる。--force で回せるが、結果は参考にしかならない）。
- 判定役にはオーナーの印を渡さない。渡すのは本文と、条件ごとの資料だけ。
- 条件は plain（本文だけ）と full（書き手の一枚・章の背骨・人物台帳・好み・これまでのオーナーの印）。モデルは --model で変える
  （書き手と同じモデルは盲点が同じ、という仮説も一緒に測る）。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/fun_judge.py pitch chapters/notes/PITCH-EP025-030-2026-10-14.md          # 一行の案：読みたい／読みたくないを当てる（plain と full）
  python ../pachi-book/scripts/fun_judge.py pitch <file> --cond full --model claude-sonnet-5-5           # 条件・モデルを変えて
  python ../pachi-book/scripts/fun_judge.py scenes EP025 V1          # 場面ごとの ○△× を当てる。notes/owner-marks-V1.md（オーナーが印を書く表）も作る
  python ../pachi-book/scripts/fun_judge.py draft EP025 V1 V2        # 初稿二本：どちらを土台にするか（両方の順）
  python ../pachi-book/scripts/fun_judge.py score pitch <file>       # オーナーの印（読みたい の列）と比べる
  python ../pachi-book/scripts/fun_judge.py score scenes EP025 V1    # notes/owner-marks-V1.md と比べる
  python ../pachi-book/scripts/fun_judge.py score draft EP025 --owner V2
出力：<fun_judge_dir>/（既定 research/fun-judge/）predict-*.md（判定）、score-*.md（当たり）、choices-pitch.jsonl（オーナーの印。full の例に使う）。
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

MARK_YES = ("読みたい", "○", "◯", "o", "O", "yes")
MARK_NO = ("読みたくない", "×", "x", "X", "no")


def fdir():
    d = A.WORK / (A.config().get("fun_judge_dir") or "research/fun-judge")
    d.mkdir(parents=True, exist_ok=True)
    return d


def head():
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=A.WORK)
    return r.stdout.strip() or "?"


def stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def model_tag(model):
    return (model or A.config().get("model") or "default").replace("claude-", "")


# ---- 資料 ----

def full_context(kind):
    cfg = A.config()
    plans = cfg.get("chapter_plans") or []
    parts = [A.section("書き手の一枚（WRITE-BRIEF）", A.doc("write_brief")),
             A.section("章の背骨", A.read(plans[0]) if plans else ""),
             A.section("台帳：登場人物（今の距離と反応）", A.doc("characters")),
             A.section("作品の好み", A.read("preferences.md"))]
    if kind == "pitch":
        parts.append(A.section("これまでのオーナーの印（一行の案 → 読みたい／読みたくない）", past_pitch_choices()))
    return A.SEP.join(parts)


def past_pitch_choices(limit=80):
    p = fdir() / "choices-pitch.jsonl"
    if not p.is_file():
        return ""
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()][-limit:]
    return "\n".join(f"- {r['mark']}：{r['text']}" for r in rows)


# ---- 一行の案 ----

PITCH_ASK = """あなたは、この連載のオーナー（作者）の判断を当てる係です。
下に、次の話の「一行の案」が話ごとに並んでいます。オーナーはこの一覧を読み、一行ごとに「読みたい」か「読みたくない」を付けます。
各行について、オーナーがどちらを付けるかを当ててください。一般論の面白さではなく、この作品と、このオーナーが選んできたもので判断してください。
資料がある場合は、章の背骨から外れる案・今の人物の距離に合わない案・封印した材料の再演は「読みたくない」に寄ります。
ただし筋の整合は見ません（整合の監査は別）。読みたくなるかだけを答えてください。

答えは次の形だけ（一行一案。番号は案の # の欄そのまま）。ツールは使わないでください。
25-1: 読みたい｜理由を一言
25-2: 読みたくない｜理由を一言
最後に、話ごとに「いちばん読みたい一本」を書いてください。
EP025 最上: 25-3
"""

ROW = re.compile(r"^\|\s*(\d+-\d+)\s*\|(.*)\|\s*$")


def pitch_rows(text):
    """[(id, 行の中身（印の欄を除く）, 印の欄)]。表の最後の列が「読みたい」の欄。"""
    rows = []
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        if len(cells) < 2 or set("".join(cells)) <= set("-: "):
            continue
        rows.append((m.group(1), " ／ ".join(c for c in cells[:-1] if c), cells[-1]))
    return rows


def owner_mark(cell):
    c = cell.strip()
    if not c:
        return None
    if c.startswith(MARK_YES):
        return "読みたい"
    if c.startswith(MARK_NO):
        return "読みたくない"
    return None


def strip_marks(text):
    """表の最後の列（読みたい）を空にして渡す。"""
    out = []
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            if len(cells) >= 2 and not set("".join(cells)) <= set("-: "):
                cells[-1] = ""
                line = f"| {m.group(1)} | " + " | ".join(cells) + " |"
        out.append(line)
    return "\n".join(out)


def pitch(path, conds, model, effort, force):
    text = Path(path).read_text(encoding="utf-8")
    rows = pitch_rows(text)
    if not rows:
        sys.exit("一行の案の表（| 25-1 | … |）が見つからない")
    marked = [r for r in rows if owner_mark(r[2])]
    if marked and not force:
        sys.exit(f"オーナーの印が {len(marked)} 行に付いている。印の前に回すのが試験（--force で回せるが参考止まり）")
    body = strip_marks(text)
    stem = Path(path).stem
    jobs = []
    for cond in conds:
        ctx = full_context("pitch") + A.SEP if cond == "full" else ""
        prompt = PITCH_ASK + A.SEP + ctx + "# 一行の案\n\n" + body + "\n"
        jobs.append((A.agents()[0], prompt, cond))
    for cond, out, err in A.run_many(jobs, model, effort):
        if err:
            print(f"{cond}: {err}")
            continue
        pred = dict(re.findall(r"^(\d+-\d+)\s*[:：]\s*(読みたい|読みたくない)", out or "", re.M))
        tag = f"{cond}-{model_tag(model)}"
        p = fdir() / f"predict-pitch-{stem}-{tag}.md"
        A.write(p, f"# 面白さの判定役の試験：一行の案 {stem}（{tag}）\n\n実行 {stamp()}　コミット {head()}　"
                   f"オーナーの印の前に記録{'（--force：印のあと）' if force else ''}\n\n{out}")
        (fdir() / f"predict-pitch-{stem}-{tag}.json").write_text(json.dumps(pred, ensure_ascii=False, indent=1), encoding="utf-8")
        print(p.relative_to(A.WORK), f"判定 {len(pred)}/{len(rows)} 行")


def score_pitch(path):
    text = Path(path).read_text(encoding="utf-8")
    rows = pitch_rows(text)
    truth = {rid: owner_mark(cell) for rid, _, cell in rows if owner_mark(cell)}
    if not truth:
        sys.exit("オーナーの印（読みたい／読みたくない）がまだ付いていない")
    stem = Path(path).stem
    out = [f"# 当たり：一行の案 {stem}", "", f"オーナーの印 {len(truth)} 行（読みたい {sum(v == '読みたい' for v in truth.values())}）。採点 {stamp()}", "",
           "| 条件・モデル | 一致 | 読みたいの再現（オーナーの読みたいを判定も読みたいと言った） | 読みたいの精度（判定の読みたいのうちオーナーも読みたい） | 外した行 |",
           "|---|---|---|---|---|"]
    for pj in sorted(fdir().glob(f"predict-pitch-{stem}-*.json")):
        pred = json.loads(pj.read_text(encoding="utf-8"))
        tag = pj.stem.replace(f"predict-pitch-{stem}-", "")
        both = [r for r in truth if r in pred]
        hit = [r for r in both if pred[r] == truth[r]]
        ty = [r for r in both if truth[r] == "読みたい"]
        py = [r for r in both if pred[r] == "読みたい"]
        rec = sum(1 for r in ty if pred[r] == "読みたい")
        prec = sum(1 for r in py if truth[r] == "読みたい")
        miss = "・".join(f"{r}（{truth[r]}）" for r in both if pred[r] != truth[r])
        out.append(f"| {tag} | {len(hit)}/{len(both)} | {rec}/{len(ty)} | {prec}/{len(py)} | {miss or 'なし'} |")
    base = max(sum(v == "読みたい" for v in truth.values()), sum(v == "読みたくない" for v in truth.values()))
    out += ["", f"当てずっぽうの目安（多いほうに全部寄せる）：{base}/{len(truth)}",
            "使える目安：読みたいの再現が 8 割以上で、判定の読みたいが全体の半分以下なら、判定役の読みたいだけをオーナーに見せて残りは畳める。"
            "届かないうちは、見せる順番（判定役の読みたいを先）にだけ使う。"]
    p = fdir() / f"score-pitch-{stem}.md"
    print(A.write(p, "\n".join(out)))
    with (fdir() / "choices-pitch.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        for rid, body, cell in rows:
            if rid in truth:
                f.write(json.dumps({"date": str(datetime.date.today()), "file": stem, "id": rid, "mark": truth[rid], "text": body}, ensure_ascii=False) + "\n")
    print("オーナーの印を choices-pitch.jsonl に足した（次の full の例になる）")


# ---- 場面の ○△× ----

SCENE_ASK = """あなたは、この連載のオーナー（作者）の判断を当てる係です。
下は新しい話の初稿です。場面（◇ で区切る）ごとに、オーナーが ○（このまま）／△（一言で直す）／×（差し替え）のどれを付けるかを当ててください。
○ は読んで面白く、この人物の今の距離で成り立っている場面。△ は骨は良いが一か所引っかかる場面。× は面白くない・前の話の繰り返し・人物の段階が戻っている場面。
文の細かい欠陥は見ません（行の点検は別）。場面として読みたいかで答えてください。

答えは次の形だけ（場面ごとに一行）。ツールは使わないでください。
場面1: ○｜理由を一言
場面2: △｜どこが引っかかるか一言
最後に「土台にできるか：できる／できない」と、一番弱い場面の番号を書いてください。
"""


def scenes_of(text):
    parts, cur = [], []
    for line in text.splitlines():
        if line.strip() == "◇":
            parts.append("\n".join(cur).strip())
            cur = []
        else:
            cur.append(line)
    parts.append("\n".join(cur).strip())
    return [p for p in parts if p]


def scene_label(s):
    for line in s.splitlines():
        t = line.strip()
        if t and not t.startswith("第"):
            return t[:28]
    return s[:28]


def scenes(ep, ver, conds, model, effort, force):
    text = A.episode_text(ep, ver)
    sc = scenes_of(text)
    marks = A.notes_dir(ep) / f"owner-marks-{ver}.md"
    if marks.is_file() and re.search(r"\|\s*場面\d+\s*\|\s*[○◯△×xX]", marks.read_text(encoding="utf-8")) and not force:
        sys.exit(f"{marks.relative_to(A.WORK)} にオーナーの印が付いている。印の前に回すのが試験（--force で参考）")
    if not marks.is_file():
        rows = "\n".join(f"| 場面{i} | {scene_label(s)} |  |  |" for i, s in enumerate(sc, 1))
        A.write(marks, f"# オーナーの印 {ep} {ver}\n\n場面ごとに ○／△／× と一言。行の指摘は書かない（行は磨きの回で）。土台にできるかも最後に一言。\n\n"
                       f"| 場面 | 書き出し | ○△× | 一言 |\n|---|---|---|---|\n{rows}\n\n土台にできるか：\n")
        print("オーナーの印の表を作った：", marks.relative_to(A.WORK))
    numbered = "\n\n".join(f"## 場面{i}\n\n{s}" for i, s in enumerate(sc, 1))
    jobs = []
    for cond in conds:
        ctx = (full_context("scenes") + A.SEP + A.section("この話の作者の決定（散文のあらすじ・メモ）", A.episode_plan(ep)) + A.SEP
               + A.section("直前の話（採用版）", A.prev_episode(ep)) + A.SEP) if cond == "full" else ""
        jobs.append((A.agents()[0], SCENE_ASK + A.SEP + ctx + "# 初稿\n\n" + numbered + "\n", cond))
    for cond, out, err in A.run_many(jobs, model, effort):
        if err:
            print(f"{cond}: {err}")
            continue
        pred = {k: v for k, v in re.findall(r"^場面(\d+)\s*[:：]\s*([○◯△×])", out or "", re.M)}
        tag = f"{cond}-{model_tag(model)}"
        p = fdir() / f"predict-scenes-{ep}-{ver}-{tag}.md"
        A.write(p, f"# 面白さの判定役の試験：場面 {ep} {ver}（{tag}）\n\n実行 {stamp()}　コミット {head()}　場面 {len(sc)}\n\n{out}")
        (fdir() / f"predict-scenes-{ep}-{ver}-{tag}.json").write_text(json.dumps(pred, ensure_ascii=False, indent=1), encoding="utf-8")
        print(p.relative_to(A.WORK), f"判定 {len(pred)}/{len(sc)} 場面")


def norm_mark(m):
    return {"◯": "○", "x": "×", "X": "×"}.get(m, m)


def score_scenes(ep, ver):
    marks = A.notes_dir(ep) / f"owner-marks-{ver}.md"
    if not marks.is_file():
        sys.exit(f"{marks.relative_to(A.WORK)} がない")
    truth = {k: norm_mark(v) for k, v in re.findall(r"\|\s*場面(\d+)\s*\|[^|]*\|\s*([○◯△×xX])", marks.read_text(encoding="utf-8"))}
    if not truth:
        sys.exit("オーナーの印がまだ付いていない")
    out = [f"# 当たり：場面 {ep} {ver}", "", f"オーナーの印 {len(truth)} 場面（{'・'.join(f'場面{k}={v}' for k, v in sorted(truth.items(), key=lambda x: int(x[0])))}）。採点 {stamp()}", "",
           "| 条件・モデル | 一致 | ×を×と言えた | ○を○と言えた | 外した場面 |", "|---|---|---|---|---|"]
    for pj in sorted(fdir().glob(f"predict-scenes-{ep}-{ver}-*.json")):
        pred = {k: norm_mark(v) for k, v in json.loads(pj.read_text(encoding="utf-8")).items()}
        tag = pj.stem.replace(f"predict-scenes-{ep}-{ver}-", "")
        both = [k for k in truth if k in pred]
        hit = [k for k in both if pred[k] == truth[k]]
        tx = [k for k in both if truth[k] == "×"]
        to = [k for k in both if truth[k] == "○"]
        miss = "・".join(f"場面{k}（オーナー {truth[k]}／判定 {pred[k]}）" for k in both if pred[k] != truth[k])
        out.append(f"| {tag} | {len(hit)}/{len(both)} | {sum(pred[k] == '×' for k in tx)}/{len(tx)} | {sum(pred[k] == '○' for k in to)}/{len(to)} | {miss or 'なし'} |")
    p = fdir() / f"score-scenes-{ep}-{ver}.md"
    print(A.write(p, "\n".join(out)))


# ---- 初稿二本 ----

DRAFT_ASK = """あなたは、この連載のオーナー（作者）の判断を当てる係です。
同じ話の初稿が二本（X と Y）あります。角度が違います。オーナーはどちらを土台にするかを選びます。
どちらをオーナーが土台にするかを当ててください。文の上手さの一般論ではなく、読みたくなるか・この人物の今の距離で成り立っているか・前の話の繰り返しがないかで答えてください。

答えは次の形だけ。ツールは使わないでください。
土台: X
理由: 一言
"""


def draft(ep, va, vb, conds, model, effort):
    ta, tb = A.episode_text(ep, va), A.episode_text(ep, vb)
    jobs = []
    for cond in conds:
        ctx = (full_context("draft") + A.SEP + A.section("この話の作者の決定（散文のあらすじ・メモ）", A.episode_plan(ep)) + A.SEP
               + A.section("直前の話（採用版）", A.prev_episode(ep)) + A.SEP) if cond == "full" else ""
        jobs.append((A.agents()[0], DRAFT_ASK + A.SEP + ctx + f"# X\n\n{ta}\n\n# Y\n\n{tb}\n", (cond, "ab")))
        jobs.append((A.agents()[0], DRAFT_ASK + A.SEP + ctx + f"# X\n\n{tb}\n\n# Y\n\n{ta}\n", (cond, "ba")))
    got = {}
    for (cond, order), out, err in A.run_many(jobs, model, effort):
        if err:
            print(f"{cond}/{order}: {err}")
            continue
        m = re.search(r"土台\s*[:：]\s*([XY])", out or "")
        pick = None
        if m:
            pick = (va if m.group(1) == "X" else vb) if order == "ab" else (vb if m.group(1) == "X" else va)
        got.setdefault(cond, {})[order] = (pick, out)
    tag = model_tag(model)
    for cond, d in got.items():
        picks = [d[o][0] for o in d]
        text = "\n\n".join(f"## 順 {o}（判定 {d[o][0]}）\n\n{d[o][1]}" for o in d)
        p = fdir() / f"predict-draft-{ep}-{va}-{vb}-{cond}-{tag}.md"
        A.write(p, f"# 面白さの判定役の試験：初稿二本 {ep} {va}／{vb}（{cond}-{tag}）\n\n実行 {stamp()}　コミット {head()}　判定 {picks}\n\n{text}")
        (fdir() / f"predict-draft-{ep}-{va}-{vb}-{cond}-{tag}.json").write_text(json.dumps(picks, ensure_ascii=False), encoding="utf-8")
        print(p.relative_to(A.WORK), "判定", picks)


def score_draft(ep, owner):
    out = [f"# 当たり：初稿二本 {ep}（オーナーの土台 {owner}）", "", "| 判定 | 両方の順 | 当たり |", "|---|---|---|"]
    for pj in sorted(fdir().glob(f"predict-draft-{ep}-*.json")):
        picks = json.loads(pj.read_text(encoding="utf-8"))
        out.append(f"| {pj.stem.replace(f'predict-draft-{ep}-', '')} | {picks} | {sum(p == owner for p in picks)}/{len(picks)} |")
    p = fdir() / f"score-draft-{ep}.md"
    print(A.write(p, "\n".join(out)))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("pitch"); p1.add_argument("file")
    p2 = sub.add_parser("scenes"); p2.add_argument("episode"); p2.add_argument("version")
    p3 = sub.add_parser("draft"); p3.add_argument("episode"); p3.add_argument("va"); p3.add_argument("vb")
    for p in (p1, p2, p3):
        p.add_argument("--cond", choices=("plain", "full", "both"), default="both")
        p.add_argument("--force", action="store_true")
        A.add_model_args(p)
    p4 = sub.add_parser("score"); p4.add_argument("what", choices=("pitch", "scenes", "draft")); p4.add_argument("args", nargs="*")
    p4.add_argument("--owner", help="draft：オーナーが土台にした版")
    a = ap.parse_args()
    if a.cmd == "score":
        if a.what == "pitch":
            score_pitch(a.args[0])
        elif a.what == "scenes":
            score_scenes(a.args[0], a.args[1])
        else:
            if not a.owner:
                sys.exit("--owner Vn が要る")
            score_draft(a.args[0], a.owner)
        return
    conds = ["plain", "full"] if a.cond == "both" else [a.cond]
    if a.cmd == "pitch":
        pitch(a.file, conds, a.model, a.effort, a.force)
    elif a.cmd == "scenes":
        scenes(a.episode, a.version, conds, a.model, a.effort, a.force)
    else:
        draft(a.episode, a.va, a.vb, conds, a.model, a.effort)


if __name__ == "__main__":
    main()
