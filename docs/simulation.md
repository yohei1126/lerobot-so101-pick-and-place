# MuJoCo 閉ループ評価

実機前に、卓上マニピュレーション環境で ACT 推論パイプラインと整列評価を検証する。

## インストール（Host / Apple Silicon）

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,dev]"
# checkpoint 推論を使う場合は training も
pip install -e "port_pick_align/[simulation,training,dev]"
```

オフスクリーン描画は素の `python` で実行する（`mjpython` は viewer 用）。問題があれば:

```bash
export MUJOCO_GL=glfw   # macOS 既定
# ヘッドレス Linux 例: export MUJOCO_GL=osmesa
```

## 環境の内容

- 6DoF + グリッパ（関節名は `configs/contract.yaml` と同じ）
- Top / Wrist カメラ（640×480）
- 小型箱と机上の目標枠
- パッケージ: `port_pick_align.simulation`（MJCF: `simulation/assets/so101_tabletop.xml`）

## 動作を目で見る

### 1. MuJoCo 3D ビューア（推奨）

macOS では **`mjpython`** が必要（`launch_passive` 制約）。uv 製 venv では `libpython` のパスも通す。

```bash
source .venv/bin/activate
# uv Python の場合（一度だけ）
mkdir -p .venv/lib
ln -sfn "$(python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')/libpython3.12.dylib" \
  .venv/lib/libpython3.12.dylib

.venv/bin/mjpython scripts/view_sim.py --policy scripted
```

マウス: ドラッグで回転、スクロールでズーム。ウィンドウを閉じると終了。

### 2. Rerun（カメラ・関節・action chunk）

venv の `rerun` が PATH に入っている必要がある。

```bash
export PATH="$PWD/.venv/bin:$PATH"
python scripts/run_sim_eval.py --policy scripted --rerun --save-video
```

### 3. ロールアウト動画（mp4）

```bash
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun
open outputs/eval/sim_rollout.mp4   # macOS
```

## 閉ループ評価の実行

```bash
# デモ向けヒューリスティック（固定スポーンで把持・整列成功）
# 既定の --video-mode topdown は OpenGL 不要の俯瞰模式図動画
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun

# MuJoCo カメラ映像の横並び動画（OpenGL / glfw が使える環境）
python scripts/run_sim_eval.py --policy scripted --video-mode mujoco --save-video

# CI / 依存最小（現在関節を tile）
python scripts/run_sim_eval.py --policy mock --episodes 1 --max-steps 20 --no-save-video

# 学習済み ACT チェックポイント（合成重みは形状疎通。タスク成功率は実データ前の限界）
python scripts/run_sim_eval.py --policy checkpoint \
  --checkpoint checkpoints/synthetic_act/best_model.pt --video-mode topdown

# Rerun 可視化付き
export PATH="$PWD/.venv/bin:$PATH"
python scripts/run_sim_eval.py --policy scripted --rerun --video-mode mujoco
```

成果物（gitignore 対象）:

- `outputs/eval/metrics.json` — 位置誤差・yaw・把持/整列成功率
- `outputs/eval/sim_rollout.mp4` — top|wrist 横並びロールアウト動画

## テスト

```bash
(cd port_pick_align && pytest -m simulation -q)
```

`mujoco` 未インストール時は `importorskip` でスキップされる（通常 CI は壊さない）。

## 関連

- 評価 API: [evaluation.md](evaluation.md)
- ACT 学習: [training.md](training.md)
