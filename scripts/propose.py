#!/usr/bin/env python3
"""直し案の点検と記録（改稿用。2026-10-01）。

オーナーに見せる直し案（一行の直しも、A／B の二択も）は、チャットで考えたまま出さない。
ここで本文に差し込んだ形にして、筋の点検（check_logic と同じ問い）と機械の点検（check_episode）を通し、
案に番号（P…）を付けて記録する。オーナーが選んだら、記録した文そのものを新しい版に入れる（--apply）。
こうすると、オーナーに見えている案が点検済みかどうかが番号で分かり、選ばれた文と入る文がずれない。

使い方（作品リポジトリのルートで）:
  # 案を点検して記録する（案ごとにファイル。一つの案に直し所が何か所あってもよい）
  python ../pachi-book/scripts/propose.py EP020 V7 --issue "冒頭のツグミの段落" --cand a.txt --cand b.txt
  # 一か所だけの案なら
  python ../pachi-book/scripts/propose.py EP020 V7 --old "元の文" --new "案"
  # 選ばれた案を新しい版に入れる（記録した文をそのまま使う）
  python ../pachi-book/scripts/propose.py EP020 V7 --apply P20261001-2130-B --to V8

案のファイルの形（直し所ごとに @@old と @@new を並べる。@@new を空にすると削除）:
  @@old
  元の文（本文から一字一句そのまま。複数行可）
  @@new
  直した文
  @@old
  …

出力: episodes/EPxxx/notes/proposals.md（人が読む記録）と proposals.json（--apply が読む）。
案が二つ以上のときは、オーナーの好みの判定役（taste.py）にも総当たりで比べさせ、「好みの判定（参考）」を出す。
--apply でオーナーが選んだ案と選ばなかった案を <taste_dir>/choices.jsonl に記録する（判定役の例が増える）。
オーナーが案を選ばず自分で書いたときは、--owner-wrote 書いた文.txt --batch P<日時> で、オーナーの文を選んだ側として記録する。
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
import check_logic  # noqa: E402
import taste  # noqa: E402

LINE_NO = re.compile(r"^WARN\s+\d+(〜\d+)?行目：")


def parse_cand(text):
    pairs, cur, buf = [], None, []
    for line in text.split("\n"):
        if line.strip() in ("@@old", "@@new"):
            if cur == "old":
                pairs.append([("\n".join(buf)).strip("\n"), None])
            elif cur == "new":
                pairs[-1][1] = ("\n".join(buf)).strip("\n")
            cur, buf = line.strip()[2:], []
        else:
            buf.append(line)
    if cur == "new":
        pairs[-1][1] = ("\n".join(buf)).strip("\n")
    if not pairs or any(n is None for _, n in pairs):
        sys.exit("案のファイルの形が違う（@@old と @@new を対で並べる）")
    return [tuple(p) for p in pairs]


def patch(text, pairs, mark=False):
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"元の文が本文に{text.count(old)}か所ある（1か所に決まる長さにする）：{old[:30]}")
        text = text.replace(old, f"【直した所】{new}【ここまで】" if mark else new, 1)
    return text.replace("\n\n\n\n", "\n\n\n") if not mark else text


def warns(path, base=None):
    script = Path(__file__).resolve().parent / "check_episode.py"
    cmd = [sys.executable, str(script), str(path)] + (["--base", str(base)] if base else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=A.WORK)
    out = (r.stdout + r.stderr).splitlines()
    return [l for l in out if l.startswith(("WARN", "ERROR"))], [l[l.index("字数"):] for l in out if "字数" in l]


def check(ep, ver, cands):
    base = A.WORK / "episodes" / ep / f"{ver}.md"
    text = base.read_text(encoding="utf-8")
    base_w = {LINE_NO.sub("WARN ", w) for w in warns(base)[0]}
    jobs, mech = [], {}
    for key, pairs in cands.items():
        tmp = A.notes_dir(ep) / f"proposal-tmp-{key}.md"
        tmp.write_text(patch(text, pairs), encoding="utf-8", newline="\n")
        w, size = warns(tmp, base)
        mech[key] = ([x for x in w if LINE_NO.sub("WARN ", x) not in base_w], size)
        tmp.unlink()
        prompt = (f"{check_logic.PROMPT_SNIPPET}{A.SEP}{check_logic.context(ep)}{A.SEP}"
                  f"# 直したあとの本文\n\n{patch(text, pairs, mark=True)}\n")
        jobs.append((A.agents()[0], prompt, key))
    return mech, {key: (t, e) for key, t, e in A.run_many(jobs)}


def cand_text(pairs):
    return "\n／\n".join(new or "（削除）" for _, new in pairs)


def record_choice(ep, chosen_id, chosen_text, sibs, db, weak=True):
    """オーナーの選択を、好みの判定役の材料に足す。weak＝「まあこっちか」で選んだ（格は選択）。強く選んだときは明示。"""
    rec = {"date": str(datetime.date.today()), "ep": ep, "issue": next(iter(sibs.values()))["issue"], "weak": weak,
           "context": next(iter(sibs.values())).get("context", ""),
           "chosen_id": chosen_id or "owner", "chosen_text": chosen_text,
           "rejected": [{"id": k, "text": cand_text(v["pairs"])} for k, v in sibs.items()]}
    with (taste.tdir() / "choices.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    taste.build()


def verdict(text):
    m = re.search(r"##\s*判定\s*\n-\s*(\S+?)[：:（(\s]", text or "")
    return m.group(1) if m else "不明"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--issue", default="", help="オーナーの指摘・何を直す案か（一行）")
    ap.add_argument("--cand", action="append", default=[], help="案のファイル（@@old/@@new）。複数可")
    ap.add_argument("--old")
    ap.add_argument("--new")
    ap.add_argument("--apply", nargs="+", help="入れる案の番号（P…）。直し所が重ならなければ複数可")
    ap.add_argument("--by-writer", action="store_true", help="書き手が好みの判定で選んで入れる（オーナーの選択として記録しない。初稿の見せ場の案選び）")
    ap.add_argument("--strong", action="store_true", help="オーナーがよさを言って選んだ（「これがいい」「これ好き」）。材料の格を明示にする。「これでいい」は妥協のことが多いので付けない")
    ap.add_argument("--to", help="--apply で作る新しい版（例 V8）")
    ap.add_argument("--owner-wrote", help="オーナーが自分で書いた文のファイル（案は全部選ばれなかったとして記録）")
    ap.add_argument("--batch", help="--owner-wrote のとき、比べた案の組（P<日時>）")
    ap.add_argument("--no-taste", action="store_true", help="好みの判定を回さない")
    a = ap.parse_args()
    ep, ver = a.episode, a.version
    store = A.notes_dir(ep) / "proposals.json"
    db = json.loads(store.read_text(encoding="utf-8")) if store.is_file() else {}

    if a.owner_wrote:
        sibs = {k: v for k, v in db.items() if a.batch and k.startswith(a.batch + "-")}
        if not sibs:
            sys.exit("--batch の案が記録にない")
        record_choice(ep, None, Path(a.owner_wrote).read_text(encoding="utf-8").strip(), sibs, db, weak=False)
        print(f"オーナーの文を選んだ側として記録した（選ばれなかった案 {len(sibs)}）")
        return

    if a.apply:
        if not a.to or any(k not in db for k in a.apply):
            sys.exit("番号が記録にないか、--to がない")
        recs = [db[k] for k in a.apply]
        if any(r["version"] != ver for r in recs):
            sys.exit(f"{ver} に対して点検した案だけを入れられる（点検し直す）")
        src = A.WORK / "episodes" / ep / f"{ver}.md"
        dst = A.WORK / "episodes" / ep / f"{a.to}.md"
        if dst.exists():
            sys.exit(f"{dst.relative_to(A.WORK)} はもうある")
        text = src.read_text(encoding="utf-8")
        for r in recs:
            text = patch(text, [tuple(p) for p in r["pairs"]])
        dst.write_text(text, encoding="utf-8", newline="\n")
        subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "sync_current.py")], cwd=A.WORK,
                       capture_output=True)
        w, size = warns(dst, src)
        for key, rec in zip(a.apply, recs):
            stamp_key = key.rsplit("-", 1)[0]
            sibs = {k: v for k, v in db.items() if k.startswith(stamp_key + "-") and k != key}
            if sibs and not a.by_writer:
                record_choice(ep, key, cand_text(rec["pairs"]), sibs, db, weak=not a.strong)
            who = "書き手が好みの判定で" if a.by_writer else "オーナーの選択で"
            print(f"{dst.relative_to(A.WORK)} に {key} を入れた（{who}。筋の点検：{rec['verdict']}" + (f"／好み：{rec['taste']:g}勝" if rec.get("taste") is not None else "") + "）")
            if rec["verdict"] != "通る":
                print(f"  注意：筋の点検で「{rec['verdict']}」だった案。理由を proposals.md で確かめる")
        print("\n".join(size + w[:10]))
        return

    files = [Path(c).read_text(encoding="utf-8") for c in a.cand]
    cands_list = [parse_cand(t) for t in files]
    if a.old is not None:
        cands_list.append([(a.old, a.new or "")])
    if not cands_list:
        sys.exit("案がない（--cand か --old/--new）")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    keys = [f"P{stamp}-{chr(65 + i)}" for i in range(len(cands_list))]
    cands = dict(zip(keys, cands_list))
    mech, logic = check(ep, ver, cands)
    base_text = (A.WORK / "episodes" / ep / f"{ver}.md").read_text(encoding="utf-8")
    first_old = cands_list[0][0][0]
    pre = base_text[:base_text.index(first_old)].rstrip("\n").split("\n")
    context = "\n".join(x for x in pre[-3:] if x.strip())
    wins, stable, terr = ({}, 0, None)
    if len(cands) >= 2 and not a.no_taste:
        wins, stable, terr = taste.judge(context, {k: cand_text(v) for k, v in cands.items()})
    lines = [f"\n## {stamp} {ep} {ver}：{a.issue or '（指摘の要約なし）'}\n"]
    for key, pairs in cands.items():
        text, err = logic[key]
        v = "失敗" if err else verdict(text)
        db[key] = {"version": ver, "issue": a.issue, "pairs": pairs, "verdict": v,
                   "new_warns": mech[key][0], "context": context, "taste": wins.get(key)}
        tj = f"／好み：{wins[key]:g}勝" if key in wins else ""
        lines.append(f"### {key}（筋：{v}／機械：新しい警告 {len(mech[key][0])}{tj}）")
        for old, new in pairs:
            lines.append(f"- 元：{old}\n- 案：{new or '（削除）'}")
        lines.append("\n".join(["", "機械：", *(mech[key][1] + mech[key][0] or ["（新しい警告なし）"])]))
        lines.append(f"\n筋の点検：\n\n{err or text}\n")
        print(f"{key}  筋：{v}  機械：新しい警告 {len(mech[key][0])}" + (f"  好み：{wins[key]:g}勝" if key in wins else "") + f"  {mech[key][1][0] if mech[key][1] else ''}")
        for x in mech[key][0][:5]:
            print("   " + x)
    if wins:
        note = (f"好みの判定（参考。taste.py。総当たりを両方の順で聞いた勝ち数。両方の順で答えがそろった組 {stable:.0%}。"
                "測定では当たり75〜79%で、決め手には足りない）" + (f"　失敗：{terr}" if terr else ""))
        lines.insert(1, note + "\n")
        print(note)
    store.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    md = A.notes_dir(ep) / "proposals.md"
    head = "" if md.is_file() else ("# 直し案の記録\n\nオーナーに見せた案と、その点検の結果。番号（P…）で `propose.py --apply` が記録した文をそのまま入れる。\n")
    with md.open("a", encoding="utf-8", newline="\n") as f:
        f.write(head + "\n".join(lines) + "\n")
    print(f"記録：{md.relative_to(A.WORK)}（筋の点検の全文はここ）")


if __name__ == "__main__":
    main()
