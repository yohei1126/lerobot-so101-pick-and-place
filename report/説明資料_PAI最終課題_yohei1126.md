<!-- markdownlint-disable MD013 MD024 MD060 -->

# Physical AI 応用編1 最終課題 説明資料

**OmniCampusアカウント名:** `yohei1126`

> 注意: 氏名・所属・メールアドレスなどの個人情報は記載しないこと。  
> 本稿は提出用 PDF（DoD ⑤）向けの**初稿**である。所有者が編集し、未確定数値・図表は TODO を埋めたうえで `./scripts/build_report_pdf.sh yohei1126` により PDF 化する。

## 0. 本稿の位置づけと出典方針

- 数値はリポジトリ内の文書・評価ログ、または GitHub の PR / Issue コメントに根拠があるものだけを達成値として書く。
- 根拠を再確認できなかった項目は **TODO** とし、推測で埋めない。
- 主要出典:
  - Phase 1.5 DoD: [Issue #23](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/issues/23)
  - post50 ACT 評価表: [PR #34 コメント](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/pull/34#issuecomment-6233795103)（2026-10-17）
  - 評価メトリクスへの初期箱姿勢・seed 記録: [PR #52](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/pull/52) / [Issue #51](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/issues/51)
  - 実機縮退方針: [`docs/plan_b.md`](../docs/plan_b.md)
  - 実機準備: [`docs/hardware.md`](../docs/hardware.md)

---

## 1. 課題設定と社会的背景（創造性）／課題と目標（DoD）

### 1.1 背景と課題

造船・海事・港湾現場では、熟練作業者の不足と危険空間での反復作業への対応が急務である。コンテナや部品パレットの整列は視覚的には単純でも、位置・姿勢の許容誤差が厳しく、失敗時の再作業コストが大きい。本課題では「把持して枠へ精密に整列する」操作を卓上直方体モックに縮約し、データ収集・学習・評価の RobOps ループを安全に再現する。

### 1.2 タスク定義

| 項目 | 内容 |
| --- | --- |
| 対象物 | 小型直方体箱（机上モック。現場のコンテナ／部品パレットに相当） |
| 目標 | 机上の目標枠（パッド）へ平面位置およびヨー角を整合させて配置 |
| 成功条件（評価 API） | 平面位置誤差 ≤ 25 mm、ヨー角誤差 ≤ 15 deg（[`docs/evaluation.md`](../docs/evaluation.md)、[`docs/hardware.md`](../docs/hardware.md)） |
| 観測 | Top / Wrist 2 眼カメラ（640×480、30 fps）および関節 6 DoF |
| 制御 | ACT（chunk_size=30）による関節位置指令。比較のため Temporal Ensembling（TE）も評価 |

### 1.3 Phase 1.5 完了基準（DoD）

出典: [Issue #23](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/issues/23)。

| # | 項目 | 本稿時点の判定 | 根拠 |
| --- | --- | --- | --- |
| ① | 教示の自動収集（50〜100 エピソードの LeRobotDataset） | 達成（post50 パイプラインで収集・学習済み） | PR #34 post50 結果コメント（チェックポイント群の存在） |
| ② | MPS 上での本格学習 | 達成 | 同上（`checkpoints/sim_act_post50`） |
| ③ | Temporal Ensembling 実装 | 達成 | コードおよび TE 評価セルの存在 |
| ④ | 定量ベンチマーク（整列 ≥ 85%、平均位置誤差 < 25 mm） | **TE モードで達成**（下記） | post50: `best_model_te` × TE |
| ⑤ | 提出用 PDF | **未完了（本稿が初稿）** | TODO: 所有者編集後に PDF ビルド |

**DoD ④ の達成モード（本稿の主張）:**  
post50 の `best_model_te` を Temporal Ensembling（`n_action_steps=1`）で評価したとき、整列成功率 1.000、平均位置誤差 18.1 mm（中央値 19.0 mm）であり、DoD の整列率・位置誤差を満たす（PR #34）。  
なお初期のベンチマークスクリプト／文書では達成判定を chunk30（`n_action_steps=30`）側に置いていた（[`scripts/run_phase15_benchmark.sh`](../scripts/run_phase15_benchmark.sh)、[`docs/results/README.md`](../docs/results/README.md)）。本稿では実測上 DoD を満たす実行モードとして **TE を主達成**と明記する。chunk30 は同ポリシーでは未達である（第 5 章）。

把持成功率の参考閾値（≥ 90%）は [`docs/results/README.md`](../docs/results/README.md) に記載がある。post50 の TE（`best_model_te`）では把持率 1.000 である。

### 1.4 公式サンプルに対する独自性

(1) `configs/contract.yaml` による契約一元管理、(2) rosbag2→LeRobot 変換と品質バリデータ、(3) GitHub Actions CI、(4) ROS 2 推論モックと Rerun、(5) MuJoCo 閉ループ評価、を単一リポジトリに統合した。港湾整列を卓上モック化し、品質検証から再学習までの RobOps を構造化した点が差分である。

---

## 2. システムアーキテクチャ（技術力）／環境

### 2.1 シミュレーション環境

| 項目 | 内容 |
| --- | --- |
| 物理エンジン | MuJoCo（`PickAlignSimEnv`、資産 `so101_tabletop.xml`） |
| アーム | SO-101 相当 6 DoF（`lerobot_type: so101_follower`） |
| 学習フレームワーク | LeRobot + ACT（ResNet18、chunk_size=30） |
| 本学習デバイス | Mac Apple Silicon（MPS） |
| 契約 SSOT | [`configs/contract.yaml`](../configs/contract.yaml)（画像 640×480、関節名、chunk_size） |

### 2.2 ソフトウェアスタック

| 実行層 | 役割 |
| --- | --- |
| Docker (ROS 2 Humble) | 推論モック、rosbag、Rerun、バリデータ結合試験 |
| Host venv (`port_pick_align`) | 教示収集、ACT 訓練、変換・検証、MuJoCo 評価 |
| 無人パイプライン | `scripts/run_pipeline.sh`（収集→学習→全 ckpt×chunk30/TE 評価） |

```text
[MuJoCo scripted expert] ──collect──▶ LeRobotDataset
        │
        ▼
   ACT train (MPS) ──▶ best_model.pt / best_model_te.pt
        │
        ├─▶ chunk30 評価 (n_action_steps=30)
        └─▶ TE 評価 (temporal ensembling, n_action_steps=1)
                 └──▶ metrics.json / summary.md
```

### 2.3 実機ハードウェア（準備状況）

設計対象は SO-ARM101（Feetech STS3215）＋ Top/Wrist カメラである。配置・機材一覧は [`docs/hardware.md`](../docs/hardware.md)。

| 項目 | 状態 | 出典 |
| --- | --- | --- |
| SO-101 Leader / Follower | キャリブレーション済み、leader→follower テレオペ動作 | TODO: オーナー報告（2026-10-17）。リポジトリ内のログ／Issue への固定リンクは未整備 |
| 制御周期 | 約 60 Hz | TODO: 同上（測定ログの添付待ち） |
| カメラ | セットアップ中（C920 上カメラ、手首カメラ） | [`docs/hardware.md`](../docs/hardware.md) の購入済み機材・配置ガイド |
| 次工程 | `lerobot-record` で実デモ収集 → 学習 → `lerobot-rollout` 評価 | TODO: 実デモ本数・成功率は未計測 |

単位系の注意（sim ↔ 実機）:

- 本リポジトリの sim／契約の関節は**ラジアン**（`contract.yaml` の `joint_limits`）。
- 実機 LeRobot SO-101 は関節が**度**、グリッパが **0–100** スケールであることが多い。実データ学習前にスケール変換を揃える必要がある（TODO: 実機ログで最終確認し、変換手順を 1 節に固定する）。

---

## 3. データパイプラインと品質管理（RobOps / 技術力）／手法（データ）

### 3.1 収集

1. MuJoCo 上で `ScriptedPickAlignPolicy` をロールアウトし、画像＋関節目標を LeRobotDataset として保存（`scripts/collect_sim_dataset.py`）。
2. 初期箱の平面位置・ヨーをランダム化し、整列成功エピソードのみ採録する（[`docs/dataset.md`](../docs/dataset.md)）。
3. `validate_episode` により同期ずれ・フレーム間隔・関節可動域・静止を検査する。
4. 教示軌道は反復改善済み（運搬中ヨー合わせ、パッド近傍の閉じた approach+place、開いた静止解放など。Issue #39/#41/#45 系）。

post50 ランは `scripts/run_pipeline.sh` 経由の収集・学習・評価である（チェックポイントディレクトリ名 `sim_act_post50`、PR #34）。

### 3.2 品質ゲート

| 検証項目 | 閾値（契約） |
| --- | --- |
| 時刻同期 | 33 ms 超を検出 |
| フレーム欠落 | 50 ms 超間隔を検出 |
| スキーマ | `contract.yaml` との一致 |
| 公式収集フラグ | 50〜100 epi、640×480、260 step 等（[`docs/dataset.md`](../docs/dataset.md)） |

---

## 4. モデル選定と学習（技術力）／手法（ACT・TE）

### 4.1 ACT 設定

| 項目 | 設定 |
| --- | --- |
| モデル | ACT（Action Chunking with Transformers） |
| 視覚バックボーン | ResNet18 |
| chunk_size | 30 |
| アクション次元 | 6（関節＋グリッパ） |
| 学習プリセット | `--preset sim`（閉ループ整列で `best_model.pt` を選択、TE 最良を `best_model_te.pt` に別保存） |
| デバイス | MPS（Mac M4 系） |
| 早期終了 | `--min-steps`（既定 3000）以降、`(整列率, −平均位置誤差)` の辞書式進捗（PR #50） |

### 4.2 Temporal Ensembling

閉ループでは毎ステップ最新チャンクを出し、過去予測との指数重み平均で指令を平滑化する（係数の既定は 0.01、評価時は `n_action_steps=1`）。チャンク先頭だけを採用する実行と比べ、重複予測の入れ替わりを抑え、運搬〜解放の連続性を保ちやすい。

### 4.3 評価プロトコルの監査性（PR #52）

post50 で多くの失敗 ckpt が同一誤差（平均 205.4 mm 等）を示したため、ランダム化不良が疑われた。Issue #51 によると、seed=1000・50 エピソードの検証でランダム化自体は有効であり、同一数値は把持失敗時の「初期位置→パッド距離」が同一シード列で一致したためと説明されている。

これを踏まえ PR #52 では、エピソードごとに `initial_box_xy` / `initial_box_yaw` / `seed`（および最終ヨー関連）を `metrics.json` に記録するようにした。以降の再検証では初期分布のばらつきをログから直接確認できる。

### 4.4 学習曲線・損失

- TODO（DoD ④ 補助）: `checkpoints/sim_act_post50/training_metrics.json` から train_loss / val_l1 / 閉ループ指標の最終値と曲線図を転記する。
- 本稿では PR #34 の評価表を主結果とし、損失の数値はファイル突合後に追記する。

---

## 5. 定量評価と動作検証（実用性）／実験と結果

> 本節の ACT 数値は **Plan B（MuJoCo）** 上の結果である。実機計測は未完了。

### 5.1 post50: TE 対 chunk30（主結果）

出典: [PR #34 の post50 パイプライン結果コメント](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/pull/34#issuecomment-6233795103)。  
条件: チェックポイントディレクトリ `checkpoints/sim_act_post50`、セルあたり評価 20 エピソード。chunk30 は `n_action_steps=30`（TE オフ）、TE は temporal ensembling オン（`n_action_steps=1`）。

| Checkpoint | Mode | Align rate | Mean pos err (mm) | Median pos err (mm) | Grasp rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `best_model` | chunk30 | 0.000 | 39.2 | 39.1 | 1.000 |
| `best_model` | TE | 0.000 | 51.0 | 51.0 | 1.000 |
| `best_model_te` | chunk30 | 0.000 | 205.4 | 208.8 | 0.000 |
| **`best_model_te`** | **TE** | **1.000** | **18.1** | **19.0** | **1.000** |

**読み取り:**

- DoD を満たす組み合わせは **`best_model_te` × TE**（整列 100%、平均 18.1 mm < 25 mm）。
- 同じ `best_model` の chunk30 は整列 0、平均 39.2 mm で DoD 未達（依頼文の「chunk モード比較」に対応）。
- 選択メトリクス（chunk 向け `best_model` と TE 向け `best_model_te`）と実行モードを揃えないと、成績が大きく崩れる。

### 5.2 DoD 判定表（post50・TE）

| 指標 | DoD | `best_model_te` × TE | 判定 |
| --- | --- | ---: | --- |
| 整列成功率 | ≥ 85% | 100% (1.000) | 達成 |
| 平均位置誤差 | < 25 mm | 18.1 mm | 達成 |
| 把持成功率（参考） | ≥ 90%（docs/results） | 100% | 達成 |

### 5.3 独立再検証（seed=1000、50 エピソード）

| 項目 | 値 | 出典確認 |
| --- | --- | --- |
| プロトコル | seed=1000、50 エピソード | Issue #51（ランダム化有効性の検証として言及） |
| TE 整列成功率 | TODO: 100% と依頼文にあるが、PR/評価 JSON への固定リンク未確認 | TODO |
| TE 平均位置誤差 | TODO: 18.28 mm（依頼文） | TODO |
| 位置誤差レンジ | TODO: 14.3–20.0 mm（依頼文） | TODO |

所有者がローカルの `metrics.json` / `summary.md` を `docs/results/` へ納品したら、上表の TODO を実測値に置換する。

### 5.4 scripted オラクル（参考ベースライン）

出典: [`docs/results/scripted_random_20.json`](../docs/results/scripted_random_20.json)。  
20 エピソード・初期配置ランダム・CPU。整列 1.0、平均位置誤差 0.0 mm、`thresholds_met=true`。ACT の結果ではない。

### 5.5 公式ベンチマーク成果物（DoD ④ のリポジトリ記録）

| 成果物 | 状態 |
| --- | --- |
| `docs/results/eval_sim_act.pending.json` | まだ pending（本学習結果の Git 管理コピーが未投入） |
| `outputs/eval_sim_act*/metrics.json` | Git 管理外。post50 の生データはローカル `eval/<ckpt>/<mode>/metrics.json`（PR #34） |
| Phase 1.5 公式スクリプト再走 | TODO: `DEVICE=mps EPISODES=20 ./scripts/run_phase15_benchmark.sh checkpoints/sim_act_post50/best_model_te.pt` の結果を `docs/results/` にコミット |

---

## 6. 考察・失敗分析と改善ループ

### 6.1 なぜ TE が chunk 実行を上回るか（post50）

1. **実行ホライズンと教示の整合:** TE は毎ステップ再計画＋平滑化により、接近〜解放のタイミングずれを吸収しやすい。chunk30 は 30 歩分を固定実行するため、開指令タイミングや運搬途中の視覚誤差が残るとパッド到達前に停滞しやすい。
2. **チェックポイント選択の分離:** `best_model_te` は TE 閉ループで選ばれた重みである。これを chunk30 で再生すると整列 0・誤差 ~205 mm まで崩れる（PR #34 表）。逆に chunk 向け `best_model` を TE で回しても post50 では整列 0 である。**学習時の選択メトリクスと評価時の実行モードを一致させることが必須**である。
3. **過去のスナップ偽陽性（PR #46）:** 解放時に箱をパッド中心へテレポートしていた時期があり、TE「整列 100%・誤差 0.0 mm」が過大評価だった。スナップ廃止後の post50 では平均 18.1 mm と、閾値内だが非ゼロの現実的な誤差になっている。

### 6.2 主な失敗モードと対策履歴

| 失敗モード | 対策 | 関連 |
| --- | --- | --- |
| 把持遷移の学習不足 | グリッパ損失重み・遷移オーバーサンプル | PR #33/#34 |
| 運搬不足・早期解放 | 教示の approach+place 延長、パッド近傍ゲート | Issue #39/#41/#45 |
| TE 誤差 0 の偽陽性 | 解放スナップ廃止、最終箱 XY ログ | PR #46 |
| 早期終了が整列 0% で停滞 | 辞書式進捗と `--min-steps` | PR #50 |
| 同一誤差の見え方 | 初期姿勢・seed を per-episode 記録 | PR #52 / Issue #51 |

### 6.3 限界

- 達成はシミュレーションかつ TE モードに依存。chunk30 単体では DoD 未達。
- 実機分布（照明、カメラ外部、摩擦、単位系）へのギャップは未評価。
- post50 の 20 エピソード表は PR コメント根拠であり、`docs/results/` への公式 JSON コミットは TODO。
- ヨー角の平均絶対誤差など、表に無い集計は TODO（metrics から追記）。

---

## 7. 実現場への展開構想（実用性）／実機への展開

### 7.1 現状（2026-10-17 時点のオーナー報告・要裏付け）

| 項目 | 内容 | 確認 |
| --- | --- | --- |
| アーム | 実 SO-101 をキャリブレーション済み、leader→follower テレオペ可 | TODO: 動画／ログを成果物に添付 |
| 周期 | 約 60 Hz | TODO |
| カメラ | セットアップ中（配置は hardware.md のガイドに準拠予定） | 進行中 |
| 次 | 実デモを `lerobot-record` → 学習 → `lerobot-rollout` | 未着手 |

### 7.2 Plan B（シミュレーション縮退）

実機が締切までに安定しない場合は [`docs/plan_b.md`](../docs/plan_b.md) に従い、MuJoCo 評価動画と RobOps（変換・バリデータ・CI）の検証性で提出要件を満たす。本稿第 5 章の post50 TE 結果がその中核エビデンスである。切り替え判定日の目安は 2026-10-23（plan_b.md）。

### 7.3 産業展開の構想

防塵・防滴、動揺追従、通信途絶時フェールセーフ、安全規格適合が現場展開の論点である。本リポジトリの価値は、現場データ取得前に契約・品質ゲート・再現可能な評価を規格化した点にある。

---

## 8. 成果発表動画の構成設計（表現力）

### 8.1 提出仕様

| 項目 | 要件 |
| --- | --- |
| タイトル | `PAI最終課題_yohei1126` |
| 長さ | 1〜3 分 |
| 公開 | 限定公開以上 |

### 8.2 タイムライン案

| 時間 | 内容 |
| --- | --- |
| 0–15 s | 課題と DoD |
| 15–60 s | RobOps（契約、CI、バリデータ） |
| 60–120 s | MuJoCo で ACT（TE）の把持〜整列。**TODO: `sim_rollout.mp4` を post50 TE で再生成** |
| 120 s–終了 | 第 5 章の表（TE vs chunk）と DoD 達成の明示。実機があればテレオペ／ロールアウトを短く |

テロップ例: chunk_size=30、TE（n_action_steps=1）、閾値 25 mm / 15 deg、post50 align=1.000 / mean=18.1 mm。

---

## 9. 今後の課題

1. **公式結果のリポジトリ固定:** post50 の `metrics.json` / 再検証（seed=1000）を `docs/results/` に置き、pending を解消する（DoD ④ の提出体裁）。
2. **chunk30 の底上げ:** TE 依存を減らし、選択メトリクスと実行を chunk でも DoD 達成できるようにする。
3. **実機デモ:** カメラ完成後にテレオペ教示を収集し、単位系（rad ↔ deg、グリッパ 0–100）を揃えて学習・評価する。
4. **PDF 化（DoD ⑤）:** 本稿 TODO を埋め、`./scripts/build_report_pdf.sh yohei1126` で提出 PDF を生成する。
5. **動画:** TE 成功ロールアウトと（可能なら）実機テレオペを 1〜3 分に収める。

---

## 付録 A. 生成すべき図表一覧（未作成は TODO）

| ID | 種別 | 内容 | 状態 |
| --- | --- | --- | --- |
| 表1 | 表 | DoD ①–⑤ 判定（第 1.3 節） | 本稿に草案あり。④の公式 JSON リンクは TODO |
| 表2 | 表 | post50 TE vs chunk（第 5.1 節） | PR #34 より転記済み |
| 表3 | 表 | seed=1000・50 epi 再検証 | TODO（数値の metrics 根拠を添付） |
| 表4 | 表 | 失敗モードと対策履歴 | 草案あり |
| 図1 | 図 | システム構成図（収集→学習→TE/chunk 評価） | TODO: 清書 |
| 図2 | 図 | 学習曲線（loss / val_l1 / CL align） | TODO: `training_metrics.json` から作成 |
| 図3 | 図 | エピソードごとの位置誤差ヒストグラム（TE） | TODO |
| 図4 | 図 | 初期箱 XY 散布（PR #52 の `initial_box_xy`） | TODO |
| 図5 | 写真/動画 | 実機テレオペ（60 Hz）とカメラ配置 | TODO |
| 図6 | 動画 | TE 成功ロールアウト MP4 | TODO |
| 図7 | 図 | 作業エリア配置（既存 [`docs/images/so101_layout_guide.png`](../docs/images/so101_layout_guide.png)） | 流用可 |

## 付録 B. TODO チェックリスト（所有者編集用）

- [ ] seed=1000・50 epi の TE 成功率・平均 18.28 mm・レンジ 14.3–20.0 mm を `metrics.json` で確認し出典 URL／パスを書く
- [ ] post50 生メトリクスを `docs/results/` にコピーし `eval_sim_act.pending.json` を解消
- [ ] `training_metrics.json` から損失・CL 指標を転記
- [ ] 平均絶対ヨー誤差を表に追加
- [ ] 実機 60 Hz テレオペの証拠（動画・ログ日付）を添付
- [ ] rad/deg・グリッパ 0–100 の変換手順を確定
- [ ] 付録 A の未作成図を生成
- [ ] 成果動画を撮影し YouTube タイトルを仕様どおりにする
- [ ] PDF ビルドと個人情報チェック（[`report/README.md`](README.md)）

---

## 改訂履歴（原稿）

| 日付 | 内容 |
| --- | --- |
| 2026-10-18 | 初稿。post50（PR #34）と PR #52 / Issue #51 / DoD（Issue #23）を反映。未確認数値は TODO |
