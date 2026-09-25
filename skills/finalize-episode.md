# finalize-episode：採用後の記録

オーナーが「EPxxx の Vn を採用」と言ったあとに行う。作品リポジトリのルートで作業する。

1. `python ../pachi-book/scripts/sync_current.py` を実行し、`episodes/current/` が最新版になっていることを確認する。
2. `episodes/EPxxx/notes/summary.md` を書く：

```
# EPxxx 要約
- 採用版：Vn
- あらすじ（3〜5行）：
- 終了時点の状態：場所・時刻・誰と一緒か・負傷・持ち物
- 新しく確定した事実：（canon へ反映したもの）
- 人物が新しく知ったこと：誰が、何を、どうやって
- 引き：
```

3. `canon/characters.md`：知っていること（取得話付き）、関係の変化、最新状態を更新する。
4. `canon/world.md`、`canon/abilities.md`：新しく確定した事実・能力を初出話付きで足す。
5. `foreshadow.md`：張った・補強・回収を話番号付きで更新する。予定外の伏線を張っていたら追加する。
6. 設定を変えた場合は `changes.md` に記録する。
7. ブロック最後の話なら、`blocks/BLOCK-nn.md` にブロック要約（10行以内）を書く。
8. コミット：`EPxxx Vn を採用、台帳を更新`。push はオーナーの指示に従う。
