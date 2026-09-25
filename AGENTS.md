# pachi book（小説制作エンジン）

カクヨム向け連載小説を、面白さを最優先に、100話規模でも破綻させずに作るための仕組み。作品本体は別リポジトリに置く（例：`pachimi14/kyuketsu-mahou-syojo04`）。作品リポジトリは本リポジトリと同じ親フォルダにクローンし、作品側の AGENTS.md から `../pachi-book/` を参照する。バージョン固定や移行手続きは持たない。

本仕組みは Claude Code と Codex のどちらでも使う。特定のエージェント専用の機能（専用スキル形式、サブエージェント、専用コマンド）に依存しない。指示の本体は AGENTS.md に書き、CLAUDE.md は AGENTS.md を読み込むだけにする。

## 原則

1. **面白さが最優先。** 各話は「何が面白いか」を1行で決めてから書く。レビューは面白さを削る方向に使わない。
2. **記録は残し、強制装置は持たない。** 正典・伏線・変更履歴は台帳として残す。検証はチェックリストとスクリプトで行う。
3. **正は作品リポジトリ1か所。** 事実は作品リポジトリの台帳と採用本文（`current/`）だけが正。会話の記憶より台帳を優先する。
4. **採否はオーナーが決める。** AIは候補を出し、オーナーが採用した版だけを `current/` に置く。
5. **読むものは最小限。** 執筆時は手順書が指定する資料だけを読む。過去は要約と台帳で扱う。

## 構成

- `docs/PROTOCOL.md`：制作手順（1話・ブロック・章、台帳の規則）
- `skills/write-episode.md`、`skills/finalize-episode.md`、`skills/chapter-review.md`：作業ごとの手順
- `skills/review-episode.md`：独立レビューの基準（`scripts/review.py` が読む）
- `scripts/`：機械チェック（作品リポジトリのルートで `python ../pachi-book/scripts/...` として実行）
- `templates/work/`：新しい作品リポジトリのひな形

## コマンド（作品リポジトリのルートで実行）

```bash
python ../pachi-book/scripts/check_episode.py episodes/EP001/V1.md
python ../pachi-book/scripts/review.py EP001 V1   # 独立レビュー。--agent claude|codex、既定は使える方
python ../pachi-book/scripts/threads.py .
python ../pachi-book/scripts/promote.py . EP001 V1
```

## レビュー用 CLI

`review.py` は `claude -p` または `codex exec` を空の一時フォルダで実行する。CLI が PATH にない場合は環境変数 `PACHI_CLAUDE` / `PACHI_CODEX` にパスを設定する。既定の選択は `PACHI_REVIEW_AGENT`（auto／claude／codex）。
