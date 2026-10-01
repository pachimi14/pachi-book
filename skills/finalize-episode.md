# finalize-episode：採用後の記録

オーナーが「EPxxx の Vn を採用」と言ったあとに行う。作品リポジトリのルートで作業する。

1. `python ../pachi-book/scripts/sync_current.py` を実行し、`episodes/current/` が最新版になっていることを確認する。
2. `episodes/EPxxx/notes/summary.md` を書く：

```
# EPxxx 要約
- 題名：
- 採用版：Vn
- 版の経緯：V1（日付）：… V2（日付）：…
- あらすじ（3〜5行）：
- 終了時点の状態：場所・時刻・誰と一緒か・負傷・持ち物
- 新しく確定した事実：（canon へ反映したもの）
- 人物が新しく知ったこと：誰が、何を、どうやって
- 引き：
- オーナーの介入：（interventions.py のこの話の行。A〜F の件数）
```

3. `canon/characters.md`：知っていること（取得話付き）、関係の変化、最新状態を更新する。
4. `canon/world.md`、`canon/abilities.md`：新しく確定した事実・能力を初出話付きで足す。
5. `foreshadow.md`：張った・補強・回収を話番号付きで更新する。予定外の伏線を張っていたら追加する。
6. 設定を変えた場合は `changes.md` に記録する。
7. あらすじの台帳（作品の pachi.json の synopsis。既定 `blocks/SYNOPSIS.md`）に、「- 第N話 …」の行で2〜3行足す。点検ツールが前の話までのあらすじとして使う。
8. 波及の監査：`python ../pachi-book/scripts/check_memo.py <章のあらすじ> <この話のメモ> <あとの話のメモ> --after EPxxx`。
   本文でメモから変えた所は、まず章のあらすじに反映し、「あとの話のメモに必要な直し」をメモに入れてから次の話を書く。
9. オーナーの指摘で直したもの（`(owner:…)` のコミット）のうち、次に使える決まりになるものは、作品のダメな例集（pachi.json の bad_examples）に、元の文／直した文／理由の組で足す。理由は「EPxxx の〜」で終わらせず、次に当てはまる形に一般化する。
10. ブロック最後の話なら、ブロック要約（10行以内）を書く。
11. コミット：`EPxxx Vn を採用、台帳を更新`。
