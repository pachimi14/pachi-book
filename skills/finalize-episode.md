# finalize-episode：採用後の記録（付録。正本は docs/PROTOCOL.md §3-10）

オーナーが「EPxxx の Vn を採用」と言ったあと、クラウドのセッションで行う。

1. `python ../pachi-book/scripts/sync_current.py`。採用前の版の仮の印「◇場面N」を外し、本物の ◇ だけ残す（どこを本物にするかはメモ）。題名を 1 行目に。
2. `episodes/EPxxx/notes/summary.md`：
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
   - 点検の回数（LLM）とオーナーが全文を読んだ回数、版の数
   - オーナーの介入：（interventions.py のこの話の行）
   ```
3. `canon/characters.md`：出る人物の「### カード」を書き直す（呼び方・口調／今の距離と反応／使う能力）。「### 記録」の「知っていること」に取得話付きで足す。今回使った反応・仕草は blocks/MOTIFS.md の 3（反応・仕草）へ（検索語も）。
4. `canon/world.md`・`canon/abilities.md`：新しく確定した事実・能力を初出話付きで。
5. `foreshadow.md`：張った・補強・回収を話番号付きで。設定を変えたら `changes.md`。
6. `blocks/SYNOPSIS.md` に「- 第N話 …」で 2〜3 行。
7. `blocks/MOTIFS.md`：使った材料の「使った話」「働き」「状態」。research/seeds の「使った話」。
8. `HANDOFF.md` を上書き（20 行以内）：今どこ／次にすること／写していない決定（この採用で全部写したなら空）／次の段で使う束の場所。
9. 波及の確認：`python ../pachi-book/scripts/check_memo.py <章の散文> <この話のメモ> <あとの話のメモ> --after EPxxx`（1 回）。食い違いと受け渡しの抜けだけを散文に反映し、メモは散文から直す。回収の提案は入れない。
10. コミット：`EPxxx Vn を採用、台帳を更新`。push。
