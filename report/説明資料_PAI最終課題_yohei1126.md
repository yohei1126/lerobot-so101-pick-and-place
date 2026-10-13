<!-- markdownlint-disable MD013 MD024 MD060 -->

# Physical AI 応用編1 最終課題 説明資料

**OmniCampusアカウント名:** `yohei1126`

> 注意: 氏名・所属・メールアドレスなどの個人情報は記載しないこと。

## 1. 課題設定と社会的背景（創造性）

### 1.1 背景と課題

造船・海事・港湾現場では、熟練作業者の不足と危険空間での反復作業が同時に進行している。コンテナ荷役やヤード内の部品・治具の整列は、見た目には単純でも、位置・姿勢の許容誤差が小さく、失敗時の再作業コストが大きい。本課題ではその「把持して枠へ精密整列する」操作を、卓上サイズの日常品モックに縮約し、Physical AI の収集〜学習〜評価のループを安全に再現する。産業スケールではなく、再現可能なデスクトップ環境で RobOps を回すことが本レポートの狙いである。

### 1.2 本課題のタスク定義

- **対象物**: 小型直方体箱（机上モック。現場ではコンテナ／部品パレットに相当）
- **目標**: 机上のマスキング枠（目標サイト）へ平面位置・ヨーを合わせて配置
- **成功条件（評価 API）**: 位置誤差 ≤ 25 mm、ヨー誤差 ≤ 15 deg、把持（リフトまたは整列近傍）成功
- **観測**: Top / Wrist の 2 眼カメラ（640×480@30）＋関節 6 DoF
- **制御**: ACT（chunk_size=30）またはデモ用 scripted ポリシーによる関節位置指令

### 1.3 公式サンプルに対する独自性

シミュレータ単体のデモに終始せず、(1) `configs/contract.yaml` によるトピック・形状の契約一元化、(2) rosbag2 → LeRobot 変換と品質バリデータ、(3) GitHub Actions CI、(4) ROS 2 推論モック＋Rerun、(5) MuJoCo 閉ループ評価までを一本のリポジトリに揃えた。海事・港湾の荷役整列を日常品でモック化し、**失敗→品質ゲート→再学習**の RobOps をレポートの主軸にする点が、公式サンプル群との差分である。

## 2. システムアーキテクチャ（技術力）

### 2.1 ハードウェア

実機本線は SO-ARM101（Feetech）＋ USB カメラ 2 台を想定。Phase 1 時点ではハード未接続のため、契約とドライラン手順（udev / Feetech extra）までを先行整備した。

| 項目 | 仕様 |
| --- | --- |
| アーム | SO-ARM101 相当 6 DoF（shoulder_pan … gripper）。`lerobot_type: so101_follower` |
| カメラ | Top / Wrist、各 640×480@30、トピック `/camera/{top,wrist}/image_raw` |
| モック対象 | 小型直方体箱＋机上目標枠（マスキングテープ相当） |

### 2.2 ソフトウェアスタック

| 層 | 役割 |
| --- | --- |
| Docker (ROS 2 Humble) | 推論モック、rosbag、Rerun、validator CI |
| Host venv (`port_pick_align`) | 合成データ、ACT、converter/validator、MuJoCo |
| Cloud GPU（任意） | ACT 本格学習 |
| `configs/contract.yaml` | トピック名・解像度・関節・品質閾値の SSOT |

```text
[rosbag2 / mock sensors]
        │
        ▼
 converter + validator  ──contract.yaml──▶  LeRobotDataset
        │
        ▼
   ACT train / ckpt
        │
        ├─▶ ROS 2 act_policy_node ──▶ /joint_commands (+ Rerun)
        └─▶ MuJoCo PickAlignSimEnv ──▶ metrics.json / sim_rollout.mp4
```

## 3. データパイプラインと品質管理（RobOps / 技術力）

### 3.1 収集から学習用データまで

1. rosbag2 に Top / Wrist / `/joint_states` を契約どおり記録
2. `scripts/convert_bag.py` → LeRobotDataset（画像・関節の整列）
3. 合成データ経路（`generate_synthetic_dataset.py`）で 2 眼＋6 DoF の ACT 疎通を先行確認
4. 学習済み重みを ROS 推論または MuJoCo 閉ループへ投入

### 3.2 品質バリデーション

フィクスチャ `port_pick_align/tests/fixtures/sample_bag/` と GitHub Actions（unit / integration）でゲートする。

| チェック項目 | 閾値 / 判定 | 結果 |
| --- | --- | --- |
| 時刻同期 | offset > 33 ms を検出 | 単体テストで意図的ズレ bag を検出 |
| フレームドロップ | 間隔 > 50 ms（&lt;20 fps）を検出 | 同上 |
| スキーマ整合 | `contract.yaml` の topic / dim / 解像度 | contract ロード試験＋converter 試験パス |
| 可動域・静止 | joint_limits / 分散≈0 エピソード除外 | validator 単体試験パス |

## 4. モデル選定と学習（技術力）

### 4.1 選定理由

ACT（Action Chunking with Transformers）は、講義（模倣学習・action chunk）と LeRobot 実装の接続が良く、短ホライズンの把持・整列に適する。Phase 1 の疎通は軽量バックボーン ResNet18 に固定し、DINOv2 等の比較は Could 扱いとした。

### 4.2 ハイパーパラメータと学習結果

| 項目 | 値 |
| --- | --- |
| chunk_size | 30 |
| backbone | ResNet18 |
| action_dim / カメラ | 6 DoF / Top+Wrist |
| 学習 | 合成データで 100 step 級の軽量学習（疎通） |
| 成果物 | `checkpoints/synthetic_act/best_model.pt` |

合成データでの学習は **入力 shape と train→infer API の疎通** が目的である。実タスク精度は実機テレオペ収集後（Phase 2）または Plan B の scripted / 公開データへ委ねる。損失曲線は CI の integration artifact（`training_metrics.json`）およびローカル学習ログで確認する。

## 5. 実機実験・定量評価（実用性）

> **本節は Plan B（MuJoCo シミュ）前提**である。ハード到着後は実機メトリクスに差し替え、[docs/plan_b.md](../docs/plan_b.md) の縮退方針を更新する。

### 5.1 評価指標

scripted 閉ループ（固定スポーン、`outputs/eval/metrics.json`）:

| 指標 | 定義 | 結果 |
| --- | --- | --- |
| 把持成功率 | エピソード中の sticky grasp または近傍整列 | **1.0**（1/1） |
| 整列誤差 (mm / deg) | 箱 XY・yaw vs 目標枠（≤25 mm / ≤15 deg） | **0.0 mm / 0.0 deg**（align 成功率 1.0） |
| 所要時間 | 制御 30 Hz、最大 300 step | 約 260 step 前後で完了 |

ACT checkpoint（合成重み）は例外なく閉ループが回り metrics / 動画を出力する（タスク成功率は未達が想定どおり）。デモ動画: `outputs/eval/sim_rollout.mp4`（topdown 模式図。OpenGL カメラ映像は `--video-mode mujoco`）。

### 5.2 外乱耐性

Phase 1 では固定スポーンを成功の正本とした。`randomize_box` による初期 XY オフセットは次段で scripted / 実データ ACT の両方に対し比較予定。照明変化は実機カメラ到着後に再評価する。

## 6. 失敗分析とモデル改善

### 6.1 失敗モード分類

| 失敗モード | 件数 / 頻度 | 推定原因 | 対策 |
| --- | --- | --- | --- |
| 把持ミス | 初期 scripted（開ループ関節）で常時 | EE が箱に未到達／指が物理開閉しない MJCF | IK＋sticky grasp、摩擦強化 |
| 解放後キック | 修正前に高頻度 | 配置直後にアームが箱へ衝突 | 配置後フリーズ＋retreat を home 側へ |
| 合成 ACT の未整列 | 現状 | ダミー軌道で学習しておりタスク分布外 | 実機／scripted デモからの再学習 |
| （ハードトラブル） | Phase 1 対象外 | 未着・通信 | Plan B（本節）＋udev/Feetech ドライラン |

### 6.2 改善ループ（RobOps）

失敗メトリクス → validator で同期／ドロップを確認 → 追加エピソード収集（または合成拡張）→ ACT 再学習 → MuJoCo / モック ROS で定量比較。契約ファイルを変えずにノードと学習が追従できることが、再実行コストを下げている。

## 7. 現場スケールアップ構想（実用性）

実船・ヤードへ展開する場合、防塵防滴・船体動揺・通信途絶・安全規格（非常停止・速度制限）がボトルネックになる。本リポの価値は「現場の生データ」そのものではなく、**契約・品質ゲート・再現可能な評価**を先に固定し、拠点が増えてもデータとモデルの差分を CI で検知できる点にある。港湾 CT のスプレッダ位置合わせは、本モックの「枠への整列誤差」を mm 単位で監視する運用に読み替えられる。

## 8. 動画構成と説明設計（表現力）

### 8.1 YouTube 提出仕様（確認）

| 項目 | 内容 |
| --- | --- |
| タイトル | `PAI最終課題_yohei1126` |
| 尺 | 1〜3 分（目標: **約 2 分 30 秒**） |
| 公開設定 | 限定公開（必須）/ 全体公開（推奨） |
| 倍速 | 実機・シミュの作業区間は **2 倍速**を予定。動画内テロップと概要欄に「2x」と明記 |

### 8.2 画面構成案

| 秒 | 内容 | 表示 |
| --- | --- | --- |
| 0–15 | 課題・背景 | 海事モックの一文＋タスク定義 |
| 15–60 | システム / RobOps | contract / CI / validator、Rerun 軌道 |
| 60–120 | タスク実行 | 俯瞰＋手先（または topdown 模式図）で把持→整列 |
| 120–終了 | 評価・失敗分析・まとめ | metrics（mm/deg）と改善ループ |

テロップで明示する技術点: ApproximateTimeSynchronizer、品質閾値（33 ms / 50 ms）、ACT chunk=30、整列閾値 25 mm / 15 deg。
