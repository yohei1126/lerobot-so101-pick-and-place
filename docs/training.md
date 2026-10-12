# ACT 学習・推論スモーク

ホスト Python 3.12+ で実行する（`lerobot` 0.6.x は 3.12 必須）。

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# 合成データ（未生成なら）
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

観測キーと action chunk 形状は契約どおり:

- `observation.images.top` / `wrist`: `(B, 3, 480, 640)` float `[0,1]`
- `observation.state`: `(B, 6)`
- action chunk: `(30, 6)`
