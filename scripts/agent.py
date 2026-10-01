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
    "fixed_numbers": [],
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


def section(title, body):
    return f"# {title}\n\n{body or '（なし）'}"


def canon_context():
    return SEP.join([section("台帳：登場人物", doc("characters")), section("台帳：世界", doc("world")),
                     section("台帳：能力", doc("abilities")), section("長期の骨格（作者用）", doc("long_arcs")),
                     section("口調カード", doc("voice_cards"))])


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


def run_many(jobs, model=None, effort=None):
    """jobs: [(name, prompt, tag)] を並行で回し、[(tag, 本文 or None, エラー)] を返す。"""
    if not jobs:
        return []
    with ThreadPoolExecutor(len(jobs)) as pool:
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

OUTPUT_RULES = """出し方の決まり：
- 直した文は書かない。「どこが・何がおかしいか」と「直す方向」（一言）だけを書く。直し方の文を書くと、そのまま本文に入って新しい直しを生むため（2026-10-01 の検証）。
- 問題を無理に探さない。ただし当たるものは全部挙げる。
- 出さない指摘：文体の好み、勢い・軽口・誇張・溜めを「説明不足」として削る提案、読者が困っていない設定の追加説明。
- 現場の細部（行事の段取り・係の動き・専門用語）に説明を足す提案はしない。気になるなら「現場の細部」として挙げる（作者が体験していない場の細部は、削るのが基本の直し方）。"""
