#!/usr/bin/env python3
"""面白さの型の一覧：market_analyze.py の印の「fun（この話で読者が得るもの）」を集め、LLM に型に分けさせる（2026-10-16）。

何のために：骨（3〜5 話のブロックの展開）の候補を作る材料。「この系統の読者が一話で何を得ているか」を、話数の位置つきの型にする。

  python ../pachi-book/scripts/market_fun_types.py --out research/story-structure [--groups research/story-structure/groups.json] [--extra-own research/story-structure/own]

出力：<out>/FUN-TYPES.md（型ごとに：名前・一行の定義・例 3 つ〈作品と話番号〉・出る位置の傾向・伸びた組と止まった組での出方）と、<out>/fun-lines.tsv（材料。作品・組・話番号・型分けの前の一行）。
LLM は一回（既定 claude-opus-5-5 / high）。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402

PROMPT = """あなたは連載 web 小説（カクヨム。現代ファンタジー：配信・TS・魔法少女・推し活・主人公最強）の編集者です。
下に、同じ系統の作品の話ごとの「この話で読者が得るもの」の一行が、作品・組（伸びた／止まった／本作）・話番号つきで並んでいます。

これを「面白さの型」に分けてください。型は 15〜25 個。一つの型は「読者が一話で受け取る報酬」の種類で、出来事の種類（戦闘・配信）ではありません（例：「無自覚の強さが外から知られる」「推しに推し返される」「正体の一歩が漏れる」「外の反応が爆発する」「関係の段が一つ上がる」「掟を破ってでも推しを取る」）。

型ごとに次を書いてください：
- 名前（10 字以内）
- 定義（一行）
- 例を 3 つ（作品名を短く＋話番号＋元の一行を 30 字まで）
- 出る位置の傾向（1〜10 話／11〜30 話／31 話以降 のどこに多いか）
- 伸びた組と止まった組での出方の違い（数が偏っていれば一言。なければ「差なし」）
- 本作（組＝本作）で使われているか（使われていれば話番号、なければ「未使用」）

最後に「本作が使っていない型のうち、本作の前提（魔法少女オタクの男が吸血鬼の美少女になって推しの現場で戦い、推される）に合うもの」を 5 つ挙げ、それぞれ一行で「本作ならどう出るか」を書いてください。

出力は Markdown。前置きは要りません。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--groups", default=None)
    ap.add_argument("--extra-own", default=None, help="本作の印のフォルダ（<out>/own など）")
    ap.add_argument("--corpus", default=None, help="題名を引くための corpus（無ければ id を使う）")
    A.add_model_args(ap)
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    groups = json.loads(Path(a.groups).read_text(encoding="utf-8")) if a.groups and Path(a.groups).is_file() else {}
    corpus = Path(a.corpus).expanduser() if a.corpus else None

    def title_of(wid):
        if corpus and (corpus / wid / "meta.json").is_file():
            return json.loads((corpus / wid / "meta.json").read_text(encoding="utf-8"))["title"][:14]
        return wid[-6:]

    rows = []
    dirs = [d for d in sorted(out.iterdir()) if d.is_dir() and (d / "labels.jsonl").is_file()]
    if a.extra_own:
        dirs += [d for d in sorted(Path(a.extra_own).expanduser().iterdir()) if d.is_dir() and (d / "labels.jsonl").is_file()]
    for d in dirs:
        g = "本作" if a.extra_own and str(d).startswith(str(Path(a.extra_own).expanduser())) else (groups.get(d.name) or {}).get("group", "")
        g = {"魔法少女タグの人気作（追跡の外）": "魔法少女"}.get(g, g or "？")
        for l in d.joinpath("labels.jsonl").read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            r = json.loads(l)
            fun = (r.get("fun") or "").strip().replace("\t", " ")
            if fun and str(r.get("n", "")).isdigit():
                rows.append((title_of(d.name) if g != "本作" else "本作", g, int(r["n"]), fun))
    rows.sort(key=lambda x: (x[0], x[2]))
    (out / "fun-lines.tsv").write_text("作品\t組\t話\t読者が得るもの\n" + "\n".join("\t".join(map(str, r)) for r in rows) + "\n", encoding="utf-8")
    print(f"材料 {len(rows)} 行（{len(dirs)} 作）→ {out / 'fun-lines.tsv'}")
    body = "\n".join(f"{t}｜{g}｜{n}話｜{f}" for t, g, n, f in rows)
    prompt = A.SEP.join([PROMPT, A.section("話ごとの「読者が得るもの」（作品｜組｜話番号｜一行）", body)]) + "\n"
    text, err = A.run("claude", prompt, a.model, a.effort or "high")
    if err:
        sys.exit(err)
    (out / "FUN-TYPES.md").write_text(f"# 面白さの型の一覧（{len(dirs)} 作・{len(rows)} 話の印から。market_fun_types.py）\n\n{text.strip()}\n", encoding="utf-8")
    print(out / "FUN-TYPES.md")


if __name__ == "__main__":
    main()
