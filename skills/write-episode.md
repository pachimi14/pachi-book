# write-episode：1話を書く（付録。手順の正本は docs/PROTOCOL.md §2〜3）

作品リポジトリのルートで行う。ここには段ごとの手の動かし方だけを書く。経緯は docs/HISTORY.md。

## 1. 一行の案（クラウド）
- `chapters/notes/PITCH-EPxxx-日付.md`（templates/work/chapters/PITCH.md の形）に 8〜10 本。一行をチャットに並べ、オーナーの印（○△×）を表に写してコミット。
- 主人公が自分からすることが行動になっているか、一話に一本（引きに一本足してよい）か、を出す前に自分で確かめる。

## 2. 散文のあらすじ（クラウド）
- 章の背骨のファイル（pachi.json chapter_plans に挙げたもの）の「各話の散文」に 400〜600 字。二択は「A／B・推奨・どちらを選ぶと何が変わるか」の形でチャットに。
- 決まったら `python ../pachi-book/scripts/check_memo.py <散文のファイル>`（1 回）。食い違いは散文に反映し、二択はオーナーに。

## 3. メモ（クラウド）
- blocks/*-memos.md に templates/work/blocks/BLOCK-MEMOS.md の形で。機械の欄（視点・型・出る人物・world・検索語（触れない）・検索語（使わない））を忘れない。
- `python ../pachi-book/scripts/check_memo.py <散文> <メモ>`（1 回）。
- `python ../pachi-book/scripts/pack.py EPxxx --writer` で書き手の束を作ってコミット（ローカルの書き手はこれだけを読む）。

## 4. 初稿二本（ローカル。A claude・B codex）
- notes/pack-writer.md だけを読み、全文を V1・V2 に。各場面に発明を一つ。「◇場面N」の仮の印。書いたら `sync_current.py`、commit、push。

## 5. 初稿の点検（クラウド）
- 二本に `check_episode.py` と `check_reuse.py` と `check_decisions.py`（機械）。ERROR・NG・再演・封印は直す。
- 推奨の一本に `python ../pachi-book/scripts/check_all.py EPxxx Vn`（機械＋筋＋声）。notes/check-Vn.md の先頭「オーナーへの報告」に、行ごとの「書き手の判断」を埋めてチャットに貼る（本文の全文は貼らない）。見せ場の抜粋 3 か所・引き・二択・もう一本との違いも添える。
- オーナーが番号で選んだものだけを次の版に入れる（`propose.py` で番号を付けて `--apply`）。

## 6. 場面の印（オーナー）→ 直し（クラウド）
- オーナーの ○△× を notes/owner-marks-Vn.md に写す。× は差し替えか角度指定の書き直し（一場面一回）。△ は一言に沿って。
- 場面の順・配置・誰が何を知るかが変わったときだけ `check_all.py EPxxx V(n+1) --base Vn`。出た行は直さずオーナーに戻す。

## 7. 磨きとならし（クラウド）
- 全部 ○ になってから。磨き一度、ならし一回（読点・改行・段落の結合だけ）。機械の［警報］が鳴らないこと。オーナーの文は触らない。

## 8. 採用前（クラウド → ローカル）
- `check_all.py EPxxx Vn --final`（機械＋筋）。報告を重要度順にチャットへ。選ばれたものだけ入れる。
- 初見読者はオーナーが要ると言ったときだけ、ローカルで `check_reader.py EPxxx Vn`（claude opus。二人目は codex）。結果は notes/reader-Vn-*.md。読者の反応として読み、直すものだけオーナーが選ぶ。
- 採用：`skills/finalize-episode.md`。
