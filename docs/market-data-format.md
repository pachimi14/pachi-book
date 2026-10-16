# ①市場分析 → ②候補生成・③候補選別 に渡すデータの形（2026-10-16。確定）

書き出しは `scripts/market_export.py`。置き場は `research/story-structure-2026-10/export/`。
①の結果は「証拠」として渡す。制作の決まりはここでは決めない。因果が確かめられない所は `limits` に残す。

## ファイル
| ファイル | 単位 | 中身 |
|---|---|---|
| `works.jsonl` | 作品 1 行 | id・題名・組・タグ・公開日・★・話数／階層（章の表と推定ブロック）／市場の系列（★を話数に写した表、PV の写真の日、限界）／9/14→10/1 の伸び／作品ごとのまとめ（work.md のパス）／印を付けた話数 |
| `episodes.jsonl` | 話 1 行 | 下の 8 項目 |
| `fun-types.md` | 一覧 | 面白さの型（名前・定義・例・位置・組の差・本作での使用） |
| `../TRACK.md`・`../STATS.md`（任意） | 表 | 人が読む用の集計。②③は jsonl を読む |

## episodes.jsonl の 1 行
```
position        {n, title, chapter{index,title,range}, windows{w3,w4,w5}, block_inferred{index,range,kind,expectation,reward,state_change,boundary_confidence,boundary_reason}} … 1. 階層
before          {lines[{line, from}], carried_from_previous{lines[...]}}      … 2. 展開前の状態（その話で動いた線の「前の段」と、前の話の after）
event           {type, summary, event, hero_act}                               … 3. 起きた出来事（型：事件／日常・会話／外の反応／回想・設定／山場）
reward          {fun, types(null), hook{type,text}, reaction{present,role}, slice_of_life} … 4. 読者報酬
delivery        {kind(null), shown_by[...], mech{chars, dialog_ratio, board_lines, blank_ratio}} … 5. 実現方法
after           {lines[{line, to, shown_by}], characters[...]}                 … 6. 展開後に変わった状態
relation_to_prior {repeat, callbacks(null)}                                    … 7. 既出展開との関係
market          {observed, pv, pv_rel_ep1, pv_snapshot_date, episode_published_at, stars_at_episode, limits[...]} … 8. 市場実績と限界
pending         [まだ無い項目の名前]
```
線の名前は作品ごとに LLM が付けたもの（「世間の目」「〈人物〉との距離」「力・正体」「敵・謎」「立場・所属」「生活」が多い）。作品をまたいで比べるときは `market_report.py` の `line_kind` と同じ寄せ方を使う。

## 取得済み／未取得（2026-10-16 時点）
| 項目 | 状態 | 備考 |
|---|---|---|
| 1. 階層 | 章・固定窓は取得済み。推定ブロックは market_blocks.py で付ける（進行中） | 章は目次から。固定窓（3・4・5 話）は統計用で機械。物語上のまとまりは印から推定し、境界ごとに信頼度（高／中／低）と根拠を持つ。4 話で切ったものを正式なブロックとは呼ばない（2026-10-16 オーナー） |
| 2. 展開前の状態 | 一部 | 動いた線の「前の段」と、前の話の after。話の頭の全人物の状態は 5 話ごとの state.json にしか無い |
| 3. 起きた出来事 | 取得済み | 型・要約・事件・主人公が自分からすること |
| 4. 読者報酬 | 一行は取得済み。型の番号は未 | fun の一行を面白さの型に当てる追加の分析（LLM 一回。一覧が確定してから） |
| 5. 実現方法 | 一部 | shown_by（表れ方）と reaction.role はある。「場面／反応／描写」の分類は未 |
| 6. 展開後の状態 | 一部 | 動いた線の「今の段」。人物の関係の段は state.json |
| 7. 既出展開との関係 | 一部 | 再演で返事が変わるもの（repeat）だけ。呼び戻し・昇格・反転の関係は未 |
| 8. 市場実績 | 取得済み（限界つき） | ランキングに載った日だけ。PV は一回の写真。因果は未検証 |

## 追加の分析（①の継続。②③を待たない）
1. 残り 20 作の収集と印付け、作品ごとのまとめ（進行中）。
2. 面白さの型の一覧を全作で作り直し、fun の一行に型の番号を付ける（reward.types）。
3. delivery.kind と relation_to_prior.callbacks を付ける二回目の印付け（必要なら。費用は一回目の半分）。
4. 推定ブロック（market_blocks.py）を全作に付ける。制作上のブロック（3〜5 話で短期の期待を作り、報酬を届け、次の状態へ移る単位）は ② の定義。①はその観測だけを渡す。

## 停止（2026-10-16 08:20 UTC。利用枠のため）
- 済み：収集 45 作・3,115 話、印 45 作・3,120 話（全部）、推定ブロック 39 作、作品ごとのまとめ 21 作、★・PV の時系列、export（45 作）、STATS.md。
- 追記（同日）：推定ブロックの残りと、面白さの型の一覧の全作での作り直し（sonnet）は済み。未はまとめの残り 24 作だけ（読み物。export には入らない）。
- 再開（作業フォルダで。LLM を使うのはこの三行だけ。どれも済んだ作品は飛ばす）：
  python3 ../pachi-book/scripts/market_blocks.py --out research/story-structure-2026-10 --workers 1
  python3 ../pachi-book/scripts/market_fun_types.py --out research/story-structure-2026-10 --groups research/story-structure-2026-10/groups.json --extra-own research/story-structure-2026-10/own --corpus <corpus>
  python3 ../pachi-book/scripts/market_analyze.py --corpus <corpus> --out research/story-structure-2026-10 --synth-only --workers 1   # 任意
- そのあと LLM なしで：market_export.py と market_report.py。
