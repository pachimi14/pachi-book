#!/usr/bin/env python3
"""pachi-book の push の関所。git の pre-push フック（.githooks/pre-push）から呼ぶ。LLM なし。

pachi-book は公開リポジトリなので、push する各コミットの追加行・コミットメッセージ・追加や変更したファイルを調べる。

必ず止める（解除できない）：
- ローカルの絶対パス（ドライブ名から始まるユーザーフォルダ、/Users/名前、/home/名前、Git Bash 形式）
- 本文の写しと 26 字以上一致する文字列。本文の写しは、このリポジトリの各ワークツリーの .local の下の .txt と、
  環境変数 PACHI_BODY_DIRS（区切りは os.pathsep）のフォルダの .txt
一度は必ず止め、オーナーの再確認を求める：
- 仕組みの外のファイル（研究・報告・引き継ぎ・計画などの資料）。仕組みは ENGINE に挙げた場所だけ
- 「」の中が 26 字以上の引用

止めたときは確認の番号を出す。オーナーが改めて許可したら PACHI_PUSH_CONFIRM=<番号> git push … で通る。
番号は止めた内容ごとに乱数で作り、一度通ったら消える。内容が変われば番号も変わる。
"""
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

ZERO = "0" * 40
ENGINE = re.compile(r"^(AGENTS\.md|CLAUDE\.md|README\.md|\.gitignore|\.gitattributes|\.githooks/[^/]+|docs/(PROTOCOL|HISTORY)\.md|"
                    r"scripts/[^/]+\.py|skills/.+\.md|templates/.+)$")
LOCALPATH = re.compile(r"(?:\b[A-Za-z]:(?:\\\\|\\|/)|/[a-z]/|/)(?:Users|home)(?:\\\\|\\|/)[A-Za-z0-9_.-]+", re.I)
QUOTE = re.compile(r"「([^「」\n]{26,})」")
SPLIT = re.compile(r"[。、！？!?「」『』（）()\[\]{}\n\r\t\"\\:,：・…　 ]+")
LONG = 26


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, check=True).stdout.decode("utf-8", "replace")


def bodies():
    dirs = [Path(d) for d in os.environ.get("PACHI_BODY_DIRS", "").split(os.pathsep) if d]
    for line in git("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            for root, ds, fs in os.walk(line[9:]):
                ds[:] = [d for d in ds if d != ".git"]
                if ".local" in Path(root).parts:
                    dirs.append(Path(root))
                    ds[:] = []
    texts = []
    for d in dirs:
        for p in d.rglob("*.txt"):
            try:
                texts.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return "\n".join(texts)


def commits(remote, lines):
    out = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:   # 削除は調べない
            continue
        out += [c for c in git("rev-list", parts[1], "--not", f"--remotes={remote}").split() if c not in out]
    return out


def main():
    sys.stderr.reconfigure(encoding="utf-8")
    remote =sys.argv[1] if len(sys.argv) > 1 else "origin"
    lines = sys.stdin.read().splitlines()
    cs = commits(remote, lines)
    if not cs:
        return 0
    body = bodies()
    hard, soft = [], []
    for c in cs:
        msg = git("log", "-1", "--format=%B", c)
        if LOCALPATH.search(msg):
            hard.append(f"{c[:7]} コミットメッセージ：ローカルの絶対パス")
        for st in git("diff-tree", "-r", "--no-commit-id", "--name-status", "--no-renames", "-m", "--first-parent", "--root", c).splitlines():
            s, _, f = st.partition("\t")
            if s != "D" and not ENGINE.match(f):
                soft.append(f"{c[:7]} {f}：仕組みの外のファイル（資料は公開リポに置かない）")
        f = None
        for ln in git("diff-tree", "-p", "-U0", "--no-color", "--no-renames", "-m", "--first-parent", "--root", c).splitlines():
            if ln.startswith("+++ "):
                f = ln[6:] if ln.startswith("+++ b/") else None
                continue
            if f is None or not ln.startswith("+"):
                continue
            t = ln[1:]
            if LOCALPATH.search(t):
                hard.append(f"{c[:7]} {f}：ローカルの絶対パス")
            if body:
                for seg in SPLIT.split(t.replace("\\n", "\n")):
                    seg = seg.strip()
                    if len(seg) >= LONG and seg in body:
                        hard.append(f"{c[:7]} {f}：本文と {len(seg)} 字一致（{seg[:8]}…）")
                        break
            for m in QUOTE.finditer(t):
                soft.append(f"{c[:7]} {f}：「」の中が {len(m.group(1))} 字の引用（{m.group(1)[:8]}…）")
    hard, soft = sorted(set(hard)), sorted(set(soft))
    if not hard and not soft:
        return 0
    print("\n[push_guard] push を止めた。pachi-book は公開リポジトリ。", file=sys.stderr)
    if not body:
        print("  （本文の写しが見つからないため、本文との一致は調べていない。PACHI_BODY_DIRS で場所を渡せる）", file=sys.stderr)
    if hard:
        print("  必ず止めるもの（確認しても通らない。取り除いてからコミットし直す）：", file=sys.stderr)
        for h in hard[:50]:
            print("   - " + h, file=sys.stderr)
        return 1
    key = hashlib.sha256(("\n".join(soft) + "\n" + "\n".join(cs)).encode("utf-8")).hexdigest()
    store = Path(git("rev-parse", "--git-common-dir").strip()) / "push-guard.json"
    try:
        pending = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pending = {}
    given = os.environ.get("PACHI_PUSH_CONFIRM", "")
    if given and pending.get(key) == given:
        del pending[key]
        store.write_text(json.dumps(pending), encoding="utf-8")
        print("  オーナーの再確認の番号を受けたので通す：", file=sys.stderr)
        for s in soft[:50]:
            print("   - " + s, file=sys.stderr)
        return 0
    pending.setdefault(key, secrets.token_hex(4))
    store.write_text(json.dumps(pending), encoding="utf-8")
    print("  一度は必ず止めるもの：", file=sys.stderr)
    for s in soft[:50]:
        print("   - " + s, file=sys.stderr)
    print("  オーナーにこの一覧を見せて、もう一度確認すること。オーナーや GPT が前に許可していても、この確認は省けない。\n"
          "  資料は非公開の作品リポジトリ（research/ など）に置く。\n"
          f"  オーナーが改めて許可したら：PACHI_PUSH_CONFIRM={pending[key]} git push …", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
