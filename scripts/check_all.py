#!/usr/bin/env python3
"""本文の点検を一度に回し、一枚の対応表にまとめる（2026-10-01。2026-10-14 組み替え：research/protocol-v3 §4）。

回すもの：
  機械（LLM なし）：check_episode.py（作品の tools/work_checks.py を含む）、check_reuse.py（再演・封印・一話の中の重なり）、check_decisions.py（決定との照合の機械版）
  筋：check_logic.py（1 回。束は RULES・カード・あらすじ・前の話・決定・本文。約 2〜3 万字）
  声：check_voice.py（--final のときだけ 1 回。AIっぽい・書きすぎ・言葉と物・数字）
まとめ役の LLM は置かない。スクリプトが機械と筋（と声）の出力を一枚の表に並べる（notes/check-Vn.md）。

表の読み方（2026-10-14 オーナー。工程 5）：必須も参考も「提案」。書き手は自動で直さない。
行ごとの「今の文／案A／案B／推奨」をチャットで出し、オーナーが選んだものだけを次の版に入れる。
機械の ERROR・［NG］・［再演］・［封印］だけは書き手が直してよい（何を直したか一覧で報告）。

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_all.py EP026 V4            # 初稿の点検（機械＋筋）
  python ../pachi-book/scripts/check_all.py EP026 V5 --final    # 採用前の点検（機械＋筋＋声 1 回）
  python ../pachi-book/scripts/check_all.py EP026 V5 --base V4  # 差分の点検（場面の順・人物の配置・誰が何を知るかが変わった直しのときだけ。文脈だけ）
廃止（2026-10-14）：--status（必須を全部埋める関門）、声 2 回、まとめ役の LLM、温度。
"""
import difflib
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402
import check_logic  # noqa: E402
import check_voice  # noqa: E402

DIFF = """あなたはこの連載の編集長です。前の版から本文を直しました。直したことで文脈がおかしくなっていないかだけを点検します。
本文は全文を渡します。直した所は【直した所】…【ここまで】、直す前の文は【直す前の文：…】、消しただけの文は【消した文：…】で示してあります。

見ること（文脈だけ）：
- つながり：直した所の前後で、話し手・指示語・時間の順・人や物の位置が一度で通るか。
- 前提：直しで消えた・変わった内容を、離れた所の文が前提にしていないか（後ろの台詞が、消えた情報を受けていないか）。
- 伏線：前に置いた振りや、後ろの受けが、直しで相手を失っていないか。
- 重なり：直した文と同じことを、近くの別の文がもう言っていないか。
- 直しどうし：同じ版で直した所どうしが食い違っていないか。
- 事実：直した所が、台帳・前の話・作者の決定（章のあらすじ・メモ）とぶつからないか。

見ないこと：
- 読者が常識で補える動作や段取りが書かれていないこと（カップを持ってから置く、店に入ってから座る、紅茶が来てから飲む、など）。小説は一から十まで描写しない。描写の省略を「前提」「つながり」の指摘にしない（2026-10-10 オーナー「一から十まですべて本文に描写しないとおかしいって指摘…小説の執筆に合ってない」）。
- 直していない所の問題（直した所に引きずられて意味が変わった所は見る）。
- 日本語の言い回し・リズム・比喩・型（AIっぽい・ダメな例）・好み。書き手の直しは別に点検済み。オーナーの文は日本語を点検しない。
- 足したほうがよい描写。

「オーナーが書いた文」の一覧に入っている文に引っかかりがあるときは、その文を直す方向を書かない。
どの文とどうぶつかるかだけを書き、誰の文の欄を「オーナー」にする。

次の形式だけで答えてください。ツールは使わないでください。引っかかりがなければ表の行を書かず「なし」とだけ書く。

## 文脈
| ID | 直した所（短く引用） | 種類 | ぶつかる所（短く引用） | 何がおかしいか | 直す方向 | 誰の文 | 対応 |
|---|---|---|---|---|---|---|---|
| D01 | 「…」 | 前提 | 「…」 | … | … | 書き手 | 未 |

種類は つながり／前提／伏線／重なり／直しどうし／事実 のどれか。誰の文は「書き手」か「オーナー」。対応の欄は全部「未」にする。
"""


def marked_diff(old, new):
    """新しい版の本文に、直した所と消した文の印を付ける。"""
    a, b = old.splitlines(), new.splitlines()
    out, n = [], 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out += b[j1:j2]
            continue
        n += 1
        gone = [l for l in a[i1:i2] if l.strip()]
        if tag == "delete":
            out += [f"【消した文：{l.strip()}】" for l in gone]
            continue
        old_set = set(a[i1:i2])
        for l in b[j1:j2]:
            out.append(l if l in old_set or not l.strip() else f"【直した所】{l}【ここまで】")
        out += [f"【直す前の文：{l.strip()}】" for l in gone if l not in b[j1:j2]]
    return "\n".join(out), n


def owner_lines(ep):
    p = A.notes_dir(ep) / "owner-lines.md"
    return p.read_text(encoding="utf-8") if p.is_file() else "（記録なし）"


def diff_check(ep, ver, base, a):
    old, new = A.episode_text(ep, base), A.episode_text(ep, ver)
    marked, n = marked_diff(old, new)
    if not n:
        sys.exit(f"{base} と {ver} に違いがない")
    prompt = A.SEP.join([DIFF, check_logic.context(ep), A.section("オーナーが書いた文（日本語は点検しない。直す方向を書かない）", owner_lines(ep)),
                         A.section(f"今回の本文（{base} → {ver}。直した所 {n} か所）", marked)])
    name = A.agents(a.agent)[0]
    table, err = A.run(name, prompt, a.model, a.effort)
    if err:
        sys.exit(f"差分の点検：{err}")
    head = (f"# 差分の点検 {ep} {base} → {ver}（文脈だけ）\n\n"
            "書き手の文の行：直した（どう直したか）／直さない：理由（文脈の行なので、理由があれば閉じてよい）。\n"
            "オーナーの文の行：書き手は直さない。オーナーに報告し、決めた言葉を「オーナー（日付）「…」」で引いて閉じる。\n"
            f"確かめ方：`python ../pachi-book/scripts/check_all.py {ep} {ver} --status`\n\n")
    print(A.write(A.notes_dir(ep) / f"diff-{ver}.md", head + table))


def mechanical(ep, ver):
    here = Path(__file__).resolve().parent
    r = subprocess.run([sys.executable, str(here / "check_episode.py"), f"episodes/{ep}/{ver}.md"], capture_output=True, text=True,
                       encoding="utf-8", cwd=A.WORK)
    r2 = subprocess.run([sys.executable, str(here / "check_reuse.py"), ep, ver], capture_output=True, text=True,
                        encoding="utf-8", cwd=A.WORK)   # 再演の点検（2026-10-13）
    r3 = subprocess.run([sys.executable, str(here / "check_decisions.py"), ep, ver], capture_output=True, text=True,
                        encoding="utf-8", cwd=A.WORK)   # 決定との照合（機械。2026-10-14）
    return "\n\n".join((x.stdout + x.stderr).strip() for x in (r, r2, r3))


ROW = re.compile(r"^\|\s*([LV]\d+)\s*\|")
MUST_KINDS = ("事実", "誰が何を知る", "話し手", "立場", "指示語", "人の動き", "決定")


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_rows(text, prefix):
    """LLM の出力から表の行（| L01 | … |）を拾う。[cells]。列が足りない行は埋める。"""
    rows = []
    for l in (text or "").splitlines():
        m = ROW.match(l)
        if not m or not m.group(1).startswith(prefix):
            continue
        c = _cells(l)
        while len(c) < 8:
            c.append("")
        rows.append(c[:8])
    return rows


def compose(ep, ver, mech, logic, voice, final):
    """機械・筋・声の出力を一枚の対応表に（LLM のまとめ役なし。2026-10-14）。"""
    must, ref = [], []
    for c in table_rows(logic, "L"):
        kind = c[2]
        (must if any(k in kind for k in MUST_KINDS) else ref).append(c + ["筋"])
    for c in table_rows(voice, "V"):
        ref.append(c + ["声"])
    mech_lines = [l for l in mech.splitlines() if l.startswith(("ERROR", "WARN", "INFO"))]   # 見出し行（「再演の点検 … ［再演］0」）は入れない
    mech_must = [l for l in mech_lines if l.startswith("ERROR") or (l.startswith("WARN") and ("［再演］" in l or "［封印］" in l or "［NG］" in l))]
    mech_ref = [l for l in mech_lines if l.startswith(("WARN", "INFO")) and l not in mech_must]

    def table(rows, pre):
        out = ["| ID | 場所（本文を短く引用） | 種類 | 何がおかしいか | 今の文 | 案A | 案B | 推奨 | 出どころ | オーナーの選択 |",
               "|---|---|---|---|---|---|---|---|---|---|"]
        for i, c in enumerate(rows, 1):
            out.append(f"| {pre}{i:02d} | " + " | ".join(c[1:9]) + " | 未 |")
        return "\n".join(out) if rows else "なし"

    head = [f"# 点検の対応表 {ep} {ver}" + ("（採用前の点検）" if final else "（初稿の点検）"),
            "",
            "読み方（2026-10-14 オーナー。工程 5）：どの行も提案。書き手は自動で直さない。行ごとの「今の文／案A／案B／推奨」をチャットで出し、"
            "オーナーが選んだものだけを次の版に入れる（「オーナーの選択」の欄に A／B／直さない を写す）。"
            "指摘を読むときは、本文で今何が成立しているか、補足によって何を失うかを確かめてから選ぶ。",
            "機械の ERROR・［NG］・［再演］・［封印］だけは書き手が直してよい（何を直したか一覧で報告）。",
            "",
            "## 必須（筋：事実・誰が何を知る・話し手・立場・指示語・人の動き・決定）", table(must, "C"),
            "", "## 必須（機械：ERROR・NG・再演・封印。書き手が直してよい）", "\n".join(f"- {l}" for l in mech_must) or "なし",
            "", "## 参考（筋：読者が知らない言葉" + ("／声：AIっぽい・書きすぎ・言葉と物・数字" if final else "") + "）", table(ref, "R"),
            "", "## 参考（機械：WARN・INFO）", "\n".join(f"- {l}" for l in mech_ref) or "なし",
            "", "## 機械の点検（元の出力）", "```", mech, "```"]
    return "\n".join(head)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--base", help="差分の点検：前の版（例 V21）。直したことで文脈がおかしくなっていないかだけを見る")
    ap.add_argument("--final", action="store_true", help="採用前の点検（機械＋筋＋声 1 回）。行ごとにオーナーが選ぶ")
    ap.add_argument("--voice", action="store_true", help="声の点検も回す（既定では --final のときだけ）")
    ap.add_argument("--bad-examples", help="（廃止。互換のため残す）")
    A.add_model_args(ap)
    a = ap.parse_args()
    ep, ver = a.episode, a.version
    if a.base:
        diff_check(ep, ver, a.base, a)
        return
    name = A.agents(a.agent)[0]
    mech = mechanical(ep, ver)
    jobs = [(name, check_logic.prompts(ep, ver), "logic")]
    with_voice = a.final or a.voice
    if with_voice:
        jobs.append((name, check_voice.prompt(ep, ver), "voice"))
    got = {"voice": ""}
    for tag, text, err in A.run_many(jobs, a.model, a.effort):
        if err:
            print(f"{tag}: {err}")
            text = f"（失敗：{err}）"
        got[tag] = text
        kind = "筋の点検" if tag == "logic" else "声の点検"
        out = A.notes_dir(ep) / f"{tag}-{ver}-{name}.md"
        A.write(out, f"# {kind} {ep} {ver}（{name}）\n\n{text}")
    out = A.notes_dir(ep) / f"check-{ver}.md"
    rows = compose(ep, ver, mech, got.get("logic", ""), got.get("voice", ""), a.final)
    print(A.write(out, rows))
    n_must = sum(1 for l in rows.splitlines() if re.match(r"\|\s*C\d+", l))
    n_ref = sum(1 for l in rows.splitlines() if re.match(r"\|\s*R\d+", l))
    print(f"必須（筋）{n_must}・参考 {n_ref}。案はチャットでオーナーに出し、選ばれたものだけ入れる。")


if __name__ == "__main__":
    main()
