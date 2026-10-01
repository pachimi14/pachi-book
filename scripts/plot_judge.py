#!/usr/bin/env python3
"""展開の判定役（2026-10-01）。章のあらすじを読んで、どの話の展開が弱いかを出す。

オーナーが章のあらすじ（chapters/CH-xx-STORY.md）を全部読むのは重い。判定役が「弱い」とした話と要約だけを読めば
足りるようにしたい。ただし LLM に「面白いか」を聞いても、一文の好みではオーナーの版を選べなかった（taste.py の経緯）。
そこで、答えの分かっている問題を作って当たりを測り、上げてから使う（計画は作品の research/plot-judge/PLAN.md）。

問題は二種類（どちらも答えが作り方から決まる）：
  1. 壊した版（make）：採用済みの話の本文から、章のあらすじと同じ形の要約を作り（base）、続く数話のうち一話だけを
     伸びなかった作品の型・オーナーが直してきた型で弱くした版を作る。両方を同じ書き方に書き直して（文の癖で見分けさせない）並べる。
  2. オーナーが直した展開（harvest）：メモ・計画・台帳に残る「旧案 → オーナーの決定」を拾い、どちらをオーナーが選んだかを当てる。
     拾ったものは書き手が目で確かめてから使う（owner.jsonl の ok を true に）。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/plot_judge.py base                    # 採用済みの話の要約（<dir>/base/EPxxx.md）
  python ../pachi-book/scripts/plot_judge.py make --n 44             # 壊した版の問題（<dir>/problems.jsonl）
  python ../pachi-book/scripts/plot_judge.py harvest                 # オーナーが直した展開の候補（<dir>/owner-raw.jsonl → 確かめて owner.jsonl）
  python ../pachi-book/scripts/plot_judge.py eval --set broken|owner # 当たりを測る（<dir>/eval-*.md）
  python ../pachi-book/scripts/plot_judge.py judge chapters/CH-02-STORY.md   # 章のあらすじの判定（chapters/notes/plot-judge-*.md）
置き場は pachi.json の plot_judge_dir（既定 research/plot-judge）。
"""
import argparse
import datetime
import json
import random
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

WORKERS = 8
AGENT = "claude"   # --agent codex で切り替える（Codex はローカルだけ。作る係と判定する係を別のモデルにしてよい）


def pdir():
    d = A.WORK / (A.config().get("plot_judge_dir") or "research/plot-judge")
    d.mkdir(parents=True, exist_ok=True)
    return d


def jl_read(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.is_file() else []


def jl_write(p, rows):
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def many(jobs, effort=None):
    out = A.run_many(jobs, None, effort, workers=WORKERS)
    for tag, _, err in out:
        if err:
            print("失敗", tag, err, flush=True)
    return out


# ---- 弱くする型（壊し方）。伸びなかった作品の型と、オーナーが直してきた型（PLAN.md） ----

KINDS = {
    "prep": ("準備の回を足して山場を遠くする",
             "窓の中のどこか一話を、作戦会議・移動・段取りの確認など準備だけの回にし、山場や出来事を一話うしろへずらす（話数は変えない。最後の話の出来事は次の窓へ押し出してよい）。"),
    "reward": ("その話の報酬を抜く",
               "一話から、読者が受け取るもの（笑い・報われ・誰かが気づく・評価が変わる・手に入れる・気になる新事実）を抜き、出来事が起きるだけの回にする。"),
    "strength": ("主人公の強さが見える場面を消す",
                 "主人公が自分の力・知識で場を決める場面を、ほかの人物が決める・偶然で片づく・主人公は見ているだけ、に変える。"),
    "closed": ("反応を身内だけに閉じる",
               "世間・ファン・ニュース・掲示板・協会など外の反応が広がる場面を、身内の数人の会話だけで受ける形にする。"),
    "hook_gag": ("引きを笑いだけで閉じる",
                 "一話の引きを、新しい情報・決断・異変ではなく、オチの一言（笑い）だけで閉じる形にする。"),
    "spoil": ("次の話の札を先に切る",
              "あとの話で明かす事実・正体・敵の台詞・決め手を、前の話で先に出してしまう（あとの話は、知っている前提で進む）。"),
    "skip_stage": ("気持ちの段階を飛ばす",
                   "関係や気持ちの変化の途中の段を抜く（まだ推しになっていないのに推しと言う、まだ打ち明けていないのに信頼しきっている、など）。"),
    "repeat": ("同じ型の場面を続ける",
               "隣り合う話で、同じ型の場面（明かす・言い返せない・助けに入る・叱られる、など）を続けて置く。"),
    "crowd": ("人物を増やす",
              "一話に、筋に要らない人物（新しい名前つきの人、既出の人物の顔出し）を何人も足し、登場人物をおよそ倍にする。"),
    "motive": ("理由のない行動",
               "ある人物の行動を、理由の書かれていない行動か、嫉妬・見張り・意地悪に読める行動に変える。"),
    "detail": ("体験していない現場の細部を足す",
               "行事の段取り・係の動き・業界の言葉・手順など、作者が体験していない現場の細部を、筋の中心に据えて足す。"),
}


# ---- 1. 要約（base） ----

BASE = """下は、連載中の小説の一話の本文と、それより前のあらすじです。この話を、章のあらすじ（作者が本文の前に書く設計）の一話分の形に要約してください。

形（これだけを出す。前置き・評価・作者向けの説明は書かない。ツールは使わない）：
### 第{n}話
（本文。350〜450字。誰がどこで何をして、誰が何を知るか。見せ場の台詞を「」で一〜二つ。メッセージの文面があれば【】で。出来事の順に。）
- 引き：（最後の一行が何か。台詞なら「」で）

読者に見えていること（本文に出たこと）だけを書く。作者用の設定・伏線の答えは書かない。"""


def base_cmd(eps):
    out = pdir() / "base"
    out.mkdir(exist_ok=True)
    cur = A.WORK / "episodes" / "current"
    files = sorted(cur.glob("EP*.md"))
    if eps:
        files = [f for f in files if f.stem in eps]
    jobs = []
    for f in files:
        n = int(f.stem[2:])
        prompt = (BASE.replace("{n}", str(n)) + A.SEP + A.section("これより前のあらすじ", A.synopsis_before(n))
                  + A.SEP + A.section(f"第{n}話の本文", f.read_text(encoding="utf-8")))
        jobs.append((AGENT, prompt, f.stem))
    for tag, text, err in many(jobs, "medium"):
        if text:
            A.write(out / f"{tag}.md", text)
            print("要約", tag, flush=True)


def base_eps():
    d = pdir() / "base"
    return {int(f.stem[2:]): f.read_text(encoding="utf-8").strip() for f in sorted(d.glob("EP*.md"))}


# ---- 2. 壊した版（make） ----

BREAK = """あなたは、連載小説の展開の判定役を測るための問題を作る係です。
下の「元の展開」は、作者が採用した数話分のあらすじです。このうち一話だけを、次の型で弱くした版を作ってください。

弱くする型：{label}
やり方：{how}

決まり：
- 弱くするのは一話だけ（{target}が向いていればそこ。向いていなければ、窓の中で一番自然に当てはまる話を選ぶ）。ほかの話は、つじつまを合わせるのに要る所だけ直す。
- 話数と、各話の「### 第N話」の見出しは変えない。
- 文の上手さは元と同じに保つ。わざと下手な文・不自然な言い回しにしない。AI の書き手が本当に出しそうな、もっともらしい案にする（展開として弱いだけで、読めば普通に通る）。
- 型の名前や「弱くした」ことが分かる言葉を本文に書かない。

次の形だけで答える。ツールは使わない。
## 弱くした話
第N話
## したこと
（一行。何をどう変えたか）
## 版
（全話。元と同じ形で）"""

NORM = """下は、連載小説の数話分のあらすじです。これを、決まった書き方にそろえて書き直してください（別の版と並べて読み比べるため、文の癖をそろえる）。

決まり：
- 出来事・登場人物・誰が何を知るか・台詞（「」）・メッセージ（【】）・引きは、一つも足さず、一つも削らず、順番も変えない。内容は直さない（弱いと思う所があっても、そのまま）。
- 各話「### 第N話」の見出しのあとに本文を一段落（300〜400字。「です・ます」は使わず、現在形で淡々と）、最後に「- 引き：…」の一行。
- 題名・前置き・評価は書かない。ツールは使わない。"""


def split_eps(text):
    parts = re.split(r"^###\s*第(\d+)話.*$", text, flags=re.M)
    return {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def join_eps(d):
    return "\n\n".join(f"### 第{n}話\n{d[n]}" for n in sorted(d))


def make(n, seed, width):
    base = base_eps()
    nums = sorted(base)
    starts = [s for s in nums if all(s + i in base for i in range(width))]
    rnd = random.Random(seed)
    keys = list(KINDS)
    combos = [(s, k) for s in starts for k in keys]
    rnd.shuffle(combos)
    # 型ごとに均等に
    pick, cnt = [], {k: 0 for k in keys}
    per = -(-n // len(keys))
    for s, k in combos:
        if cnt[k] < per and len(pick) < n:
            pick.append((s, k))
            cnt[k] += 1
    jobs = []
    for s, k in pick:
        window = {i: base[i] for i in range(s, s + width)}
        target = f"第{s + rnd.randrange(1, width)}話"
        label, how = KINDS[k]
        prompt = (BREAK.replace("{label}", label).replace("{how}", how).replace("{target}", target)
                  + A.SEP + A.section("これより前のあらすじ", A.synopsis_before(s))
                  + A.SEP + A.section("元の展開", join_eps(window)))
        jobs.append((AGENT, prompt, (s, k)))
    broken = []
    for (s, k), text, err in many(jobs):
        if not text:
            continue
        m = re.search(r"##\s*弱くした話\s*\n\s*第(\d+)話", text)
        what = re.search(r"##\s*したこと\s*\n(.+)", text)
        body = text.split("## 版", 1)[-1]
        eps = split_eps(body)
        if not m or set(eps) != set(range(s, s + width)):
            print("形が合わない", s, k, flush=True)
            continue
        broken.append({"start": s, "kind": k, "ep": int(m.group(1)), "what": what.group(1).strip() if what else "",
                       "orig_raw": join_eps({i: base[i] for i in range(s, s + width)}), "broken_raw": join_eps(eps)})
    # 両方を同じ書き方に
    jobs = []
    for i, b in enumerate(broken):
        for side in ("orig", "broken"):
            jobs.append((AGENT, NORM + A.SEP + b[f"{side}_raw"], (i, side)))
    for (i, side), text, err in many(jobs, "medium"):
        if text and set(split_eps(text)) == set(split_eps(broken[i]["orig_raw"])):
            broken[i][side] = text.strip()
    rows = []
    for i, b in enumerate(broken):
        if b.get("orig") and b.get("broken"):
            rows.append(dict(b, id=f"b{seed}-{i:02d}-{b['kind']}-EP{b['ep']:03d}"))
    p = pdir() / "problems.jsonl"
    old = [r for r in jl_read(p) if r["id"] not in {x["id"] for x in rows}]
    jl_write(p, old + rows)
    print(f"{len(rows)} 問（{p.relative_to(A.WORK)}、全 {len(old) + len(rows)} 問）")


# ---- 3. オーナーが直した展開（harvest） ----

HARVEST = """下は、連載小説の作者（オーナー）と書き手が残した資料（メモ・計画・台帳・変更の差分）です。
この中から、「展開」についてオーナーが案を決め直した記録を拾ってください。展開とは、出来事・場面の配置や有無・人物の動きや配置・誰が何を知るか・引き・話の分け方・章の行き先など、筋の決めのこと。
一文の言い回し・台詞の語尾・字数・数字の表記だけの直しは拾わない。

拾う条件：直す前の案が資料の中にはっきり残っていること（「旧：」「前の案〈…〉から変更」「取り消し」「〜はやめる」「外した」「差分の - の行」など）。直す前の案を想像で作らない。
オーナーの決定でないもの（書き手や監査の直し）は拾わない。オーナーが決めたかどうか分からないものも拾わない。

一件ごとに、次の JSON を一行で出す（JSON の行だけを出す。前置き・コードブロックは書かない。ツールは使わない）：
{"where": "第N話・場面など", "context": "前提（その時点の状況。2〜3文。どちらの案にも共通すること）", "before": "直す前の展開（2〜4文）", "after": "オーナーが決めた展開（2〜4文）", "reason": "資料に残っている理由（なければ空）", "quote": "根拠にした資料の文（短く抜き出す）"}

before と after は、同じくらいの長さ・細かさ・書き方で書く（どちらが新しい案か、書き方で分からないように）。「（オーナー）」「旧」「改」などの印は書かない。"""


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, encoding="utf-8", cwd=A.WORK).stdout


def harvest_sources():
    cfg = A.config()
    srcs = cfg.get("plot_judge_sources") or []
    groups = [[s] if isinstance(s, str) else s for s in srcs]
    out = []
    for g in groups:
        body = A.SEP.join(A.section(f, A.read(f)) for f in g if A.read(f))
        if body:
            out.append((" + ".join(g), body))
    # オーナーの判断で直したコミットのうち、メモ・計画・章のあらすじの差分
    for line in git("log", "--format=%H%x09%s").splitlines():
        h, subj = line.split("\t", 1)
        if "オーナー" not in subj and "owner:" not in subj:
            continue
        diff = git("show", "--format=", h, "--", "blocks/", "chapters/")
        if diff.strip():
            out.append((f"git {h[:7]}", f"# コミット {h[:7]}：{subj}\n\n{diff[:60000]}"))
    return out


def harvest():
    jobs = [(AGENT, HARVEST + A.SEP + body, name) for name, body in harvest_sources()]
    rows = []
    for name, text, err in many(jobs):
        for line in (text or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("before") and r.get("after"):
                rows.append(dict(r, src=name))
    for i, r in enumerate(rows):
        r["id"] = f"o{i:03d}"
        r["ok"] = None
    p = pdir() / "owner-raw.jsonl"
    jl_write(p, rows)
    print(f"{len(rows)} 件（{p.relative_to(A.WORK)}）。重なり・オーナーの決定でないものを外し、ok を true にして owner.jsonl へ")


OWNER_NORM = """下は、連載小説の同じ場面についての展開の二つの案（P と Q）です。二つを、同じ書き方・同じくらいの長さ（それぞれ2〜4文、100〜180字）に書き直してください。
読み比べるときに、書き方の差（細かさ・言い切り・理由の添え方）でどちらかが選ばれないようにするためです。
- 中身（出来事・誰が何をするか・台詞）は足さず、削らず、変えない。どちらが良いかの評価や理由は書かない。
- 次の形だけで答える。ツールは使わない。
P：…
Q：…"""


def owner_norm():
    """オーナーが直した展開の二案を、どちらがどちらか伏せたまま同じ書き方にそろえる（拾った係はどちらが新しい案か知っているため）。"""
    p = pdir() / "owner.jsonl"
    rows = jl_read(p)
    rnd = random.Random(1)
    jobs = []
    for i, r in enumerate(rows):
        if r.get("ok") and not r.get("before_n"):
            sw = rnd.random() < 0.5
            a, b = (r["after"], r["before"]) if sw else (r["before"], r["after"])
            jobs.append((AGENT, OWNER_NORM + A.SEP + f"前提：{r['context']}\nP：{a}\nQ：{b}", (i, sw)))
    for (i, sw), text, err in many(jobs, "medium"):
        m = re.search(r"P\s*[:：]\s*(.+?)\n+\s*Q\s*[:：]\s*(.+)", text or "", re.S)
        if m:
            pn, qn = m.group(1).strip(), m.group(2).strip()
            rows[i]["after_n"], rows[i]["before_n"] = (pn, qn) if sw else (qn, pn)
    jl_write(p, rows)
    print(sum(1 for r in rows if r.get("before_n")), "件をそろえた")


def owner_rows():
    rows = [r for r in jl_read(pdir() / "owner.jsonl") if r.get("ok")]
    return [dict(r, before=r.get("before_n") or r["before"], after=r.get("after_n") or r["after"]) for r in rows]


# ---- 判定の材料 ----

def work_context(full):
    cfg = A.config()
    parts = [A.section("作品の核", A.read("concept.md"))]
    if full:
        parts += [A.section("オーナーの好み", A.read("preferences.md")),
                  A.section("良い例（読者とオーナーが面白いと言った場面）", A.doc("good_examples")),
                  A.section("市場の調べ（伸びた作品・伸びなかった作品の型。題名・目次からの推測）",
                            "\n\n".join(A.read(m) for m in cfg.get("plot_judge_market") or cfg.get("market") or []))]
    return A.SEP.join(parts)


def owner_examples(rows):
    return "\n".join(f"- {r['where']}：{r['context']}\n  選ばなかった：{r['before']}\n  選んだ：{r['after']}"
                     + (f"\n  理由：{r['reason']}" if r.get("reason") else "") for r in rows)


RUBRIC = "\n".join(f"- {k}：{v[0]}" for k, v in KINDS.items())

PAIR = """あなたは、この連載の担当編集です。下の各問には、同じ連載の同じ数話について、展開の二つの案（X と Y）があります。
一つは作者が採った展開、もう一つは一話だけ展開を弱くした案です。文の上手さではなく、展開（出来事・配置・誰が何を知るか・引き・報酬）で比べてください。
読者がこの続きを毎日読みに来るか、を基準にしてください。
判定は必ず二段で行ってください。
1. まず台詞の言い回しを評価から外し、「誰が・何をするか・なぜそうするか」だけで、出来事と配置が通るかを比べる。
2. そのうえで台詞を戻し、話した人物が直前までに何を知ったか、今どんな気持ちか、その一言が以後にどんな行動をすると約束するかを確かめ、文脈に合うかを見る。一言だけが魅力的でも、文脈に合わなければ高く評価しない。
{rubric}
答えは一問一行、次の形だけ。ツールは使わない。
問1: X | 弱い案の弱い話: 第N話 | 型: {kindfmt} | 理由: 一行
"""


def pair_prompt(full):
    return (PAIR.replace("{rubric}", ("展開が弱くなるよくある型（弱い案の型は、このどれか）：\n" + RUBRIC + "\n") if full else "")
            .replace("{kindfmt}", "型の名前（英字）" if full else "一言"))


OWNER_ASK = """あなたは、この連載のオーナー（作者）の好みを当てる係です。下の各問には、同じ場面についての展開の二つの案（X と Y）があります。
一つはオーナーが選んだ案、もう一つは選ばなかった案です。オーナーがどちらを選ぶかを答えてください。文の上手さの一般論ではなく、この作品とこのオーナーの決め方で答えてください。
判定は必ず二段で行ってください。
1. まず台詞の言い回しを評価から外し、「誰が・何をするか・なぜそうするか」だけで、出来事と配置が通るかを比べる。
2. そのうえで台詞を戻し、話した人物が直前までに何を知ったか、今どんな気持ちか、その一言が以後にどんな行動をすると約束するかを確かめ、文脈に合うかを見る。一言だけが魅力的でも、文脈に合わなければ選ばない。
答えは一問一行、次の形だけ。ツールは使わない。
問1: X | 理由: 一行
"""


def overlap(a, b):
    a, b = re.sub(r"\s", "", a), re.sub(r"\s", "", b)
    return any(a[i:i + 12] in b for i in range(0, max(len(a) - 12, 0), 6))


def parse(text):
    got = {}
    for m in re.finditer(r"問(\d+)\s*[:：]\s*([XY])(.*)", text or ""):
        rest = m.group(3)
        ep = re.search(r"第(\d+)話", rest)
        kind = re.search(r"型\s*[:：]\s*([a-z_]+)", rest)
        why = re.search(r"理由\s*[:：]\s*(.+)", rest)
        got[int(m.group(1))] = {"ans": m.group(2), "ep": int(ep.group(1)) if ep else None,
                                "kind": kind.group(1) if kind else None, "why": why.group(1).strip() if why else ""}
    return got


def evaluate(which, n, seed, batch, conds):
    rnd = random.Random(seed)
    if which == "broken":
        P = jl_read(pdir() / "problems.jsonl")
    else:
        P = owner_rows()
    if not P:
        sys.exit("問題がない（make / harvest が先）")
    hold = rnd.sample(P, min(n, len(P)))
    jobs, keys = [], {}
    for cond in conds:
        full = cond == "full"
        for b in range(0, len(hold), batch):
            chunk = hold[b:b + batch]
            for flip in (False, True):
                items, key = [], []
                for i, p in enumerate(chunk, 1):
                    good_first = flip ^ (i % 2 == 0)
                    if which == "broken":
                        x, y = (p["orig"], p["broken"]) if good_first else (p["broken"], p["orig"])
                        items.append(f"## 問{i}\n### X\n{x}\n\n### Y\n{y}")
                    else:
                        x, y = (p["after"], p["before"]) if good_first else (p["before"], p["after"])
                        items.append(f"## 問{i}（{p['where']}）\n前提：{p['context']}\nX：{x}\nY：{y}")
                    key.append("X" if good_first else "Y")
                if which == "broken":
                    head = pair_prompt(full) + A.SEP + work_context(full)
                else:
                    # 伏せるのはこの束の問だけ。同じ文を含む例も外す（taste.py と同じ）
                    ex = [r for r in P if r not in chunk and not any(overlap(r["before"] + r["after"], c["before"] + c["after"]) for c in chunk)] if full else []
                    head = OWNER_ASK + A.SEP + work_context(full) + (A.SEP + A.section("オーナーが選んだ例（選ばなかった案 → 選んだ案）", owner_examples(ex)) if ex else "")
                prompt = head + A.SEP + "# 問題\n\n" + "\n\n".join(items)
                jobs.append((AGENT, prompt, (cond, b, flip)))
                keys[(cond, b, flip)] = (key, chunk)
    rows = []
    for tag, text, err in many(jobs):
        got = parse(text)
        key, chunk = keys[tag]
        for i, (k, p) in enumerate(zip(key, chunk), 1):
            g = got.get(i, {})
            rows.append({"cond": tag[0], "flip": tag[2], "id": p["id"], "ok": g.get("ans") == k, "answered": bool(g),
                         "ep_ok": (g.get("ep") == p.get("ep")) if which == "broken" else None,
                         "kind_ok": (g.get("kind") == p.get("kind")) if which == "broken" else None,
                         "why": g.get("why", "")})
    report(which, seed, hold, rows, conds)


def report(which, seed, hold, rows, conds):
    day = f"{datetime.date.today()}-{which}-s{seed}"
    lines = [f"# 展開の判定役の測定（{day}）", "",
             f"問題 {len(hold)}（{'壊した版' if which == 'broken' else 'オーナーが直した展開'}）×順番2通り。"
             + ("full は良い例・好み・市場の調べ・弱くなる型の一覧を渡す。plain は作品の核だけ。" if which == "broken"
                else "full は好み・良い例・市場の調べと、伏せた問以外のオーナーの例を渡す。plain は作品の核だけ。"), "",
             "| 条件 | 当たり（判定の数） | 両方の順で当てた | 両方の順で答えがそろった問だけの当たり |"
             + (" 弱い話も当てた | 型も当てた |" if which == "broken" else ""),
             "|---|---|---|---|" + ("---|---|" if which == "broken" else "")]
    for c in conds:
        R = [r for r in rows if r["cond"] == c]
        ok = sum(r["ok"] for r in R)
        by = {}
        for r in R:
            by.setdefault(r["id"], []).append(r["ok"])
        both = sum(1 for v in by.values() if len(v) == 2 and all(v))
        cons = sum(1 for v in by.values() if len(v) == 2 and (all(v) or not any(v)))
        line = f"| {c} | {ok}/{len(R)}（{ok / max(len(R), 1):.0%}） | {both}/{len(by)} | {both}/{cons}（{both / max(cons, 1):.0%}） |"
        if which == "broken":
            ep = sum(1 for r in R if r["ok"] and r["ep_ok"])
            kd = sum(1 for r in R if r["ok"] and r["kind_ok"])
            line += f" {ep}/{len(R)}（{ep / max(len(R), 1):.0%}） | {kd}/{len(R)}（{kd / max(len(R), 1):.0%}） |"
        lines.append(line)
    if which == "broken":
        hmap = {h["id"]: h for h in hold}
        lines += ["", "## 型ごとの当たり（判定の数）", "", "| 型 | " + " | ".join(conds) + " |", "|---|" + "---|" * len(conds)]
        for k, (label, _) in KINDS.items():
            cells = []
            for c in conds:
                R = [r for r in rows if r["cond"] == c and hmap[r["id"]]["kind"] == k]
                cells.append(f"{sum(r['ok'] for r in R)}/{len(R)}" if R else "-")
            lines.append(f"| {k}（{label}） | " + " | ".join(cells) + " |")
    out = pdir() / f"eval-{day}.md"
    A.write(out, "\n".join(lines))
    (pdir() / f"eval-{day}-rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines))


# ---- 4. 章のあらすじの判定（judge） ----

JUDGE = """あなたは、この連載の担当編集です。下の「章のあらすじ」は、作者が本文の前に書いた章の設計です。オーナーは全部を読む時間がないので、
あなたの判定を見て、弱い話から読みます。読者がこの続きを毎日読みに来るか、を基準に、各話の展開を判定してください。
文の上手さ・誤字・設定の細かい食い違いは見ない（別の点検がある）。見るのは展開：出来事・配置・誰が何を知るか・引き・その話の報酬・山場までの間合い。
判定は必ず二段で行う。まず台詞の言い回しを外し、「誰が・何をするか・なぜそうするか」だけで出来事と配置が通るかを見る。次に台詞を戻し、話した人物が直前までに何を知ったか、今どんな気持ちか、その一言が以後にどんな行動をすると約束するかを確かめ、文脈に合うかを見る。一言だけが魅力的でも、文脈に合わなければ強い展開とはしない。

展開が弱くなるよくある型（当てはまれば名前を添える。これ以外の弱さも書いてよい）：
{rubric}

採用済みの話（「これまでのあらすじ」の部分）は判定しない。これから書く話だけ。
次の形だけで答える。ツールは使わない。

## 一番弱い所（重い順に3つまで）
- 第N話：何が弱いか（一行）：直す方向（一行。新しい設定を足さない）

## 話ごと
| 話 | 判定 | 型 | 理由（一行） |
|---|---|---|---|
| 第N話 | 弱い／普通／強い | 型の名前か「-」 | ... |

## 章の要約（オーナーが最初に読む。400字以内）
（章で何が起きて、どこで盛り上がり、どこで止まるか。判定は書かない）
"""


def judge(path, runs):
    p = A.WORK / path
    if not p.is_file():
        sys.exit(f"{path} がない")
    prompt = (JUDGE.replace("{rubric}", RUBRIC) + A.SEP + work_context(True)
              + (A.SEP + A.section("オーナーが選んだ例（選ばなかった案 → 選んだ案）", owner_examples(owner_rows())) if owner_rows() else "")
              + A.SEP + A.section("これまでのあらすじ（採用済み）", A.doc("synopsis"))
              + A.SEP + A.section("章のあらすじ", p.read_text(encoding="utf-8")))
    out_dir = p.parent / "notes"
    out_dir.mkdir(exist_ok=True)
    texts = {}
    for tag, text, err in many([(AGENT, prompt, i) for i in range(1, runs + 1)]):
        if text:
            texts[tag] = text
            head = (f"# 展開の判定（plot_judge.py、{datetime.date.today()}、{tag}回目）\n\n"
                    "参考。測定の当たりは research/plot-judge/README.md。判定で展開を決めず、オーナーが読む順番（弱い所から）に使う。\n\n")
            print(A.write(out_dir / f"plot-judge-{p.stem}-{tag}.md", head + text))
    if len(texts) > 1:
        print(A.write(out_dir / f"plot-judge-{p.stem}.md", merge(texts, p)))


RANK = {"弱い": 0, "普通": 1, "強い": 2}


def merge(texts, p):
    """何回かの判定を並べ、そろった判定とそろわない判定を分ける（オーナーが読む一枚）。"""
    table = {}
    for tag, text in sorted(texts.items()):
        for m in re.finditer(r"^\|\s*第(\d+)話\s*\|\s*(弱い|普通|強い)\s*\|\s*([^|]*)\|\s*([^|]*)\|", text, re.M):
            table.setdefault(int(m.group(1)), {})[tag] = (m.group(2), m.group(3).strip(), m.group(4).strip())
    tags = sorted(texts)
    lines = [f"# 展開の判定のまとめ（plot_judge.py、{datetime.date.today()}、{len(tags)}回）", "",
             f"対象：{p.relative_to(A.WORK)}。各回の全文は plot-judge-{p.stem}-N.md。参考（当たりは research/plot-judge/README.md）。",
             "読む順番：「そろって弱い」→「割れた」→ほかは見出しと一行。", "",
             "| 話 | " + " | ".join(f"{t}回目" for t in tags) + " | まとめ |", "|---|" + "---|" * (len(tags) + 1)]
    groups = {"そろって弱い": [], "割れた": [], "そろって普通か強い": []}
    for n in sorted(table):
        v = [table[n].get(t, ("-", "", ""))[0] for t in tags]
        r = [RANK.get(x) for x in v if x in RANK]
        g = "そろって弱い" if r and max(r) == 0 else "割れた" if r and 0 in r else "そろって普通か強い"
        groups[g].append(n)
        lines.append(f"| 第{n}話 | " + " | ".join(f"{x}（{table[n].get(t, ('', '-', ''))[1]}）" for x, t in zip(v, tags)) + f" | {g} |")
    lines += [""] + [f"- {g}：" + ("、".join(f"第{n}話" for n in ns) or "なし") for g, ns in groups.items()]
    lines += ["", "## 理由（回ごと）"]
    for n in sorted(table):
        lines.append(f"- 第{n}話：" + " ／ ".join(f"{t}回目 {table[n][t][2]}" for t in tags if t in table[n]))
    m = re.search(r"## 章の要約.*?\n(.+)", texts[tags[0]], re.S)
    if m:
        lines += ["", "## 章の要約（1回目）", m.group(1).strip()]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("base", "make", "harvest", "owner-norm", "eval", "judge"))
    ap.add_argument("files", nargs="*", help="base：話（EP001 …、省略で全部）／judge：章のあらすじ")
    ap.add_argument("--n", type=int, default=44)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--width", type=int, default=4, help="make：一問の話数")
    ap.add_argument("--set", default="broken", choices=("broken", "owner"))
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--cond", nargs="+", default=["plain", "full"])
    ap.add_argument("--runs", type=int, default=2, help="judge：回数（ぶれを見る）")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--agent", default="claude", choices=("claude", "codex"))
    a = ap.parse_args()
    global WORKERS, AGENT
    WORKERS, AGENT = a.workers, a.agent
    if a.cmd == "base":
        base_cmd(a.files)
    elif a.cmd == "make":
        make(a.n, a.seed, a.width)
    elif a.cmd == "harvest":
        harvest()
    elif a.cmd == "owner-norm":
        owner_norm()
    elif a.cmd == "eval":
        evaluate(a.set, a.n, a.seed, a.batch, a.cond)
    else:
        judge(a.files[0], a.runs)


if __name__ == "__main__":
    main()
