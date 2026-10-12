# Task 2: 合成データ ACT 疎通

ホスト Python 3.12+ で実行する（Docker には torch / lerobot を入れない。`lerobot` 0.6.x は 3.12 必須）。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,dev]"

# 契約準拠の合成 LeRobotDataset（既定: 8 episodes × 64 frames）
python scripts/generate_synthetic_dataset.py

# ResNet18 ACT を 100 step 学習し best_model.pt を保存 → 推論スモーク
python -m port_pick_align.training.train_act
```

成果物（ローカル生成・gitignore 対象）:

- `data/synthetic/lerobot/` — 合成データセット
- `checkpoints/synthetic_act/best_model.pt` — 疎通用チェックポイント
- `checkpoints/synthetic_act/training_metrics.json`

推論のみ再実行:

```bash
python -m port_pick_align.training.train_act --infer-only
```
