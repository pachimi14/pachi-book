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

def tier_of(subj):
    """材料の格（2026-10-01 オーナー：「まあこっちか」で選んだものと、「この文にして」と書いたものが同じ扱いになっていた）。
    明示：オーナーが書いた・文を指定した／指示：オーナーの指摘を受けて書き手が書いた／選択：書き手の案から選んだ／混在：レビューなどとまとめた直し（材料から外す）"""
    if re.search(r"初見読者レビューとオーナー|執筆工程の改善|ほか）|、採用を保留", subj):
        return "混在"
    if re.search(r"owner:A|（案。未採用）", subj):
        return "選択"
    if re.search(r"オーナーの文面|オーナーの形|オーナー修正|オーナーの細部修正|owner:[CD]", subj):
        return "明示"
    return "指示"


def not_owner():
    """件名に「オーナー」「owner:」があっても、オーナー本人の指摘・選択でないコミット（GPT など AI の判断）。
    作品の <taste_dir>/not-owner-commits.txt に「短いハッシュ 理由」を一行ずつ書く（2026-10-02 オーナー：
    EP024 で GPT の判断をオーナーの選択として記録してしまった。件名は push 済みで直せないので、ここで外す）。"""
    p = tdir() / "not-owner-commits.txt"
    if not p.is_file():
        return set()
    return {l.split()[0][:7] for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


def from_git():
    out = []
    skip = not_owner()
    for line in git("log", "--format=%H%x09%an%x09%s").splitlines():
        h, author, subj = line.split("\t", 2)
        if "オーナー" not in subj and "owner:" not in subj:
            continue
        if h[:7] in skip:
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
                ctx = "\n".join(x for x in a[max(0, i1 - 12):i1] if x.strip())   # 前後を広めに（2026-10-01：前3行では筋の直しを外した）
                after = "\n".join(x for x in a[i2:i2 + 5] if x.strip())
                out.append({"src": "git", "tier": tier_of(subj), "id": f"{h[:7]}:{path}:{i1}", "ep": path.split("/")[1], "subject": subj[:80],
                            "context": ctx, "after": after, "worse": old, "better": new, "reason": ""})
    return out


def from_bad():
    out, title, pend = [], "", None
    for line in A.doc("bad_examples").splitlines():
        if line.startswith("## "):
            title, pend = line[3:].strip(), None
        elif line.startswith("- 元："):
            pend = {"src": "bad", "tier": "明示", "id": f"bad:{title}:{len(out)}", "ep": "", "context": "", "title": title,
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
                out.append({"src": "choice", "tier": "明示" if c["chosen_id"] == "owner" else ("選択" if c.get("weak", True) else "明示"),
                            "id": f"{c['chosen_id']}>{r['id']}", "ep": c["ep"], "context": c.get("context", ""),
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


def pairs(all_=False):
    p = tdir() / "pairs.jsonl"
    P = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.is_file() else build()
    return P if all_ else [x for x in P if x.get("tier") != "混在"]


# ---- 判定 ----

ASK = """あなたは、この連載のオーナー（作者）の好みを当てる係です。
下の各問には、本文の同じ箇所の二つの版（X と Y）があります。一つはオーナーが選ぶ版、もう一つは選ばない版です。
資料の「オーナーが選んだ例」で、オーナーがどういう直しをする人か（何を削り、何を足し、どんな一言を嫌うか）を見てから、
オーナーがどちらを選ぶかを答えてください。文の上手さの一般論ではなく、このオーナーの好みで答えてください。

答えは次の形だけ（一問一行）。ツールは使わないでください。
問1: X
問2: Y
"""


TIER_NOTE = {"明示": "オーナーが書いた", "指示": "オーナーの指摘で書き手が書いた", "選択": "書き手の案からオーナーが選んだ（弱い好み）"}


def examples_text(ex):
    return "\n".join(f"- 〔{TIER_NOTE.get(p.get('tier'), '')}〕選ばなかった：{p['worse'] or '（削った）'}\n  選んだ：{p['better'] or '（削った）'}"
                     + (f"\n  理由：{p['reason']}" if p["reason"] else "") for p in ex)


PROFILE = """下は、ある連載のオーナー（作者）が、書き手の文を直した・選んだ記録です（選ばなかった版 → 選んだ版、理由つきのものもある）。
このオーナーの好みを、次に別の文を見たときに「オーナーならどちらを選ぶか」を当てられるように、傾向として書き出してください。
- 一般論（読みやすく、など）ではなく、このオーナーに特有の向きを書く。何を削るか、何を足すか、どんな一言を嫌うか、どこで具体を求めるか、筋のどこにうるさいか。
- 傾向ごとに、記録の中の件数のめやすと、短い例（選ばなかった → 選んだ）を一つ。
- 迷ったときの決め方（例：迷ったら短いほう、など）があれば最後に書く。
- 15〜25項目。ツールは使わないでください。
"""


def profile_text():
    p = tdir() / "profile.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def make_profile(ex=None):
    ex = ex if ex is not None else pairs()
    text, err = A.run(A.agents()[0], PROFILE + A.SEP + examples_text(ex), None, "xhigh")
    if err:
        sys.exit(err)
    return text


def context_block(ex, profile=None):
    prof = profile if profile is not None else profile_text()
    return (A.section("良い例（読者とオーナーが面白いと言った場面）", A.doc("good_examples")) + A.SEP
            + (A.section("オーナーの好みの傾向（記録から書き出したもの）", prof) + A.SEP if prof else "")
            + A.section("オーナーが選んだ例（選ばなかった版 → 選んだ版）", examples_text(ex)))


def items_text(items):
    out = []
    for i, it in enumerate(items, 1):
        ctx, x, y = it[:3]
        after = it[3] if len(it) > 3 else ""
        c = f"（直前の文）\n{ctx}\n" if ctx else ""
        d = f"（直後の文）\n{after}\n" if after else ""
        out.append(f"## 問{i}\n{c}X：\n{x or '（この箇所の文を削った版）'}\nY：\n{y or '（この箇所の文を削った版）'}\n{d}")
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
    P = pairs(all_=True)
    rnd = random.Random(seed)
    pool = [p for p in P if p.get("tier") == "明示"]   # 測るのは「オーナーが書いた」組だけ
    hold = rnd.sample(pool, min(n, len(pool)))
    hc = {h["id"].split(":")[0] for h in hold}
    ex = [p for p in P if p not in hold and not (strict and p["id"].split(":")[0] in hc)
          and not any(overlap(p["worse"] + p["better"], h["worse"]) or overlap(p["worse"] + p["better"], h["better"]) for h in hold)]
    ex_t = [p for p in ex if p.get("tier") != "混在"]
    jobs, keys = [], {}
    for cond in ("base", "taste", "tiered"):
        for b in range(0, len(hold), batch):
            chunk = hold[b:b + batch]
            for flip in (False, True):
                items, key = [], []
                for i, p in enumerate(chunk):
                    first_better = flip ^ (i % 2 == 1)
                    af = p.get("after", "")
                    items.append((p["context"], p["better"], p["worse"], af) if first_better else (p["context"], p["worse"], p["better"], af))
                    key.append("X" if first_better else "Y")
                ctx = (A.section("良い例", A.doc("good_examples")) if cond == "base"
                       else context_block([dict(p, tier=None) for p in ex], "") if cond == "taste" else context_block(ex_t, ""))
                prompt = ASK + A.SEP + ctx + A.SEP + "# 問題\n\n" + items_text(items)
                jobs.append((A.agents()[0], prompt, (cond, b, flip)))
                keys[(cond, b, flip)] = (key, [p["id"] for p in chunk])
    res, both = {"base": [0, 0], "taste": [0, 0], "tiered": [0, 0]}, {}
    rows = []
    for tag, text, err in A.run_many(jobs):
        got = dict(re.findall(r"問(\d+)\s*[:：]\s*([XY])", text or ""))
        key, ids = keys[tag]
        for i, k in enumerate(key, 1):
            ok = got.get(str(i)) == k
            res[tag[0]][0] += ok
            res[tag[0]][1] += 1
            both.setdefault((tag[0], ids[i - 1]), []).append(ok)
            rows.append({"cond": tag[0], "id": ids[i - 1], "ok": ok})
        if err:
            print(tag, err)
    stable = {c: sum(1 for (cc, _), v in both.items() if cc == c and all(v)) for c in res}
    consistent = {c: sum(1 for (cc, _), v in both.items() if cc == c and (all(v) or not any(v))) for c in res}
    day = f"{datetime.date.today()}-s{seed}" + ("-strict" if strict else "")
    lines = [f"# 好みの判定役の測定（{day}）", "",
             f"伏せた組 {len(hold)}（オーナーが書いた組＝明示から）、渡した例 {len(ex)}（伏せた組と重なる例{'・同じコミットの例' if strict else ''}は外した）、順番2通り。", "",
             "| 条件 | 当たり（判定の数） | 両方の順で当てた組 | 両方の順で答えがそろった組だけの当たり（そろわない組は「判定できず」） |", "|---|---|---|---|"]
    for c, (ok, m) in res.items():
        cs = consistent[c]
        lines.append(f"| {c}（{ {'base': '良い例だけ', 'taste': '良い例＋例（格なし・混在も含む）', 'tiered': '良い例＋例（格つき・混在を外す）'}[c] }） | {ok}/{m}（{ok / max(m, 1):.0%}） | {stable[c]}/{len(hold)} | {stable[c]}/{cs}（{stable[c] / max(cs, 1):.0%}）・答えた組 {cs}/{len(hold)} |")
    hmap = {h["id"]: h for h in hold}
    miss = {}
    for r in rows:
        if r["cond"] == "tiered" and not r["ok"]:
            miss[r["id"]] = miss.get(r["id"], 0) + 1
    (tdir() / f"eval-{day}-miss.json").write_text(json.dumps([dict(hmap[k], miss=v) for k, v in miss.items()], ensure_ascii=False, indent=1), encoding="utf-8")
    out = tdir() / f"eval-{day}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("build", "eval", "profile", "compare", "record"))
    ap.add_argument("files", nargs="*", help="compare：比べる版のファイル（2〜4）／record：選ばれた版、選ばれなかった版…の順")
    ap.add_argument("--issue", default="", help="record：何を選んだか（例 EP023 温度の一場面）")
    ap.add_argument("--ep", default="", help="record：話")
    ap.add_argument("--strong", action="store_true", help="record：オーナーがはっきり選んだ")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        from collections import Counter
        P = build()
        print(len(P), dict(Counter(p["src"] for p in P)))
    elif a.cmd == "compare":
        # 温度確認の一場面など、角度の違う版を比べる（2026-10-01）。参考。オーナーに見せるときに添える
        if not 2 <= len(a.files) <= 4:
            sys.exit("比べる版は2〜4個")
        cands = {Path(f).stem: Path(f).read_text(encoding="utf-8").strip() for f in a.files}
        wins, stable, err = judge("", cands)
        print("好みの判定（参考。taste.py。総当たりを両方の順で聞いた勝ち数。当たりは測定で75%前後）")
        for k, v in sorted(wins.items(), key=lambda x: -x[1]):
            print(f"  {k}：{v:g}勝")
        print(f"  両方の順で答えがそろった組：{stable:.0%}" + (f"　失敗：{err}" if err else ""))
    elif a.cmd == "record":
        # オーナーが版を選んだ記録（温度の一場面など、propose.py を通さない選択）
        if len(a.files) < 2:
            sys.exit("選ばれた版、選ばれなかった版…の順に2つ以上")
        texts = [Path(f).read_text(encoding="utf-8").strip() for f in a.files]
        rec = {"date": str(datetime.date.today()), "ep": a.ep, "issue": a.issue, "weak": not a.strong, "context": "",
               "chosen_id": Path(a.files[0]).stem, "chosen_text": texts[0],
               "rejected": [{"id": Path(f).stem, "text": x} for f, x in zip(a.files[1:], texts[1:])]}
        with (tdir() / "choices.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(len(build()), "組（記録した）")
    elif a.cmd == "profile":
        out = tdir() / "profile.md"
        out.write_text(f"# オーナーの好みの傾向（taste.py profile。{datetime.date.today()}。記録 {len(pairs())} 組から）\n\n" + make_profile(), encoding="utf-8")
        print(out.relative_to(A.WORK))
    else:
        evaluate(a.n, a.seed, a.strict)


if __name__ == "__main__":
    main()
