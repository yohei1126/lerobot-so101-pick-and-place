# 関節・グリッパの単位（sim / 契約 / 実機 LeRobot）

コード上の Single Source of Truth は [`port_pick_align/units.py`](../port_pick_align/src/port_pick_align/units.py) と [`configs/contract.yaml`](../configs/contract.yaml) である。本ページはレポート転記用の確定記述である（`docs/hardware.md` は変更しない）。

## 結論

| 系 | アーム 5 軸 | グリッパ | 箱ヨー / 評価ヨー |
| --- | --- | --- | --- |
| MuJoCo sim / `contract.yaml` | **ラジアン** | **ラジアン**（他関節と同じ 6 次元目） | sim の `box_yaw` は **ラジアン**。`metrics.json` の `yaw_error_deg` / `mean_abs_yaw_error_deg` は **度** |
| 実機 LeRobot SO-101（典型） | **度** | **0–100**（開度パーセント） | （実機評価時は度で揃える） |

実データ学習の前に、実機ログの単位を確認し、必要なら `deg_to_rad` / `gripper_percent_to_rad` で契約ラジアンへ揃える。

## 契約のグリッパ可動域

`contract.yaml` の `joint_limits.gripper` は `[-0.1745, 1.7453]` rad（コメント上およそ −10° .. 100°）である。本モジュールの「開度パーセント」線形写像は:

- `0` ↔ `−0.1745` rad（より閉じた側）
- `100` ↔ `1.7453` rad（より開いた側）
- 実装: `gripper_rad_to_percent` / `gripper_percent_to_rad`

**注意（実機デプロイ）:** LeRobot 0.6.1 の SO follower では、離散グリッパ指令の符号から **高い `gripper.pos` = より閉じる**（0≈開、100≈閉）と読むのが妥当である。sim→実機ラッパー（[sim_to_real_act.md](sim_to_real_act.md)）は既定でその極性を使い、`--no-gripper-closed-is-high` で本モジュールの開度パーセント意味に切り替えられる。キャリブ結果で逆に見える場合は dry-run で確認すること。

## シミュレータ内の慣例（0–100 ではない）

| 定数 | 値 (rad) | 役割 |
| --- | --- | --- |
| Scripted closed | `0.0` | `ScriptedPickAlignPolicy` の閉指令 |
| Scripted open | `1.2` | 同・開指令 |
| `GRIPPER_CLOSE_THRESH` | `0.45` | sticky grasp の閉判定 |
| `GRIPPER_OPEN_THRESH` | `0.90` | 開判定 / パッド近傍解放ゲート |

これらはすべてラジアンである。0–100 スケールに直すと closed ≈ 9%、open(1.2) ≈ 72% 程度になる（契約上下限への線形写像）。

## 評価のヨー

`compute_pose_errors` は平面位置を mm、ヨー差をラジアン差分→度に変換して返す。`summarize()` は絶対値の平均・中央値を `mean_abs_yaw_error_deg` / `median_abs_yaw_error_deg` として出す。`scripts/run_sim_eval.py` 終了時にこれらを 1 行で表示する。

## 確認コマンド

```bash
python -c "from port_pick_align.units import describe_unit_conventions; import json; print(json.dumps(describe_unit_conventions(), indent=2))"
(cd port_pick_align && pytest -m unit tests/test_units.py -q)
```
