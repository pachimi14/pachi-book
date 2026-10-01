#!/usr/bin/env python3
"""オーナーの好みの判定役（2026-10-01）。

LLM に「面白いか」を聞いても、オーナーの版を選べなかった（10回中5回）。外れ方は、オーナーが削る「ファンらしい一言」を
LLM が好む、という向きにそろっていた。足りないのは一般論の面白さではなく、このオーナーの好み。
そこで、オーナーが選んだ・直した組（選ばなかった版 → 選んだ版）を例として渡し、案の比べ役にする。

材料（作品リポジトリの <taste_dir>、既定 research/taste/）:
  pairs.jsonl   build で作る。1行1組。better がオーナーの選んだ側。
    - git の履歴：件名に「オーナー」「owner:」を含むコミットで、版の本文を書き換えた所（その場の書き換えと、一つ前の版との差）
    - blocks/BAD-EXAMPLES.md の「元」「直」
    - choices.jsonl：propose.py で二〜四択を出し、オーナーが選んだ記録（--apply のときに足される）
使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/taste.py build                 # 組を作り直す
  python ../pachi-book/scripts/taste.py eval --n 40 --strict  # 伏せた組で当たりを測る（結果は <taste_dir>/eval-*.md）
  propose.py が案が二つ以上のときに judge() を呼び、「好みの判定（参考）」を出す。

測定（2026-10-01、kyuketsu）：伏せた組40×順番2通り。例なし 55〜60% → 例あり 75〜79%（同じコミットの例も外した厳しい条件で75%）。
両方の順で同じ答えになった組は 25〜29/40。決め手には足りない（目安 80%）ので、オーナーに見せる案の並べ方の参考にとどめる。
オーナーの選択がたまるほど例が増える。ときどき eval で測り直す。
"""
import argparse
import datetime
import difflib
import json
import random
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

EP = re.compile(r"^episodes/EP\d{3}/V\d+\.md$")


def tdir():
    d = A.WORK / (A.config().get("taste_dir") or "research/taste")
    d.mkdir(parents=True, exist_ok=True)
    return d


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, encoding="utf-8", cwd=A.WORK).stdout


# ---- 材料を集める ----

def from_git():
    out = []
    for line in git("log", "--format=%H%x09%an%x09%s").splitlines():
        h, author, subj = line.split("\t", 2)
        if "オーナー" not in subj and "owner:" not in subj:
            continue
        for st in git("diff-tree", "--no-commit-id", "-r", "--name-status", h).splitlines():
            parts = st.split("\t")
            if parts[0] not in ("M", "A") or not EP.match(parts[1]):
                continue
            path = src = parts[1]
            if parts[0] == "A":
                m = re.match(r"(episodes/EP\d{3}/V)(\d+)\.md", path)
                src = f"{m.group(1)}{int(m.group(2)) - 1}.md"
            a = git("show", f"{h}^:{src}").splitlines()
            b = git("show", f"{h}:{path}").splitlines()
            if not a:
                continue
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
                if tag == "equal":
                    continue
                old = "\n".join(x for x in a[i1:i2] if x.strip())
                new = "\n".join(x for x in b[j1:j2] if x.strip())
                if not old.strip() or old.strip() == new.strip() or len(old) > 600 or len(new) > 600:
                    continue
                if re.match(r"第\d+話", old) or re.match(r"第\d+話", new):
                    continue  # 題名の行は除く（一律のきまりで変えて戻した記録が混ざるため）
                if re.sub(r"[、。\s]", "", old) == re.sub(r"[、。\s]", "", new):
                    continue  # 読点・空白だけの直しは除く
                ctx = "\n".join(x for x in a[max(0, i1 - 3):i1] if x.strip())
                out.append({"src": "git", "id": f"{h[:7]}:{path}:{i1}", "ep": path.split("/")[1], "subject": subj[:80],
                            "context": ctx, "worse": old, "better": new, "reason": ""})
    return out


def from_bad():
    out, title, pend = [], "", None
    for line in A.doc("bad_examples").splitlines():
        if line.startswith("## "):
            title, pend = line[3:].strip(), None
        elif line.startswith("- 元："):
            pend = {"src": "bad", "id": f"bad:{title}:{len(out)}", "ep": "", "context": "", "title": title,
                    "worse": line[4:].strip(), "better": None, "reason": ""}
        elif line.startswith("- 直：") and pend:
            pend["better"] = "" if line[4:].strip().startswith("削除") else line[4:].strip()
            out.append(pend)
            pend = None
        elif line.startswith("- 理由："):
            for p in out:
                if p.get("title") == title and not p["reason"]:
                    p["reason"] = line[5:].strip()
    return out


def from_choices():
    p = tdir() / "choices.jsonl"
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            for r in c["rejected"]:
                out.append({"src": "choice", "id": f"{c['chosen_id']}>{r['id']}", "ep": c["ep"], "context": c.get("context", ""),
                            "worse": r["text"], "better": c["chosen_text"], "reason": c.get("issue", "")})
    return out


def build():
    seen, uniq = set(), []
    for p in from_git() + from_bad() + from_choices():
        k = (p["worse"], p["better"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    with (tdir() / "pairs.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for p in uniq:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return uniq


def pairs():
    p = tdir() / "pairs.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.is_file() else build()


# ---- 判定 ----

ASK = """あなたは、この連載のオーナー（作者）の好みを当てる係です。
下の各問には、本文の同じ箇所の二つの版（X と Y）があります。一つはオーナーが選ぶ版、もう一つは選ばない版です。
資料の「オーナーが選んだ例」で、オーナーがどういう直しをする人か（何を削り、何を足し、どんな一言を嫌うか）を見てから、
オーナーがどちらを選ぶかを答えてください。文の上手さの一般論ではなく、このオーナーの好みで答えてください。

答えは次の形だけ（一問一行）。ツールは使わないでください。
問1: X
問2: Y
"""


def examples_text(ex):
    return "\n".join(f"- 選ばなかった：{p['worse'] or '（削った）'}\n  選んだ：{p['better'] or '（削った）'}"
                     + (f"\n  理由：{p['reason']}" if p["reason"] else "") for p in ex)


def context_block(ex):
    return (A.section("良い例（読者とオーナーが面白いと言った場面）", A.doc("good_examples")) + A.SEP
            + A.section("オーナーが選んだ例（選ばなかった版 → 選んだ版）", examples_text(ex)))


def items_text(items):
    out = []
    for i, (ctx, x, y) in enumerate(items, 1):
        c = f"（直前の文）\n{ctx}\n" if ctx else ""
        out.append(f"## 問{i}\n{c}X：\n{x or '（この箇所の文を削った版）'}\nY：\n{y or '（この箇所の文を削った版）'}")
    return "\n\n".join(out)


def ask(items, ex, model=None, effort=None):
    """items: [(ctx, x, y)] → ['X'/'Y'/None]"""
    prompt = ASK + A.SEP + context_block(ex) + A.SEP + "# 問題\n\n" + items_text(items)
    text, err = A.run(A.agents()[0], prompt, model, effort)
    got = dict(re.findall(r"問(\d+)\s*[:：]\s*([XY])", text or ""))
    return [got.get(str(i)) for i in range(1, len(items) + 1)], err


def judge(context, cands):
    """cands: {key: text}（同じ箇所の案。2〜4個）。総当たりで、両方の順に聞く。
    返す：{key: 勝ち数}, 両方の順で答えがそろった組の割合"""
    keys = list(cands)
    pairs_ = [(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]]
    items = [(context, cands[a], cands[b]) for a, b in pairs_] + [(context, cands[b], cands[a]) for a, b in pairs_]
    got, err = ask(items, pairs())
    wins = {k: 0.0 for k in keys}
    stable = 0
    n = len(pairs_)
    for i, (a, b) in enumerate(pairs_):
        g1, g2 = got[i], got[i + n]
        w1 = a if g1 == "X" else b if g1 == "Y" else None
        w2 = b if g2 == "X" else a if g2 == "Y" else None
        for w in (w1, w2):
            if w:
                wins[w] += 0.5
        stable += int(w1 is not None and w1 == w2)
    return wins, (stable / n if n else 0), err


# ---- 測定 ----

def overlap(a, b):
    a, b = re.sub(r"\s", "", a), re.sub(r"\s", "", b)
    if len(a) < 12:
        return bool(a) and a in b
    return any(a[i:i + 12] in b for i in range(0, len(a) - 12, 6))


def evaluate(n, seed, strict, batch=10):
    P = pairs()
    rnd = random.Random(seed)
    pool = [p for p in P if p["src"] in ("git", "choice")]
    hold = rnd.sample(pool, min(n, len(pool)))
    hc = {h["id"].split(":")[0] for h in hold}
    ex = [p for p in P if p not in hold and not (strict and p["id"].split(":")[0] in hc)
          and not any(overlap(p["worse"] + p["better"], h["worse"]) or overlap(p["worse"] + p["better"], h["better"]) for h in hold)]
    jobs, keys = [], {}
    for cond in ("base", "taste"):
        for b in range(0, len(hold), batch):
            chunk = hold[b:b + batch]
            for flip in (False, True):
                items, key = [], []
                for i, p in enumerate(chunk):
                    first_better = flip ^ (i % 2 == 1)
                    items.append((p["context"], p["better"], p["worse"]) if first_better else (p["context"], p["worse"], p["better"]))
                    key.append("X" if first_better else "Y")
                ctx = (A.section("良い例", A.doc("good_examples")) if cond == "base" else context_block(ex))
                prompt = ASK + A.SEP + ctx + A.SEP + "# 問題\n\n" + items_text(items)
                jobs.append((A.agents()[0], prompt, (cond, b, flip)))
                keys[(cond, b, flip)] = (key, [p["id"] for p in chunk])
    res, both = {"base": [0, 0], "taste": [0, 0]}, {}
    for tag, text, err in A.run_many(jobs):
        got = dict(re.findall(r"問(\d+)\s*[:：]\s*([XY])", text or ""))
        key, ids = keys[tag]
        for i, k in enumerate(key, 1):
            ok = got.get(str(i)) == k
            res[tag[0]][0] += ok
            res[tag[0]][1] += 1
            both.setdefault((tag[0], ids[i - 1]), []).append(ok)
        if err:
            print(tag, err)
    stable = {c: sum(1 for (cc, _), v in both.items() if cc == c and all(v)) for c in res}
    day = f"{datetime.date.today()}-s{seed}" + ("-strict" if strict else "")
    lines = [f"# 好みの判定役の測定（{day}）", "",
             f"伏せた組 {len(hold)}（git の履歴・選択の記録から）、渡した例 {len(ex)}（伏せた組と重なる例{'・同じコミットの例' if strict else ''}は外した）、順番2通り。", "",
             "| 条件 | 当たり（判定の数） | 両方の順で当てた組 |", "|---|---|---|"]
    for c, (ok, m) in res.items():
        lines.append(f"| {c}（{'良い例だけ' if c == 'base' else '良い例＋オーナーが選んだ例'}） | {ok}/{m}（{ok / max(m, 1):.0%}） | {stable[c]}/{len(hold)} |")
    out = tdir() / f"eval-{day}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("build", "eval"))
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        from collections import Counter
        P = build()
        print(len(P), dict(Counter(p["src"] for p in P)))
    else:
        evaluate(a.n, a.seed, a.strict)


if __name__ == "__main__":
    main()
