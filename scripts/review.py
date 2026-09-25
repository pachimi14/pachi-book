#!/usr/bin/env python3
"""Independent review of one episode by a fresh, non-interactive agent run.

Usage (from the work repository root):
    python ../pachi-book/scripts/review.py EP002 V1 [--agent auto|claude|codex]

The reviewer gets only: the rubric (skills/review-episode.md), the episode text,
the previous episode's summary.md, and canon sections for characters that
appear in the text. It runs in an empty temporary directory, so it cannot read
the repository or the writer's conversation. Output: episodes/EPxxx/review-Vn-<agent>.md
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ENGINE = Path(__file__).resolve().parent.parent
KNOWN = {
    "claude": [Path.home() / ".local/bin/claude.exe", Path.home() / ".local/bin/claude"],
    "codex": [],
}


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
        # Codex desktop bundles the CLI under a version-hashed folder; take the newest.
        bundled = sorted(Path(os.environ["LOCALAPPDATA"], "OpenAI", "Codex", "bin").glob("*/codex.exe"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if bundled:
            return str(bundled[0])
    return None


def canon_sections(path, text):
    if not path.is_file():
        return ""
    body = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^(?=## )", body)
    keep = []
    for part in parts:
        m = re.match(r"## (.+)", part)
        if not m:
            continue
        name = re.sub(r"[（(].*", "", m.group(1)).strip()
        if name == "主人公" or (name and name in text):
            keep.append(part.strip())
    return "\n\n".join(keep)


def build_prompt(work, ep, ver):
    ep_dir = work / "episodes" / ep
    text = (ep_dir / f"{ver}.md").read_text(encoding="utf-8")
    num = int(ep[2:])
    prev = work / "episodes" / f"EP{num - 1:03d}" / "summary.md"
    prev_summary = prev.read_text(encoding="utf-8") if prev.is_file() else "（なし：第1話、または前話が未採用）"
    canon = "\n\n".join(filter(None, [canon_sections(work / "canon" / "characters.md", text),
                                      canon_sections(work / "canon" / "abilities.md", text)]))
    rubric = (ENGINE / "skills" / "review-episode.md").read_text(encoding="utf-8")
    return (f"{rubric}\n\n---\n\n# 直前話の要約\n\n{prev_summary}\n\n# 登場人物の正典\n\n{canon or '（なし）'}\n\n"
            f"# レビュー対象：{ep} {ver}\n\n{text}\n\n---\n\n上の基準の出力形式だけで回答してください。ツールは使わないでください。")


def run(agent, exe, prompt):
    with tempfile.TemporaryDirectory() as tmp:
        if agent == "claude":
            cmd = [exe, "-p", "--output-format", "text"]
        else:
            cmd = [exe, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral", "-"]
        r = subprocess.run(cmd, input=prompt, text=True, encoding="utf-8", capture_output=True, cwd=tmp, timeout=900)
    if r.returncode != 0:
        sys.exit(f"{agent} failed ({r.returncode}): {r.stderr.strip()[:500]}")
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("version")
    ap.add_argument("--agent", default=os.environ.get("PACHI_REVIEW_AGENT", "auto"), choices=("auto", "claude", "codex"))
    ap.add_argument("--work", default=".", type=Path)
    a = ap.parse_args()

    order = ["claude", "codex"] if a.agent == "auto" else [a.agent]
    agent = exe = None
    for name in order:
        exe = find_agent(name)
        if exe:
            agent = name
            break
    if not agent:
        sys.exit("レビュー用の CLI が見つからない（claude または codex）。PACHI_CLAUDE / PACHI_CODEX でパスを指定できる。")

    prompt = build_prompt(a.work, a.episode, a.version)
    result = run(agent, exe, prompt)
    out = a.work / "episodes" / a.episode / f"review-{a.version}-{agent}.md"
    out.write_text(f"# {a.episode} {a.version} 独立レビュー（{agent}）\n\n{result}\n", encoding="utf-8", newline="\n")
    must = len(re.findall(r"\[直すべき\]", result))
    owner = len(re.findall(r"\[オーナー判断\]", result))
    print(f"{out}  reviewer={agent}  直すべき {must} / オーナー判断 {owner}")


if __name__ == "__main__":
    main()
