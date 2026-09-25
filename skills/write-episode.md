# write-episode：1話を書く

作品リポジトリのルートで行う。成果物は `episodes/EPxxx/memo.md` と新しい版 `episodes/EPxxx/Vn.md`。台帳と current はまだ変えない。

## 1. メモを決める

`memo.md` がなければ作る。オーナーと合意してから本文へ進む。

```
# EPxxx メモ
- 面白さの主役（1行）：
- 流れ（5行前後）：
- 引き（1行）：次に何を確かめたくさせるか
- 使う伏線ID：
- この話で新しく確定する事実：
```

ブロック計画（`blocks/BLOCK-nn.md`）がある場合は、それに沿わせる。

## 2. 読む（これ以外は読まない）

1. `concept.md`、`style.md`、`voices.md`、`preferences.md`
2. 該当ブロック計画と、同ブロックで既に採用された話の `summary.md`
3. 直前話の `current/` 本文（全文）
4. `canon/` のうち、登場人物と使う能力の項だけ
5. `python ../pachi-book/scripts/threads.py .` の出力のうち、この話に関係する伏線

## 3. 書く

- 面白さの主役に紙幅を集める。主役に関係しない説明は削る。
- 冒頭で掴み、話末で引く。1話単独で読まれても成立させる。
- 主人公の声とノリを style.md の見本に合わせる。正しさのために勢いを削らない。
- 新しい版番号で `Vn.md` に保存する（既存の版は上書きしない）。

## 4. 確認

1. `python ../pachi-book/scripts/check_episode.py episodes/EPxxx/Vn.md`。ERRORは直して新しい版にする。
2. `../pachi-book/docs/PROTOCOL.md` 3節の矛盾チェックリストを本文に当てる。欠陥だけを直す。好みの修正はしない。
3. オーナーへの報告は短く：版のパス、字数、主役が伝わるか一言、直した欠陥、気になった点。本文は貼らない。
