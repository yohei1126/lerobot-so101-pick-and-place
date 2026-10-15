# 閉ループ評価の記録

本ディレクトリは、実測した評価ログと、未実行のプロトコルを分けて置く。`status` が `pending` のファイルは測定値を持たない。`summary` が null の項目を、達成値としてレポートや表に転記しない。

## 未実行: 学習済み ACT

`eval_sim_act.pending.json` は Task 7.4 の本評価がまだ無いことを示す。本学習で `checkpoints/sim_act/best_model.pt` を得た後、次を実行する。成果物は Git 管理外の `outputs/eval_sim_act/` に書かれる。

```bash
DEVICE=mps ./scripts/run_phase15_benchmark.sh
```

MPS が無い環境では `DEVICE=cpu` とできる。その実行が 20 エピソード未満、または `training_metrics.json` の `below_recommended_steps` が true の重みを使った場合は、提出用の達成値にしない。

達成条件は、整列成功率 85% 以上、把持成功率 90% 以上、平均平面位置誤差 25 mm 未満、平均絶対ヨー角誤差 15 deg 未満である。`metrics.json` の `thresholds_met` はこの条件の成否を示す。

## 比較条件

オラクル（scripted、初期配置ランダム、Temporal Ensembling なし）:

```bash
python scripts/run_sim_eval.py --policy scripted --episodes 20 --max-steps 260 \
  --randomize-box --no-temporal-ensemble --no-save-video \
  --output-dir outputs/eval_scripted_random
```

モック（現在姿勢の繰り返し。学習ベースラインではない）:

```bash
python scripts/run_sim_eval.py --policy mock --episodes 20 --max-steps 260 \
  --randomize-box --no-save-video --output-dir outputs/eval_mock_random
```

いずれのログも、実行して `status` が `measured` になったファイルだけを数値の根拠にする。
