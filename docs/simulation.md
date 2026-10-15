# MuJoCo シミュレーションによる閉ループ評価

実機環境での動作に先立ち、卓上マニピュレーションシミュレータを用いて ACT 推論パイプラインおよび整列精度の閉ループ検証を行う。

## 依存環境のセットアップ（ホスト環境）

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,dev]"
# 学習済みチェックポイントの推論を行う場合は training 拡張も導入する
pip install -e "port_pick_align/[simulation,training,dev]"
```

オフスクリーン描画は標準の `python` インタプリタで実行可能である（`mjpython` は対話型 3D ビューアの起動時にのみ使用する）。グラフィクス描画バックエンドの指定が必要な環境では、以下の環境変数を設定する。

```bash
export MUJOCO_GL=glfw   # macOS の既定値
# ヘッドレス Linux 環境の例: export MUJOCO_GL=osmesa
```

## シミュレーション環境の構成

- 機構モデル: 6 自由度アームおよびグリッパ（関節名は `configs/contract.yaml` と同一）
- センサ構成: Top および Wrist の 2 眼カメラ（解像度 640×480）
- オブジェクト: 小型直方体箱および机上面の目標整列枠
- 実装パッケージ: `port_pick_align.simulation`（モデル定義: `simulation/assets/so101_tabletop.xml`）

## 動作の可視化と確認

### 1. MuJoCo 対話型 3D ビューア

macOS 環境では、スレッド制約（`launch_passive`）のため **`mjpython`** を使用して起動する必要がある。uv で作成した仮想環境では、動的ライブラリへのシンボリックリンクを作成して実行する。

```bash
source .venv/bin/activate
# uv 製仮想環境における動的ライブラリの配置（初回のみ）
mkdir -p .venv/lib
ln -sfn "$(python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')/libpython3.12.dylib" \
  .venv/lib/libpython3.12.dylib

.venv/bin/mjpython scripts/view_sim.py --policy scripted
```

操作方法: マウスのドラッグ操作で視点回転、スクロールでズームを行う。ウィンドウを閉じると終了する。

### 2. Rerun による多峰性データ可視化

仮想環境内の `rerun` バイナリが実行可能パスに含まれていることを前提とする。

```bash
export PATH="$PWD/.venv/bin:$PATH"
python scripts/run_sim_eval.py --policy scripted --rerun --save-video
```

### 3. ロールアウト動画ファイルの確認

```bash
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun
open outputs/eval/sim_rollout.mp4   # macOS 環境での再生確認
```

## 閉ループ評価の実行手順

ポリシーの種別や実行環境に応じて、以下のコマンドを実行する。

```bash
# デモ用ヒューリスティックポリシー（固定スポーン位置における把持・整列動作の確認）
# 既定の --video-mode topdown は OpenGL 不要の俯瞰模式図動画を生成する
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun

# OpenGL / glfw が利用可能な環境におけるカメラ撮像動画の生成
python scripts/run_sim_eval.py --policy scripted --video-mode mujoco --save-video

# 最小依存関係による動作テスト（現在関節位置の繰り返し入力）
python scripts/run_sim_eval.py --policy mock --episodes 1 --max-steps 20 --no-save-video

# 学習済み ACT チェックポイントによる推論実行（入出力形状の疎通検証）
python scripts/run_sim_eval.py --policy checkpoint \
  --checkpoint checkpoints/synthetic_act/best_model.pt --video-mode topdown

# Rerun 可視化を有効化した閉ループ評価
export PATH="$PWD/.venv/bin:$PATH"
python scripts/run_sim_eval.py --policy scripted --rerun --video-mode mujoco
```

評価スクリプトの出力成果物（Git 管理対象外）:

- `outputs/eval/metrics.json`: 平面位置誤差、ヨー角誤差、把持および整列の成功率集計
- `outputs/eval/sim_rollout.mp4`: 視覚化ロールアウト動画

## 単体・統合テスト

```bash
(cd port_pick_align && pytest -m simulation -q)
```

`mujoco` パッケージが未インストールの環境では `pytest.importorskip` により自動的にテストがスキップされるため、最小構成の CI パイプラインを阻害しない。

## オラクル教示データの収集

同一環境と `ScriptedPickAlignPolicy` から LeRobotDataset を自動収集する手順は [dataset.md](dataset.md) に記載する。エントリポイントは `scripts/collect_sim_dataset.py` である。

## 関連文書

- 評価 API 仕様: [evaluation.md](evaluation.md)
- ACT モデルの訓練: [training.md](training.md)
- 教示データ収集: [dataset.md](dataset.md)

