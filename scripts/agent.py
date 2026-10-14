#!/usr/bin/env python3
"""LLM 点検の共通部：CLI の実行、モデルの固定、作品の資料の読み込み。

点検スクリプト（check_logic / check_voice / check_reader / check_memo / check_all / backtest）が使う。
作品リポジトリのルートで実行する前提（作品の資料は作業フォルダから読む）。

モデルと effort（2026-10-01）：既定は claude-opus-5-5 / high。変えるときは環境変数か各スクリプトの
--model / --effort。点検の結果のぶれにモデルの違いを混ぜないため、CLI の既定に任せない。
  PACHI_MODEL   既定 claude-opus-5-5
  PACHI_EFFORT  既定 high
  PACHI_AGENT   既定 auto（クラウドは claude だけ、ローカルは claude と codex）
  PACHI_TIMEOUT 既定 900 秒
  PACHI_CLAUDE / PACHI_CODEX  CLI のパス

作品ごとの資料の場所は、作品ルートの pachi.json で上書きできる（無ければ下の DEFAULTS）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ENGINE = Path(__file__).resolve().parent.parent
WORK = Path.cwd()
SEP = "\n\n---\n\n"

DEFAULTS = {
    "synopsis": "blocks/SYNOPSIS.md",          # 「- 第N話」で始まる行のあらすじ
    "characters": "canon/characters.md",
    "world": "canon/world.md",
    "abilities": "canon/abilities.md",
    "long_arcs": "blocks/LONG-ARCS.md",        # 作者用の長期の骨格
    "voice_cards": "blocks/VOICE-CARDS.md",    # 人物ごとの口調
    "voice_rules": "blocks/CH-01-voice.md",    # 主人公の掟・語り方
    "owner_eye": "blocks/OWNER-EYE.md",        # オーナーの目（書いたあとの点検）
    "bad_examples": "blocks/BAD-EXAMPLES.md",  # オーナーが直した文の組
    "good_examples": "blocks/GOOD-EXAMPLES.md",
    "line_aim": None,                          # 主人公の「らしい一言」の照準の問い（例 blocks/FAN-LINE-AIM.md）
    "write_brief": None,                       # 書き手の一枚（地の文の仕事と形・見本の話。声の点検が読む。2026-10-13）
    "motifs": "blocks/MOTIFS.md",              # 材料の台帳（「検索語」の列を check_reuse.py が当てる）
    "names": [],                               # 人物名（再演の点検で、名前だけの重なりを除く）
    "reuse_ignore": [],                        # 再演の点検で出さない言い回し
    "fixed_numbers": [],
    "rules": None,                             # 決まりごと一枚（例 blocks/RULES.md。書き手と点検に毎回渡す。2026-10-14）
    "card_heading": "### カード",              # 人物台帳の、書き手と点検に渡す節の見出し（その下から次の ### か ## まで）
    "narration_plain": [],                     # 地の文では呼び捨てにする人物名（check_episode が「名前＋さん」を ERROR にする）
    "narrator_override": {},                   # 語り手が主人公でない話 {"EP023": "ツグミ"}（地の文の敬称の点検を飛ばす）
    "type_samples": {},                        # 場面の型 → 見本の話 {"日常・会話": "EP007", "現場": "EP005", "配信": "EP009"}
    "min_chars": 0,                            # 一話の字数の下限（check_episode が WARN）
    "must_say": {},                            # 台詞に必ず出る語 {"大学時代の友人": ["私"]}（check_decisions が INFO）
    "market": [],                              # 市場の調べ（ストーリーテラーが読む）
    "goal": "",                                # 作品の目標（例：公開から1か月で★1000）
    "schedule": None,                          # 公開の予定 {"start": "YYYY-MM-DD", "first_day": 8, "per_day": 2}                       # 台帳で決まっている数字（数字の検出から除く。例 "十年"）
}


def config():
    cfg = dict(DEFAULTS)
    p = WORK / "pachi.json"
    if p.is_file():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def read(rel):
    if not rel:
        return ""
    p = WORK / rel
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def doc(key):
    return read(config().get(key))


def episode_text(ep, ver):
    p = WORK / "episodes" / ep / f"{ver}.md"
    if not p.is_file():
        sys.exit(f"{p.relative_to(WORK)} がない")
    return p.read_text(encoding="utf-8")


def prev_episode(ep):
    p = WORK / "episodes" / "current" / f"EP{int(ep[2:]) - 1:03d}.md"
    return p.read_text(encoding="utf-8") if p.is_file() else "（なし）"


def synopsis_before(n):
    """第 n 話より前のあらすじの行だけ。"""
    return "\n".join(l for l in doc("synopsis").splitlines()
                     if (m := re.match(r"- 第(\d+)話", l)) and int(m.group(1)) < n)


def _ep_sections(text, ep):
    """見出し（## か ###）が EPxxx で始まる節を、同じ深さ以上の次の見出しまで抜き出す（「EP023〜031」のような範囲の見出しは除く）。"""
    out, lines = [], text.splitlines()
    for i, l in enumerate(lines):
        m = re.match(rf"(#{{2,3}})\s+{ep}(?![〜~\-–\d])", l)
        if not m:
            continue
        depth, body = len(m.group(1)), [l]
        for nxt in lines[i + 1:]:
            m2 = re.match(r"(#{1,3})\s", nxt)
            if m2 and len(m2.group(1)) <= depth:
                break
            body.append(nxt)
        out.append("\n".join(body).strip())
    return out


def plan_files():
    """作者の決定が書いてあるファイル。pachi.json の chapter_plans（並び順どおり。今の計画だけを挙げる）があればそれだけ、
    無ければ chapters/CH-*-STORY.md と blocks/*-memos.md の全部。
    2026-10-14：EP025〜026 の点検は、glob に当たらない今の散文（CH-01-END-2026-10-13.md）を渡さず、
    「点検には使わない」と書いてある旧メモ（CH-01-E-memos.md）を渡していた。chapter_plans を正にする。"""
    cfg = config().get("chapter_plans") or []
    if cfg:
        return [WORK / p for p in cfg if (WORK / p).is_file()]
    return sorted(WORK.glob("chapters/CH-*-STORY.md")) + sorted(WORK.glob("blocks/*-memos.md"))


def memo_files():
    return [p for p in plan_files() if p.name.endswith("-memos.md")]


def episode_plan(ep):
    """その話の作者の決定：章のあらすじ（散文）の節と、ブロックのメモの節（plan_files の順）。
    見出しに【旧 が付く節は渡さない。

    2026-10-02：筋の点検にこれを渡していなかったため、点検役が決めた筋を知らずに「直す」を出し、
    直し案がそれに合わせて筋から外れていった（EP023）。メモは、確定したあらすじを場面に分けたもの。
    """
    parts = []
    for p in plan_files():
        title = "メモ" if p.name.endswith("-memos.md") else "章のあらすじ（散文）"
        for s in _ep_sections(p.read_text(encoding="utf-8"), ep):
            if "【旧" in s.splitlines()[0]:
                continue
            parts.append(f"## {title}（{p.relative_to(WORK).as_posix()}）\n\n{s}")
    return "\n\n".join(parts)


def section(title, body):
    return f"# {title}\n\n{body or '（なし）'}"


FIELD = re.compile(r"^- (視点|型|出る人物|world|検索語（触れない）|検索語（使わない）)[：:]\s*(.*)$")


def memo_fields(ep):
    """その話のメモの機械が読む欄（2026-10-14）：視点・型・出る人物・world・検索語（触れない）・検索語（使わない）。
    値は「／」区切りを list に（視点・型は str）。無い欄は入っていない。"""
    out = {}
    for p in memo_files():
        for sec in _ep_sections(p.read_text(encoding="utf-8"), ep):
            if "【旧" in sec.splitlines()[0]:
                continue
            for l in sec.splitlines():
                m = FIELD.match(l.strip() if not l.startswith("  ") else "")
                if not m:
                    continue
                key, val = m.group(1), m.group(2).strip()
                if key in ("視点", "型"):
                    out[key] = val
                else:
                    out[key] = [v.strip() for v in re.split(r"[／/]", val) if v.strip()]
    return out


def _split_sections(text, level):
    """見出し（level 個の #）で切る。[(見出しの文, 本文)]。"""
    pat = re.compile(rf"^#{{{level}}}\s+(.+)$", re.M)
    heads = list(pat.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((m.group(1).strip(), text[m.end():end]))
    return out


def cards(names=None):
    """人物台帳の「カード」（card_heading の節）だけ。names（出る人物）があればその人物だけ、無ければ全員。
    人物の名前は見出しの先頭と照らす（「友人」は「大学時代の友人（名前未定）」に当たる）。2026-10-14。"""
    text = doc("characters")
    head = config().get("card_heading") or "### カード"
    out = []
    for title, body in _split_sections(text, 2):
        if names and not any(n in title or title.split("（")[0] in n for n in names):
            continue
        m = re.search(re.escape(head) + r"[^\n]*\n(.*?)(?=\n### |\Z)", body, re.S)
        if not m:
            continue
        card = m.group(1).strip()
        if card:
            out.append(f"## {title}\n{card}")
    return "\n\n".join(out)


def knowledge(names=None):
    """人物台帳の「記録」から「- 知っていること」の箇条（とその字下げ行）だけ。前の話との矛盾を見る点検に渡す（書き手には渡さない。2026-10-14 オーナー）。"""
    text = doc("characters")
    out = []
    for title, body in _split_sections(text, 2):
        if names and not any(n in title or title.split("（")[0] in n for n in names):
            continue
        lines, keep, on = body.splitlines(), [], False
        for l in lines:
            if l.startswith("- "):
                on = l.startswith("- 知っていること")
            if on and (l.startswith("- ") or l.startswith("  ")):
                keep.append(l)
        if keep:
            out.append(f"## {title}\n" + "\n".join(keep))
    return "\n\n".join(out)


def world_sections(titles):
    """canon/world.md のうち、見出しが titles のどれかで始まる節だけ。"""
    text = doc("world")
    out = []
    for title, body in _split_sections(text, 2):
        if any(title.startswith(t) for t in titles):
            out.append(f"## {title}\n{body.strip()}")
    return "\n\n".join(out)


def rules():
    return doc("rules")


def canon_context(ep=None, with_knowledge=True):
    """点検に渡す台帳（2026-10-14 組み替え）：決まりごと一枚・出る人物のカード・「知っていること」（前の話との矛盾を見るため）・メモが指定する world の節。
    台帳の記録のそれ以外（旧状態の履歴）・LONG-ARCS・口調カード・OWNER-EYE は渡さない（73k 字の資料の中で一行の決まりが拾えなかった）。
    ep が無いとき（メモの監査など）はカードを全員分。"""
    f = memo_fields(ep) if ep else {}
    names = f.get("出る人物")
    parts = [section("決まりごと一枚（RULES）", rules()),
             section("台帳：出る人物のカード（呼び方・口調／今の距離と反応／使う能力）", cards(names))]
    if with_knowledge:
        parts.append(section("台帳：知っていること（取得話付き。前の話との矛盾はこれと、これまでのあらすじ・前の話で見る）", knowledge(names)))
    if f.get("world"):
        parts.append(section("台帳：世界（この話に関わる節）", world_sections(f["world"])))
    return SEP.join(parts)


# ---- CLI の実行 ----

KNOWN = {"claude": [Path.home() / ".local/bin/claude.exe", Path.home() / ".local/bin/claude"], "codex": []}


def find_agent(name):
    env = os.environ.get(f"PACHI_{name.upper()}")
    if env and Path(env).is_file():
        return env
    found = shutil.which(name)
    if found:
        return found
    for p in KNOWN[name]:
        if p.is_file():
            return str(p)
    if name == "codex" and os.environ.get("LOCALAPPDATA"):
        bundled = sorted(Path(os.environ["LOCALAPPDATA"], "OpenAI", "Codex", "bin").glob("*/codex.exe"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if bundled:
            return str(bundled[0])
    return None


def cloud():
    return os.environ.get("CLAUDE_CODE_REMOTE") == "true"


def codex_ready():
    """クラウドで Codex が使えるか数秒で確かめる。使えなければ理由を返す。"""
    if not os.environ.get("OPENAI_API_KEY"):
        return "OPENAI_API_KEY が設定されていない"
    try:
        urllib.request.urlopen("https://api.openai.com/v1/models", timeout=5)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and "proxy" not in str(e.reason).lower():
            return None
        return f"api.openai.com に接続できない（{e.code}）"
    except Exception as e:  # noqa: BLE001
        return f"api.openai.com に接続できない（{e}）"
    return None


def agents(choice=None):
    choice = choice or os.environ.get("PACHI_AGENT", "auto")
    if choice in ("auto", "both"):
        return ["claude"] if cloud() else ["claude", "codex"]
    return [choice]


def run(name, prompt, model=None, effort=None):
    """一回実行して (本文, エラー) を返す。空の一時フォルダで実行し、リポジトリは読ませない。"""
    exe = find_agent(name)
    if not exe:
        return None, f"{name} の CLI が見つからない"
    if name == "codex" and cloud():
        why = codex_ready()
        if why:
            return None, f"codex: {why}"
    if name == "claude":
        cmd = [exe, "-p", "--output-format", "text",
               "--model", model or os.environ.get("PACHI_MODEL", "claude-opus-5-5"),
               "--effort", effort or os.environ.get("PACHI_EFFORT", "high")]
    else:
        cmd = [exe, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral", "-"]
    timeout = int(os.environ.get("PACHI_TIMEOUT", "900"))
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r = subprocess.run(cmd, input=prompt, text=True, encoding="utf-8", capture_output=True,
                               cwd=tmp, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, f"{timeout}秒で終わらなかったので打ち切った"
    if r.returncode != 0:
        return None, f"{name} 失敗（{r.returncode}）：{r.stderr.strip()[:300]}"
    return r.stdout.strip(), None


def run_many(jobs, model=None, effort=None, workers=None):
    """jobs: [(name, prompt, tag)] を並行で回し、[(tag, 本文 or None, エラー)] を返す。
    workers：同時に回す数の上限（既定は全部。数十本を回すときは PACHI_WORKERS か引数で絞る）。"""
    if not jobs:
        return []
    workers = workers or int(os.environ.get("PACHI_WORKERS", "0")) or len(jobs)
    with ThreadPoolExecutor(min(workers, len(jobs))) as pool:
        futs = [pool.submit(run, n, p, model, effort) for n, p, _ in jobs]
        return [(tag, *f.result()) for (_, _, tag), f in zip(jobs, futs)]


def add_model_args(ap):
    ap.add_argument("--agent", default=None, choices=("auto", "both", "claude", "codex"))
    ap.add_argument("--model", default=None, help="既定 PACHI_MODEL または claude-opus-5-5")
    ap.add_argument("--effort", default=None, choices=("low", "medium", "high", "xhigh", "max"))


def notes_dir(ep):
    d = WORK / "episodes" / ep / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write(path, text):
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    return path.relative_to(WORK)


# ---- 点検の出し方（全部の LLM 点検で共通。2026-10-01） ----

OUTPUT_RULES = """出し方の決まり（2026-10-14。research/protocol-v3 §4b）：
- 行ごとに「今の文」「案A」「案B」「推奨」を書く。入れるのはオーナーが選んだものだけなので、文があるほうが選びやすい（自動では入らない）。案は元の文の長さを超えない。説明を足す案は作らない（読者が常識で補うことは書かない）。
- 問題を無理に探さない。ただし当たるものは全部挙げる。
- 出さない指摘：文体の好み、勢い・軽口・誇張・溜めを「説明不足」として削る提案、読者が困っていない設定の追加説明、散文の運び（どの順で何が目に入るか）との違い（書き手の発明の領域）、作者が体験していない現場の細部（決まりごと一枚で書き手が守る。点検は見ない）、読者が常識で補える動作や段取りの省略。"""
