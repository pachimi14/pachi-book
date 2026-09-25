# write-episode：1話を書く

作品リポジトリのルートで行う。成果物は `episodes/EPxxx/memo.md` と新しい版 `episodes/EPxxx/Vn.md`。台帳はまだ変えない。版を作るたびに `python ../pachi-book/scripts/sync_current.py` で `episodes/current/` を最新版にする。

## 1. メモを決める

`memo.md` がなければ作る。オーナーと合意してから本文へ進む。

```
# EPxxx メモ
- タイトル：第N話　サブタイトル
- 面白さの主役（1行）：
- 流れ（5行前後）：
- 引き（1行）：次に何を確かめたくさせるか
- 場面の種類：action / streaming / board / everyday のうち該当するもの（なければ なし）
- 使う伏線ID：
- この話で新しく確定する事実：
```

ブロック計画（`blocks/BLOCK-nn.md`）がある場合は、それに沿わせる。

## 2. 読む（これ以外は読まない）

1. `concept.md`、`style.md`、`voices.md`、`preferences.md`
2. `../pachi-book/skills/layout.md` と `../pachi-book/skills/japanese-prose.md`（毎話必ず）と、メモの「場面の種類」に対応する `../pachi-book/skills/lenses/<種類>.md`
3. 該当ブロック計画と、同ブロックで既に採用された話の `summary.md`
4. 直前話の採用版の本文（全文。`summary.md` の「採用版」が指す Vn）
5. `canon/` のうち、登場人物と使う能力の項だけ
6. `python ../pachi-book/scripts/threads.py .` の出力のうち、この話に関係する伏線

## 3. 書く

- 面白さの主役に紙幅を集める。主役に関係しない説明は削る。
- 冒頭で掴み、話末で引く。1話単独で読まれても成立させる。
- 主人公の声とノリを style.md の見本に合わせる。正しさのために勢いを削らない。
- 新しい版番号で `Vn.md` に保存する（既存の版は上書きしない）。保存したら `sync_current.py` を実行する。

## 4. 確認（書き終えたら、オーナーへ報告する前に必ず自動で実行する）

1. `python ../pachi-book/scripts/check_episode.py episodes/EPxxx/Vn.md`。ERRORは直して新しい版にする。
2. `../pachi-book/docs/PROTOCOL.md` 3節の矛盾チェックリストと `japanese-prose.md` を本文に当てる。欠陥だけを直す。地の文の対句否定（チェッカーのERROR）は必ず書き換える。
3. `python ../pachi-book/scripts/review.py EPxxx Vn`。独立した読み手（新しいエージェント実行）がレビューし、`episodes/EPxxx/review-Vn-<agent>.md` に保存される。オーナーに別の会話を開かせない。
4. レビューの `[直すべき]` だけを直し、新しい版 `V(n+1).md` にして、1〜3をもう一度実行する（最大2回まで。それでも残るものはオーナーへ報告する）。`[オーナー判断]` は直さずに報告する。
5. オーナーへの報告は短く：最終版のパス、字数、レビューの総評、直した指摘、オーナー判断の項目。本文は貼らない。
