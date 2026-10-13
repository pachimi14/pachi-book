#!/usr/bin/env python3
"""本文の点検を一度に回し、一枚の対応表にまとめる（2026-10-01）。

回すもの（並行）：
  機械：check_episode.py（作品の tools/work_checks.py を含む）と check_reuse.py（再演。前の採用版との言い回しの重なり・台帳で封印した材料）
  筋：check_logic.py（1回）
  声：check_voice.py（2回。ぶれを補う）
そのあと、まとめ役が重なりを一つにし、重い順に番号を振って notes/check-Vn.md に書く。
表は「必須」と「参考」に分かれる。必須の「対応」は書き手が埋める（直した／直さない：理由）。参考は書き手が選ぶ。
（2026-10-01 の検証：ツールが拾ったのに直さずに渡した所があり、オーナーがあとで直していた）

使い方（作品リポジトリのルートで）:
  python ../pachi-book/scripts/check_all.py EP023 V2          # 点検して対応表を作る
  python ../pachi-book/scripts/check_all.py EP023 V2 --status # 閉じていない行を数える（0 でなければ終了コード 1。読みにくさの行は「直さない」で閉じられない）
  python ../pachi-book/scripts/check_all.py EP024 V22 --base V21  # 差分の点検（文脈だけ。直すたび）
  python ../pachi-book/scripts/check_all.py EP024 V30 --final      # 採用前の全文の点検（行ごとに直すか選ぶ）
初見読者レビュー（check_reader.py）は別。採用前の最後に一回回す。

工程（2026-10-13 オーナー。研究 kyuketsu-mahou-syojo04/research/process-review-2026-10-13.md。
　　旧：2026-10-03。EP024 で全文の点検を6回回しても必須が尽きず、EP025〜026 では「削る」の必須で声の文まで消えて報告だけが残った）：
  1. 初稿のあと：機械と筋だけ（このスクリプトを版だけで。声の点検は回さない）。必須は筋と事実だけで、全部対応する。
     参考（AIっぽい・照準・仕組み・リズムなど）は書き手が選ぶ。削るだけの対応はしない（言い換える・判断の文を置く）。
  2. オーナーが場面に ○／△／× を付けたあとの直しは、文脈が変わるとき（筋・人物・場面の順）だけ --base で差分の点検。
     行の直しにはかけない。見るのは文脈だけ（つながり・前提・伏線・重なり・直しどうし・事実）。
  3. 場面が全部 ○ になってから、採用前に --final で全文の点検（機械・筋・声）。必須と出ても、直すのは本当に破綻している所と、
     変えたほうが面白くなる所だけ。直さない行は「見送り：理由」で閉じ、直した行と見送った行の一覧をオーナーに見せる。
  4. そのあと初見読者レビュー（check_reader.py）を1回。直したら --base で差分の点検。
  声の点検を初稿にもかけたいときは --voice。
オーナーが書いた文は一字も直さずに入れる。差分の点検で文脈が引っかかったら、直さずにオーナーに報告して決めてもらう。
オーナーの文は episodes/EPxxx/notes/owner-lines.md に一行ずつ（「…」で）書いておく。点検係に渡す。
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

MERGE = """あなたはこの連載の編集長です。一つの話に、別々の点検係が出した指摘を一枚の対応表にまとめます。
資料：機械の点検、筋の点検、声の点検（同じ係が2回。挙げる所が回ごとにぶれる）、今回の本文。

まとめ方：
- 同じ文・同じ問題を指す指摘は一つにまとめる。
- 本文に照らして間違っている指摘（本文に書いてあることを「ない」と言う、など）は落とす。
- 声の点検で一回にしか出ていない指摘は、本文に照らして当たっているものだけ残す。
- 機械の点検の WARN は、本文を見て直す価値のあるものだけ残す（台帳で決まった数字、意図した型は落とす）。
- 機械の「再演の点検」の［再演］（前の採用版 2 話以上に同じ言い回し）と［封印］（台帳で封印した材料）は、落とさず必須に入れる（種類「再演」。2026-10-10 オーナー「2 回以上なら使わない」）。
  ただし事実として触れているだけ（「あの夜の流れ星」と名詞で指すだけ）なら、直す方向を「事実の言及なら残す」と書く。［既出］［転換点］は参考（種類「再演」）。
- 重い順に並べる：①事実・筋の食い違い ②読者が一度で詰まる ③抽象のまとめ・ダメな例の型 ④足りない所・書きすぎ ⑤リズム・数字。
- 直した文は書かない。直す方向を一言だけ書く。
- 筋の点検の「確実」は、本文に照らして間違っていない限り全部残す。行の数で削らない（2026-10-01：25行で打ち切って当たりを落としていた）。

表は二つに分ける（2026-10-01：全部の行に従うと本文が4割長くなり、オーナーの直しとかけ離れた。2026-10-13：声の文まで削られて報告だけが残ったので、必須を筋と事実に絞った）。
- 必須：事実／つながり／指示語／話し手／立場／段階／人の動き／読者が知らない言葉／現場の細部／決定との照合（本文が作者の決定から外れた所）／再演（［再演］［封印］）。読者が一度で詰まる・筋が食い違う・前の話の繰り返しの所だけ。
- 参考：照準／AIっぽい／ダメな例／仕組み／比喩／緊張／足りない／書きすぎ／リズム／数字。直すかどうかは書き手が選ぶ（採用前の点検では行ごとに「直す／見送り」を選ぶ）。
- AIっぽい文の扱い（2026-10-13 オーナー）：削るのは「抽象のまとめ」だけ。気持ちを抽象語で名づける（覚悟・言葉を持っていなかった）、否定の強調の決まり文句（何ひとつ〜なかった）、AならX・BはYの対句、格言。
  段落の最後の「具体の評価」の一文（我ながら苦しい。たぶん逆効果だった。審査員は俺一人だったが、通った。）はこの語り手の声そのもので、AIっぽい文ではない。挙げない。
  直す方向は「削る」だけにしない。「その場で思ったことに言い換える」「報告の直後に判断を置く」のように、声を残す方向を書く。
- 地の文の塊が報告（〜た。）だけで終わっている場面は「仕組み」として参考に挙げ、「報告のあとに判断・理由・言い直しを置く」と方向を書く。
次の形式だけで答えてください。ツールは使わないでください。

## 必須
| ID | 場所（本文を短く引用） | 種類 | 何がおかしいか | 直す方向 | 出どころ | 対応 |
|---|---|---|---|---|---|---|
| C01 | 「…」 | 事実 | … | … | 筋・声2回 | 未 |

## 参考
| ID | 場所（本文を短く引用） | 種類 | 何がおかしいか | 直す方向 | 出どころ | 対応 |
|---|---|---|---|---|---|---|
| R01 | 「…」 | 比喩 | … | … | 声2回 | 未 |

出どころは「機械」「再演」「筋」「声1回」「声2回」の組み合わせ。対応の欄は全部「未」にする。
"""


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
    return (r.stdout + r.stderr).strip() + "\n\n" + (r2.stdout + r2.stderr).strip()


READABLE_OK = ("事実", "段階")   # 「直さない」で閉じてよいのは筋の行だけ（2026-10-02 オーナー）
OWNER_WORDS = re.compile(r"オーナー[（(]\d{4}-\d{2}-\d{2}[)）]「[^」]+」")
REF_MUST = re.compile(r"日本語|重複|二度|繰り返|同じことを|普通の言い方")


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _quotes(cell):
    return [q for q in re.findall(r"「([^」]{6,})」", cell)]


def status(ep, ver):
    """2026-10-02 オーナー：点検が拾った読みにくさを、書き手が「直さない」と書いて閉じていた（EP024 V10）。
    - 必須：未は空。「直さない」で閉じてよいのは種類が事実・段階の行だけで、オーナーの言葉を「オーナー（日付）「…」」で引く。
      それ以外（話し手・指示語・つながり・照準・AIっぽい・ダメな例など読みにくさ）の「直さない」は空と数える。
    - 参考：日本語の不自然さ・重複・繰り返しの行は必須と同じに扱う。ほかの参考も「未」のままにしない（読んで直す／直さないを書く）。
    - 「直した」と書いた行は、引用した元の文が後の版にそのまま残っていたら空に戻す。"""
    files = [f for f in (A.notes_dir(ep) / f"check-{ver}.md", A.notes_dir(ep) / f"diff-{ver}.md") if f.is_file()]
    if not files:
        sys.exit(f"{ep} {ver} の点検の表がない（先に点検を回す）")
    total = 0
    for p in files:
        total += _status_one(ep, ver, p)
    sys.exit(1 if total else 0)


def _status_one(ep, ver, p):
    body = p.read_text(encoding="utf-8")
    lines = body.splitlines()
    final = "採用前の点検" in lines[0]
    if p.name.startswith("diff-"):
        bad = []
        for l in lines:
            if not re.match(r"\|\s*D\d+", l):
                continue
            c = _cells(l)
            rid, who, ans = c[0], c[-2], c[-1]
            if re.fullmatch(r"未?", ans):
                bad.append((rid, "未"))
            elif "オーナー" in who and not OWNER_WORDS.search(ans):
                bad.append((rid, "オーナーの文の行は、オーナーの言葉（オーナー（日付）「…」）を引いて閉じる"))
        nrows = sum(1 for l in lines if re.match(r"\|\s*D\d+", l))
        print(f"{p.relative_to(A.WORK)}：文脈の行 {nrows}。閉じていない {len(bad)} 行")
        for rid, why in bad:
            print(f"  {rid}：{why}")
        return len(bad)
    rows = [l for l in lines if re.match(r"\|\s*C\d+", l)]
    ref = [l for l in lines if re.match(r"\|\s*R\d+", l)]
    n = int(ver.lstrip("V"))
    later = sorted((int(m.group(1)), f) for f in (A.WORK / "episodes" / ep).glob("V*.md")
                   if (m := re.match(r"V(\d+)\.md$", f.name)) and int(m.group(1)) > n)
    latest = later[-1][1].read_text(encoding="utf-8") if later else None
    bad = []
    for l, must in [(l, True) for l in rows] + [(l, False) for l in ref]:
        c = _cells(l)
        if len(c) < 3:
            continue
        rid, place, kind, ans = c[0], c[1], c[2], c[-1]
        text = " ".join(c[1:-1])
        hard = must or bool(REF_MUST.search(text))
        why = None
        if re.fullmatch(r"未?", ans):
            why = "未"
        elif final and ans.startswith("見送り"):
            pass   # 採用前の点検：直すのは破綻と面白くなる所だけ（2026-10-03 オーナー）。見送りは理由つきで閉じる
        elif ans.startswith("直さない") and hard:
            if OWNER_WORDS.search(ans):
                pass   # オーナー本人が決めた行は、種類を問わず閉じてよい（AI の判断では閉じられない）
            elif not any(k in kind for k in READABLE_OK):
                why = "読みにくさの行は「直さない」で閉じられない（閉じられるのはオーナーの言葉を引いたときだけ）"
            else:
                why = "直さない理由にオーナーの言葉（オーナー（日付）「…」）がない"
        elif ans.startswith("直した") and latest is not None and "台帳" not in ans and "メモ" not in ans:
            left = [q for q in _quotes(place) if q in latest]
            shown = [q for q in _quotes(ans) if q.replace("〜", "") in latest]   # 対応欄に引いた新しい文が後の版にあれば直したと見る
            if left and not shown:
                why = f"直したと書いたが {later[-1][1].name} に元の文が残っている：「{left[0][:30]}」"
        if why:
            bad.append((rid, why, l))
    print(f"{p.relative_to(A.WORK)}：必須 {len(rows)} 行・参考 {len(ref)} 行。閉じていない {len(bad)} 行"
          + (f"（直したかは {later[-1][1].name} で確かめた）" if later else "（後の版がないので、直したかは確かめていない）"))
    for rid, why, l in bad:
        print(f"  {rid}：{why}")
    return len(bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--base", help="差分の点検：前の版（例 V21）。直したことで文脈がおかしくなっていないかだけを見る")
    ap.add_argument("--final", action="store_true", help="採用前の全文の点検（行ごとに直すか選ぶ。見送りは理由つきで閉じる）")
    ap.add_argument("--voice", action="store_true", help="声の点検も回す（既定では採用前の --final のときだけ回す。2026-10-13）")
    ap.add_argument("--bad-examples", help="声の点検に渡す、同じ型の場面のオーナーの直しの組（ファイル）。既定では渡さない")
    A.add_model_args(ap)
    a = ap.parse_args()
    ep, ver = a.episode, a.version
    if a.status:
        status(ep, ver)
    if a.base:
        diff_check(ep, ver, a.base, a)
        return
    name = A.agents(a.agent)[0]
    mech = mechanical(ep, ver)
    jobs = [(name, check_logic.prompts(ep, ver), "logic")]
    with_voice = a.final or a.voice
    if with_voice:   # 2026-10-13：初稿の点検は機械と筋だけ。声の点検は採用前（--final）か --voice のときだけ
        vp = check_voice.prompt(ep, ver, a.bad_examples)
        jobs += [(name, vp, "voice-1"), (name, vp, "voice-2")]
    got = {"voice-1": "（今回は回していない。初稿の点検は機械と筋だけ。2026-10-13）", "voice-2": "（同上）"}
    for tag, text, err in A.run_many(jobs, a.model, a.effort):
        if err:
            print(f"{tag}: {err}")
            text = f"（失敗：{err}）"
        got[tag] = text
        kind = "筋の点検" if tag == "logic" else "声の点検"
        out = A.notes_dir(ep) / (f"logic-{ver}-{name}.md" if tag == "logic" else f"{tag.replace('voice', 'voice-' + ver + '-' + name)}.md")
        A.write(out, f"# {kind} {ep} {ver}（{name} {tag}）\n\n{text}")
    merge_prompt = A.SEP.join([MERGE, A.section("機械の点検", mech), A.section("筋の点検", got["logic"]),
                               A.section("声の点検（1回目）", got["voice-1"]), A.section("声の点検（2回目）", got["voice-2"]),
                               A.section("今回の本文", A.episode_text(ep, ver))])
    table, err = A.run(name, merge_prompt, a.model, a.effort)
    if err:
        sys.exit(f"まとめ：{err}")
    out = A.notes_dir(ep) / f"check-{ver}.md"
    head = (f"# 点検の対応表 {ep} {ver}" + ("（採用前の点検）" if a.final else "") + "\n\n"
            + ("採用前の点検（2026-10-03 オーナー）：必須と出ても直すかは行ごとに選ぶ。直すのは本当に破綻している所と、変えたほうが面白くなる所だけ。"
               "ほかは「見送り：理由」で閉じ、直した行と見送った行の一覧をオーナーに見せる。オーナーの文は直さない。\n" if a.final else "")
            + "「必須」（筋と事実）の対応を書き手が全部埋める：直した（どう直したか一言）／直さない：理由。埋めてからオーナーに渡す。\n"
            "「参考」は直すかどうかを書き手が選ぶ（全部に従わない。削るだけで対応しない。段落の最後の具体の評価の一文は声なので残す。2026-10-13）。\n"
            "直した版は `check_episode.py 新しい版 --base 直す前の版` で字数の増え方を確かめる。\n"
            f"確かめ方：`python ../pachi-book/scripts/check_all.py {ep} {ver} --status`\n"
            "直した版で点検をかけ直すときは、新しい版の番号で回す。\n\n")
    print(A.write(out, head + table + f"\n\n## 機械の点検（元の出力）\n\n```\n{mech}\n```"))


if __name__ == "__main__":
    main()
