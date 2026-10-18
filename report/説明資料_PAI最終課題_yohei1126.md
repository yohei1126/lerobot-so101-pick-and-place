<!-- markdownlint-disable MD013 MD024 MD060 -->

# Physical AI 応用編1 最終課題 説明資料

**OmniCampusアカウント名:** `yohei1126`

> 注意: 氏名・所属・メールアドレスなどの個人情報は記載しないこと。  
> 本稿は提出用 PDF（DoD ⑤）向けの原稿である。残 TODO は実機証拠リンク・成果動画・最終 PDF のみ（付録 B）。`./scripts/build_report_pdf.sh yohei1126` で PDF 化する。

## 0. 本稿の位置づけと出典方針

- 定量値の正本は `docs/results/` にピン留めした JSON である（[`docs/results/README.md`](../docs/results/README.md)、[`post50_official_summary.json`](../docs/results/post50_official_summary.json)）。表示の丸めは summary ファイル、転記根拠は各セル JSON の `summary` およびエピソード配列とする。
- 単位系は [`docs/units.md`](../docs/units.md)（および `port_pick_align/units.py`）に従う。
- 図表は [`docs/figures/`](../docs/figures/)（[`manifest.json`](../docs/figures/manifest.json)）。
- その他の主要出典: [Issue #23](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/issues/23)（DoD）、[PR #34](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/pull/34#issuecomment-6233795103)（post50 パイプライン経緯）、[PR #52](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/pull/52) / [Issue #51](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/issues/51)、[`docs/plan_b.md`](../docs/plan_b.md)、[`docs/hardware.md`](../docs/hardware.md)。

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

| # | 項目 | 判定 | 根拠 |
| --- | --- | --- | --- |
| ① | 教示の自動収集（50〜100 エピソードの LeRobotDataset） | 達成 | post50 パイプライン（`checkpoints/sim_act_post50`） |
| ② | MPS 上での本格学習 | 達成 | 同上。学習曲線は図 2 |
| ③ | Temporal Ensembling 実装 | 達成 | TE 評価セルおよびコード |
| ④ | 定量ベンチマーク（整列 ≥ 85%、平均位置誤差 < 25 mm） | **TE モードで達成** | [`eval_sim_act_post50_best_model_te_te.json`](../docs/results/eval_sim_act_post50_best_model_te_te.json) |
| ⑤ | 提出用 PDF | **未完了** | TODO: 所有者による最終 PDF ビルド |

**DoD ④ の達成モード:**  
`best_model_te` を Temporal Ensembling（`n_action_steps=1`）で評価したとき、整列成功率 1.000、平均位置誤差 18.081 mm（中央値 18.955 mm）であり、DoD を満たす。正本: [`docs/results/eval_sim_act_post50_best_model_te_te.json`](../docs/results/eval_sim_act_post50_best_model_te_te.json)（一覧: [`post50_official_summary.json`](../docs/results/post50_official_summary.json)）。  
初期のベンチマーク文書では達成判定を chunk30 側に置いていたが、本稿では実測上 DoD を満たす実行モードとして **TE を主達成**と明記する。chunk30 比較セルは未達である（第 5 章）。

把持成功率の参考閾値（≥ 90%）は [`docs/results/README.md`](../docs/results/README.md) にあり、上記 TE セルでは把持率 1.000 である。

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
                 └──▶ docs/results/*.json（ピン留め）
```

### 2.3 単位系（sim / 契約 / 実機）

出典: [`docs/units.md`](../docs/units.md)。

| 系 | アーム 5 軸 | グリッパ | 箱ヨー / 評価ヨー |
| --- | --- | --- | --- |
| MuJoCo sim / `contract.yaml` | **ラジアン** | **ラジアン**（6 次元目） | sim の `box_yaw` はラジアン。`metrics.json` のヨー誤差は **度** |
| 実機 LeRobot SO-101（典型） | **度** | **0–100**（開度パーセント） | 実機評価時は度で揃える |

契約のグリッパ可動域は `[-0.1745, 1.7453]` rad。0–100 への線形写像は `gripper_rad_to_percent` / `gripper_percent_to_rad`（`port_pick_align/units.py`）。実データ学習前に実機ログの単位を確認し、必要なら契約ラジアンへ揃える。

### 2.4 実機ハードウェア（準備状況）

設計対象は SO-ARM101（Feetech STS3215）＋ Top/Wrist カメラ。配置・機材一覧は [`docs/hardware.md`](../docs/hardware.md)。

| 項目 | 状態 | 出典 |
| --- | --- | --- |
| SO-101 Leader / Follower | キャリブレーション済み、leader→follower テレオペ動作（オーナー報告 2026-10-17） | TODO: 証拠リンク（動画／ログ）を所有者が添付 |
| 制御周期 | 約 60 Hz（同上） | TODO: 同上 |
| カメラ | セットアップ中（C920 上カメラ、手首カメラ） | [`docs/hardware.md`](../docs/hardware.md) |
| 次工程 | `lerobot-record` → 学習 → `lerobot-rollout` | 未着手 |

---

## 3. データパイプラインと品質管理（RobOps / 技術力）／手法（データ）

### 3.1 収集

1. MuJoCo 上で `ScriptedPickAlignPolicy` をロールアウトし、画像＋関節目標を LeRobotDataset として保存（`scripts/collect_sim_dataset.py`）。
2. 初期箱の平面位置・ヨーをランダム化し、整列成功エピソードのみ採録する（[`docs/dataset.md`](../docs/dataset.md)）。
3. `validate_episode` により同期ずれ・フレーム間隔・関節可動域・静止を検査する。
4. 教示軌道は反復改善済み（運搬中ヨー合わせ、パッド近傍の閉じた approach+place、開いた静止解放など。Issue #39/#41/#45 系）。

post50 ランは `scripts/run_pipeline.sh` 経由の収集・学習・評価である（チェックポイントディレクトリ `sim_act_post50`）。

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

PR #52 以降、エピソードごとに `initial_box_xy` / `initial_box_yaw` / `seed` を `metrics.json` に記録できる。post50 当初の評価 JSON には初期 XY が無いため、散布図作成時は同一 seed で `env.reset` して spawn XY を再構成した（第 5.6 節・図 4）。

### 4.4 学習曲線

post50 の `training_metrics.json` から生成した学習曲線を図 2 に示す（入力は [`docs/figures/manifest.json`](../docs/figures/manifest.json) の `training_metrics`）。

![図2. post50 学習曲線（train_loss / val_l1）](../docs/figures/training_loss_curve.png)

---

## 5. 定量評価と動作検証（実用性）／実験と結果

> 本節の ACT 数値は **Plan B（MuJoCo）** 上の結果である。正本は下表の JSON パス。

### 5.1 post50: TE 対 chunk30（主結果）

条件: `checkpoints/sim_act_post50`、seed 0、各 20 エピソード、最大 260 ステップ、初期配置ランダム。  
一覧: [`docs/results/post50_official_summary.json`](../docs/results/post50_official_summary.json)。

| Checkpoint | Mode | Align | Mean pos (mm) | Median (mm) | Range (mm) | Mean \|yaw\| (deg) | Grasp | 正本 JSON |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| **`best_model_te`** | **TE** | **1.000** | **18.081** | **18.955** | **14.579–20.190** | **11.830** | **1.000** | [`eval_sim_act_post50_best_model_te_te.json`](../docs/results/eval_sim_act_post50_best_model_te_te.json) |
| `best_model` | chunk30 | 0.000 | 39.157 | 39.097 | 38.921–39.439 | 36.711 | 1.000 | [`eval_sim_act_post50_best_model_chunk30.json`](../docs/results/eval_sim_act_post50_best_model_chunk30.json) |

表示値は `post50_official_summary.json` の公式セル（丸め）。mean / yaw は各 JSON の `summary`、median・range は同ファイルの公式セルおよびエピソード配列から算出した値と一致する。

**読み取り:**

- DoD を満たす組み合わせは **`best_model_te` × TE**（整列 100%、平均 18.081 mm < 25 mm、平均 \|ヨー\| 11.830 deg < 15 deg）。
- `best_model` × chunk30 は整列 0、平均 39.157 mm で DoD 未達。
- 選択メトリクス（chunk 向け / TE 向け）と実行モードを揃えないと成績が大きく崩れる。

位置誤差の分布比較:

![図3. TE と chunk30 の位置誤差ヒストグラム](../docs/figures/position_error_histogram.png)

### 5.2 DoD 判定表（post50・TE）

| 指標 | DoD | `best_model_te` × TE | 判定 |
| --- | --- | ---: | --- |
| 整列成功率 | ≥ 85% | 1.000（20/20） | 達成 |
| 平均位置誤差 | < 25 mm | 18.081 mm | 達成 |
| 平均絶対ヨー誤差 | < 15 deg（docs/results 参考） | 11.830 deg | 達成 |
| 把持成功率（参考） | ≥ 90% | 1.000 | 達成 |

### 5.3 独立再検証（seed=1000、50 エピソード・TE）

正本: [`docs/results/eval_sim_act_post50_seed1000_te.json`](../docs/results/eval_sim_act_post50_seed1000_te.json)（`post50_official_summary.json` の `seed1000_te_verification.measured`、`match_within_tol: true`）。

| 項目 | 実測値 |
| --- | ---: |
| seed / エピソード数 | 1000 / 50 |
| 整列成功率 | 1.000 |
| 平均位置誤差 (mm) | 18.283 |
| 中央値 (mm) | 18.961 |
| 位置誤差レンジ (mm) | 14.320–20.038 |
| 平均絶対ヨー誤差 (deg) | 11.665 |
| 把持成功率 | 1.000 |

依頼文の「100%、平均 18.28 mm、範囲 14.3–20.0 mm」は上記 JSON と tol 内で一致した（[`docs/results/README.md`](../docs/results/README.md)）。不一致時は JSON を正とする。

### 5.4 scripted オラクル（参考ベースライン）

出典: [`docs/results/scripted_random_20.json`](../docs/results/scripted_random_20.json)。  
20 エピソード・初期配置ランダム・CPU。整列 1.0、平均位置誤差 0.0 mm、`thresholds_met=true`。ACT の結果ではない。

### 5.5 公式ベンチマーク成果物

| 成果物 | 役割 |
| --- | --- |
| [`post50_official_summary.json`](../docs/results/post50_official_summary.json) | 公式セル一覧と seed=1000 検証状態 |
| [`eval_sim_act_post50_best_model_te_te.json`](../docs/results/eval_sim_act_post50_best_model_te_te.json) | DoD 主結果（TE・20 epi） |
| [`eval_sim_act_post50_best_model_chunk30.json`](../docs/results/eval_sim_act_post50_best_model_chunk30.json) | chunk30 比較（20 epi） |
| [`eval_sim_act_post50_seed1000_te.json`](../docs/results/eval_sim_act_post50_seed1000_te.json) | 独立再検証（TE・50 epi） |

### 5.6 初期箱 XY 散布図と代表ロールアウト

初期箱 XY 散布図（図 4）は TE 評価の最終誤差を色・成否で示す。元の post50 TE `metrics.json` には `initial_box_xy` が無かったため、**同一 seed で `env.reset` して spawn XY のみ再構成**したうえでプロットした（誤差・成否は元 JSON）。出典: [`docs/figures/manifest.json`](../docs/figures/manifest.json) の notes（`backfill_initial_box_xy: true`）。

![図4. 初期箱 XY 散布（TE、初期 XY は seed から再構成）](../docs/figures/initial_box_xy_scatter.png)

代表ロールアウト動画（`best_model_te` × TE）: [`docs/figures/sim_rollout_representative.mp4`](../docs/figures/sim_rollout_representative.mp4)

---

## 6. 考察・失敗分析と改善ループ

### 6.1 なぜ TE が chunk 実行を上回るか（post50）

1. **実行ホライズンと教示の整合:** TE は毎ステップ再計画＋平滑化により、接近〜解放のタイミングずれを吸収しやすい。chunk30 は 30 歩分を固定実行するため、開指令や運搬途中の視覚誤差が残るとパッド到達前に停滞しやすい（平均約 39 mm 帯に固まる）。
2. **チェックポイント選択の分離:** `best_model_te` は TE 閉ループで選ばれた重みである。**学習時の選択メトリクスと評価時の実行モードを一致させることが必須**である。
3. **過去のスナップ偽陽性（PR #46）:** 解放時に箱をパッド中心へテレポートしていた時期があり、TE「整列 100%・誤差 0.0 mm」が過大評価だった。スナップ廃止後の post50 TE は平均 18.081 mm と、閾値内だが非ゼロの現実的な誤差になっている。

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
- 実機分布（照明、カメラ外部、摩擦）へのギャップは未評価。単位変換手順は [`docs/units.md`](../docs/units.md) に確定済みだが、実機ログでの突合はこれからである。
- 散布図の初期 XY は seed からの再構成であり、評価当時にログされた座標そのものではない（誤差は元 JSON）。

---

## 7. 実現場への展開構想（実用性）／実機への展開

### 7.1 現状

| 項目 | 内容 | 確認 |
| --- | --- | --- |
| アーム | 実 SO-101 をキャリブレーション済み、leader→follower テレオペ可（2026-10-17 オーナー報告） | TODO: 証拠リンクを添付 |
| 周期 | 約 60 Hz | TODO: 同上 |
| カメラ | セットアップ中（配置は hardware.md に準拠予定） | 進行中 |
| 単位 | sim/契約は rad、実機は deg + グリッパ 0–100（[`docs/units.md`](../docs/units.md)） | 文書化済み |
| 次 | 実デモを `lerobot-record` → 学習 → `lerobot-rollout` | 未着手 |

### 7.2 Plan B（シミュレーション縮退）

実機が締切までに安定しない場合は [`docs/plan_b.md`](../docs/plan_b.md) に従い、MuJoCo 評価動画と RobOps（変換・バリデータ・CI）の検証性で提出要件を満たす。本稿第 5 章の post50 TE 結果と [`sim_rollout_representative.mp4`](../docs/figures/sim_rollout_representative.mp4) がその中核エビデンスである。切り替え判定日の目安は 2026-10-23（plan_b.md）。

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
| 15–60 s | RobOps（契約、CI、バリデータ、単位系） |
| 60–120 s | MuJoCo で ACT（TE）の把持〜整列。[`sim_rollout_representative.mp4`](../docs/figures/sim_rollout_representative.mp4) を素材に使用可 |
| 120 s–終了 | 第 5 章の表（TE vs chunk、seed=1000 検証）と DoD 達成の明示。実機があればテレオペを短く |

テロップ例: chunk_size=30、TE（n_action_steps=1）、閾値 25 mm / 15 deg、post50 TE align=1.000 / mean=18.081 mm。

**TODO:** YouTube 提出用の最終成果動画（1〜3 分）を撮影・公開する。

---

## 9. 今後の課題

1. **chunk30 の底上げ:** TE 依存を減らし、選択メトリクスと実行を chunk でも DoD 達成できるようにする。
2. **実機デモ:** カメラ完成後にテレオペ教示を収集し、[`docs/units.md`](../docs/units.md) の変換で契約ラジアンへ揃えて学習・評価する。
3. **成果動画:** 提出仕様の YouTube 動画を完成させる。
4. **PDF 化（DoD ⑤）:** `./scripts/build_report_pdf.sh yohei1126` で提出 PDF を生成する。

---

## 付録 A. 図表一覧

| ID | 内容 | パス / 状態 |
| --- | --- | --- |
| 表1 | DoD ①–⑤ 判定 | 第 1.3 節 |
| 表2 | post50 TE vs chunk30 | 第 5.1 節（JSON 正本） |
| 表3 | seed=1000・50 epi 再検証 | 第 5.3 節 |
| 表4 | 失敗モードと対策 | 第 6.2 節 |
| 図2 | 学習曲線 | [`docs/figures/training_loss_curve.png`](../docs/figures/training_loss_curve.png) |
| 図3 | 位置誤差ヒストグラム | [`docs/figures/position_error_histogram.png`](../docs/figures/position_error_histogram.png) |
| 図4 | 初期箱 XY 散布（XY は seed 再構成） | [`docs/figures/initial_box_xy_scatter.png`](../docs/figures/initial_box_xy_scatter.png) |
| 動画 | TE 代表ロールアウト | [`docs/figures/sim_rollout_representative.mp4`](../docs/figures/sim_rollout_representative.mp4) |
| 配置図 | 作業エリア | [`docs/images/so101_layout_guide.png`](../docs/images/so101_layout_guide.png) |
| 実機写真 | 60 Hz テレオペ証拠 | TODO（所有者提供） |

## 付録 B. 残 TODO（所有者）

- [ ] 実機 60 Hz テレオペの証拠リンク（動画・ログ）を添付する
- [ ] 成果発表動画（YouTube、タイトル `PAI最終課題_yohei1126`）を公開する
- [ ] 最終 PDF（DoD ⑤）を `./scripts/build_report_pdf.sh yohei1126` で生成し、個人情報チェックを行う（[`report/README.md`](README.md)）

---

## 改訂履歴（原稿）

| 日付 | 内容 |
| --- | --- |
| 2026-10-18 | 初稿。post50（PR #34）と PR #52 / Issue #51 / DoD（Issue #23）を反映 |
| 2026-10-18 | `docs/results` ピン留め JSON・`docs/units.md`・`docs/figures` を反映。解消済み TODO / pending 表現を削除 |
