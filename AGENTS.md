# pachi book（小説制作エンジン）

カクヨム向け連載小説を、面白さを最優先に、100話規模でも破綻させずに作るための仕組み。作品本体は別リポジトリに置く（例：`pachimi14/kyuketsu-mahou-syojo04`）。作品リポジトリは本リポジトリと同じ親フォルダにクローンし、作品側の AGENTS.md から `../pachi-book/` を参照する。バージョン固定や移行手続きは持たない。

本仕組みは Claude Code と Codex のどちらでも使う。特定のエージェント専用の機能（専用スキル形式、サブエージェント、専用コマンド）に依存しない。指示の本体は AGENTS.md に書き、CLAUDE.md は AGENTS.md を読み込むだけにする。

## 原則

1. **面白さが最優先。** 各話は「何が面白いか」を1行で決めてから書く。レビューは面白さを削る方向に使わない。
2. **記録は残し、強制装置は持たない。** 正典・伏線・変更履歴は台帳として残す。検証はチェックリストとスクリプトで行う。
3. **正は作品リポジトリ1か所。** 事実は作品リポジトリの台帳と、採用版の本文（`episodes/EPxxx/notes/summary.md` の「採用版」が指す Vn）だけが正。会話の記憶より台帳を優先する。
4. **採否はオーナーが決める。** AIは版（Vn）を作り、オーナーが採用した版を `notes/summary.md` に記録する。`episodes/EPxxx/` 直下は版の本文だけ、資料は `notes/`。
5. **読むものは最小限。** 執筆時は手順書が指定する資料だけを読む。過去は要約と台帳で扱う。
6. **`episodes/current/` は通し読み用。** 各話の最新版を常に置く（採用前も含む）。版を作ったら必ず `sync_current.py` で更新する。

## 構成

- `docs/PROTOCOL.md`：制作プロトコル v3（2026-10-14）。手順と決まりの正本。`skills/` と食い違えばこちらが正
- `docs/HISTORY.md`：経緯（なぜそうなったか）。作業では読まなくてよい
- `skills/write-episode.md`・`revise-episode.md`・`finalize-episode.md`・`chapter-review.md`：段ごとの手の動かし方（付録）
- `skills/japanese-prose.md`：AIの日本語が滑りやすい箇所（対句否定など。機械の点検の根拠）
- `skills/layout.md`：行・空行・場面転換（既定は◇）・表記・括弧の役割の既定値（pack.py が書き手の束に入れる）
- `skills/lenses/`：場面別の点検（action／streaming／board／everyday）。該当する話だけ読む
- `scripts/`：束の生成（pack.py）、機械の点検（check_episode・check_reuse・check_decisions）、LLM の点検（check_logic・check_voice・check_memo・check_reader）、直し案（propose）、記録（sync_current・interventions・threads）。試験：fun_judge・taste・backtest（本線からは呼ばない）
- `templates/work/`：新しい作品リポジトリのひな形（`blocks/RULES.md` 決まりごと一枚、`blocks/BLOCK-MEMOS.md` 各話のメモ、`chapters/STORY.md` 章の散文、`chapters/PITCH.md` 一行の案、`HANDOFF.md` 20 行の現在地）

## コマンド（作品リポジトリのルートで実行）

```bash
# 束（2026-10-14。research/protocol-v3 §3。書き手も点検も、この束に入っているものだけを読む）
python ../pachi-book/scripts/pack.py EP001 --writer        # 書き手の束 → notes/pack-writer.md（RULES・WRITE-BRIEF・同じ型の見本・出る人物のカード・world の節・散文とメモ・直前話・layout）
python ../pachi-book/scripts/pack.py EP001 V1 --check      # 点検の束 → notes/pack-check-V1.md（筋・差分・採用前の点検が読むもの。台帳の記録・LONG-ARCS・OWNER-EYE は入らない）
# 本文
python ../pachi-book/scripts/check_episode.py episodes/EP001/V1.md   # 機械の点検（作品の tools/work_checks.py も読む。地の文の敬称は pachi.json narration_plain で ERROR。2026-10-14）
python ../pachi-book/scripts/check_decisions.py EP001 V1             # 決定との照合（機械。メモの見せ場の台詞・引き・触れないこと・出る人物・知らない言葉の候補・口調の候補・場面の台詞の量。2026-10-14）
python ../pachi-book/scripts/check_reuse.py EP001 V1                 # 再演の点検（機械。前の採用版と同じ言い回し・台帳で封印した材料。check_all が一緒に回す。2026-10-13）
python ../pachi-book/scripts/check_all.py EP001 V1                   # 初稿の点検（機械・再演・決定の照合・筋 1 回〈前の話との矛盾・話の中の破綻を含む〉・声 1 回。まとめ役の LLM なし）。対応表 notes/check-V1.md。行は提案で、入れるのはオーナーが選んだものだけ（2026-10-14）
python ../pachi-book/scripts/check_all.py EP001 V2 --base V1         # 差分の点検（筋・人物・場面の順が変わる直しのときだけ。文脈だけ。notes/diff-V2.md）
python ../pachi-book/scripts/check_all.py EP001 V9 --final           # 採用前の点検（機械・再演・筋 1 回。前の話との矛盾・話の中の破綻だけ。声は回さない。2026-10-14 オーナー）
python ../pachi-book/scripts/check_episode.py episodes/EP001/V2.md --base episodes/EP001/V1.md   # 直しで字数が増えすぎていないか
python ../pachi-book/scripts/check_reader.py EP001 V1                # 初見読者レビュー（採用前の最後に一回）
python ../pachi-book/scripts/check_reader.py EP001 V1 --model claude-sonnet-5-5 --effort medium   # 二人目の読者（別モデル。盲点を変える。2026-10-13）
python ../pachi-book/scripts/propose.py EP001 V1 --issue "指摘" --cand 案A.txt --cand 案B.txt   # 直し案の機械の点検と番号（P…）。LLM の筋の差し込み点検は --logic、好みの判定は --taste（既定は機械だけ。2026-10-14）
python ../pachi-book/scripts/propose.py EP001 V1 --apply P…-A --to V2   # 選ばれた案を、点検した文のまま新しい版に入れる（選択は好みの材料に記録）
python ../pachi-book/scripts/taste.py build|eval   # 試験（本線では呼ばない）：オーナーの好みの判定役
python ../pachi-book/scripts/fun_judge.py pitch <一行の案> | scenes EP001 V1 | draft EP001 V1 V2   # 試験（本線では呼ばない）：面白さの判定役。オーナーの印の前に判定を記録
python ../pachi-book/scripts/fun_judge.py score pitch <一行の案> | score scenes EP001 V1 | score draft EP001 --owner V2   # 印が付いたら当たりを出す
# 方向・あらすじ・メモ
python ../pachi-book/scripts/story_direction.py --target "第3章"   # ストーリーテラー：市場の実績と作品の流れから、次の章の方向の案（chapters/DIRECTION-日付.md）
python ../pachi-book/scripts/check_memo.py chapters/CH-01-STORY.md    # あらすじ・メモの監査（1 回。食い違い・誰が何を知るか・受け渡し・二択だけ。市場の型は --market。2026-10-14）
python ../pachi-book/scripts/check_memo.py blocks/CH-01-A-memos.md   # 各話のメモの監査
python ../pachi-book/scripts/check_memo.py <採用した話のメモ> <あとのメモ> --after EP001   # 採用後の波及の監査
# 記録・測定
python ../pachi-book/scripts/sync_current.py      # 各話の最新版を episodes/current/ へ
python ../pachi-book/scripts/threads.py .         # 未回収の伏線
python ../pachi-book/scripts/interventions.py     # オーナーの介入の件数（話ごと・分類ごと）
python ../pachi-book/scripts/backtest.py          # 点検ツールの回帰テスト（作品の research/tool-backtest/truth.json）
```

`check_voice.py`（声の点検。AIっぽい・書きすぎ・言葉と物・数字・説明の五つだけ、1 回）は初稿の `check_all.py` から呼ばれる（オーナーが読む前に直っていてほしいもの。採用前では回さない）。単独でも回せる。

## LLM の点検

点検は `claude -p` または `codex exec` を空の一時フォルダで実行する（リポジトリは読ませず、資料はプロンプトで渡す）。共通部は `scripts/agent.py`。
- モデルは固定する（点検のぶれにモデルの違いを混ぜない）：既定 `claude-opus-5-5`、effort `high`。変えるときは `PACHI_MODEL` / `PACHI_EFFORT` か各スクリプトの `--model` / `--effort`。
- エージェントの選択：`PACHI_AGENT`（auto／claude／codex）。auto はクラウドでは claude だけ、ローカルでは claude と codex。
- CLI が PATH にない場合は `PACHI_CLAUDE` / `PACHI_CODEX` にパスを設定する。打ち切りは `PACHI_TIMEOUT`（既定 900 秒）。
- 作品の資料の場所（あらすじ・台帳・書き手の一枚 write_brief・材料の台帳 motifs・人物名 names・決まりごと一枚 rules）は、作品ルートの `pachi.json` で上書きできる（既定は `scripts/agent.py` の DEFAULTS）。
- 点検に渡す台帳は、決まりごと一枚（rules）と、人物台帳の「### カード」の節（出る人物の分だけ。メモの「- 出る人物：」）と、記録の「- 知っていること」（前の話との矛盾を見るため。書き手には渡さない）と、メモの「- world：」が指す world の節だけ（`agent.canon_context(ep)`。2026-10-14）。台帳の記録のそれ以外・LONG-ARCS は渡さない（73k 字の中で一行の決まりが拾えなかった）。作者の決定は pachi.json の `chapter_plans` に挙げたファイルだけから取る（`agent.plan_files`。glob で旧メモを拾っていた）。
- 一話の LLM の点検は六回まで：メモ 1・初稿の筋 1＋声 1・採用前の筋 1・読者 1（二人目は要るときだけ）・波及 1。差分の点検は場面の順が変わったときだけ。まとめ役・判定役は置かない。
- 点検は間違いを見つける係で、面白さは見ない（面白さは一行の案と場面の ○△× でオーナーが選ぶ）。拾えない種類（現場の細部・足りない所）は点検で追わない。「くどい」「前の話と同じ反応」は機械 `check_reuse.py` が見る。
- 対応表の先頭は「オーナーへの報告」：全部の指摘を重要度（高・中・低）順に並べ、書き手が行ごとに「直す：案Aで／直す：別の形で／そのままでよい：理由」を埋めてチャットに出す。判断は、本文で今何が成立しているか、補足で何を失うかを確かめてから書く。入れるのはオーナーが選んだものだけ。
- 対応表は「必須」（筋：事実・誰が何を知る・話し手・立場・指示語・人の動き・決定。機械：ERROR・NG・再演・封印）と「参考」（筋：読者が知らない言葉。声：AIっぽい・書きすぎ・言葉と物・数字・説明。機械の WARN・INFO）に分ける。段落の最後の具体の評価の一文は語り手の声なので挙げない。
- 読者レビューは任意で、書き手と別のモデルで二人目を回せる（同じモデルは盲点が同じ）。

## 改善の測り方

オーナーの指摘で直したコミットには `(owner:A)`〜`(owner:F)` を付け、`interventions.py` で話ごとに数える。作者の判断（A）以外の件数が減っていれば、仕組みが効いている。
点検ツールを直したら `backtest.py` を回し、オーナーの過去の介入を先に拾える件数が減っていないかを見る。
