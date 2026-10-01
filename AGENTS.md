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

- `docs/PROTOCOL.md`：制作手順（1話・ブロック・章、台帳の規則）
- `skills/write-episode.md`、`skills/revise-episode.md`（直す：指摘・点検の結果・二択の案）、`skills/finalize-episode.md`、`skills/chapter-review.md`：作業ごとの手順
- `skills/japanese-prose.md`：AIの日本語が滑りやすい箇所。対句否定（「Aではない。Bだ」）は地の文で禁止。書いたあとの点検で使う
- `skills/layout.md`：行・空行・場面転換（既定は◇）・表記・括弧の役割の既定値。書く前に読む
- `skills/lenses/`：場面別の点検（action／streaming／board／everyday）。該当する話だけ読む
- `scripts/`：機械チェックと LLM の点検（作品リポジトリのルートで `python ../pachi-book/scripts/...` として実行）
- `templates/work/`：新しい作品リポジトリのひな形（`chapters/STORY.md` が章のあらすじ、`blocks/BLOCK-MEMOS.md` が各話のメモの形）

## コマンド（作品リポジトリのルートで実行）

```bash
# 本文
python ../pachi-book/scripts/check_episode.py episodes/EP001/V1.md   # 機械の点検（作品の tools/work_checks.py も読む）
python ../pachi-book/scripts/check_all.py EP001 V1                   # 機械・筋・声の点検をまとめた対応表 notes/check-V1.md
python ../pachi-book/scripts/check_all.py EP001 V1 --status          # 必須の対応が空の行（0 になるまで埋める）
python ../pachi-book/scripts/check_episode.py episodes/EP001/V2.md --base episodes/EP001/V1.md   # 直しで字数が増えすぎていないか
python ../pachi-book/scripts/check_reader.py EP001 V1                # 初見読者レビュー（採用前の最後に一回）
python ../pachi-book/scripts/propose.py EP001 V1 --issue "指摘" --cand 案A.txt --cand 案B.txt   # 直し案の点検と番号（P…）。オーナーに見せる案は必ずこれを通す
python ../pachi-book/scripts/propose.py EP001 V1 --apply P…-A --to V2   # 選ばれた案を、点検した文のまま新しい版に入れる（選択は好みの材料に記録）
python ../pachi-book/scripts/taste.py build|eval   # オーナーの好みの判定役：材料を作る／伏せた組で当たりを測る
# 方向・あらすじ・メモ
python ../pachi-book/scripts/story_direction.py --target "第3章"   # ストーリーテラー：市場の実績と作品の流れから、次の章の方向の案（chapters/DIRECTION-日付.md）
python ../pachi-book/scripts/check_memo.py chapters/CH-01-STORY.md    # 章のあらすじの監査（通し読み・二択・現場）
python ../pachi-book/scripts/check_memo.py blocks/CH-01-A-memos.md   # 各話のメモの監査
python ../pachi-book/scripts/check_memo.py <採用した話のメモ> <あとのメモ> --after EP001   # 採用後の波及の監査
# 記録・測定
python ../pachi-book/scripts/sync_current.py      # 各話の最新版を episodes/current/ へ
python ../pachi-book/scripts/threads.py .         # 未回収の伏線
python ../pachi-book/scripts/interventions.py     # オーナーの介入の件数（話ごと・分類ごと）
python ../pachi-book/scripts/backtest.py          # 点検ツールの回帰テスト（作品の research/tool-backtest/truth.json）
```

`check_voice.py`（声の点検）は `check_all.py` から呼ばれる。単独でも回せる。

## LLM の点検

点検は `claude -p` または `codex exec` を空の一時フォルダで実行する（リポジトリは読ませず、資料はプロンプトで渡す）。共通部は `scripts/agent.py`。
- モデルは固定する（点検のぶれにモデルの違いを混ぜない）：既定 `claude-opus-5-5`、effort `high`。変えるときは `PACHI_MODEL` / `PACHI_EFFORT` か各スクリプトの `--model` / `--effort`。
- エージェントの選択：`PACHI_AGENT`（auto／claude／codex）。auto はクラウドでは claude だけ、ローカルでは claude と codex。
- CLI が PATH にない場合は `PACHI_CLAUDE` / `PACHI_CODEX` にパスを設定する。打ち切りは `PACHI_TIMEOUT`（既定 900 秒）。
- 作品の資料の場所（あらすじ・台帳・口調カード・オーナーの目・ダメな例・良い例）は、作品ルートの `pachi.json` で上書きできる（既定は `scripts/agent.py` の DEFAULTS）。
- 点検は直す方向だけを言い、直した文は出さない（ツールの直し案がそのまま本文に入り、オーナーに消される一行を生んでいたため。2026-10-01）。
- 対応表は「必須」（事実・筋・詰まる所）と「参考」（文体など）に分ける。参考は書き手が選ぶ。全部に従うと本文が長くなり、オーナーの直しから離れる（2026-10-01 の実験）。
- 面白さは点検で決めない。LLM の判定役はオーナーの版を選べなかった（2026-10-01）。面白さの判断はオーナーがする。

## 改善の測り方

オーナーの指摘で直したコミットには `(owner:A)`〜`(owner:F)` を付け、`interventions.py` で話ごとに数える。作者の判断（A）以外の件数が減っていれば、仕組みが効いている。
点検ツールを直したら `backtest.py` を回し、オーナーの過去の介入を先に拾える件数が減っていないかを見る。
