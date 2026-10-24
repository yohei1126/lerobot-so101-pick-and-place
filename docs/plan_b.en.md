# Plan B: degraded operation when hardware is delayed or broken

When the real-robot environment (Plan A: SO-ARM101 and tabletop mock) cannot run, use simulation and public datasets to still meet evaluation requirements.

## Switch criteria

If hardware is not working as of 2026-10-23 (Fri), follow this decision flow and move to Plan B:

```text
Real robot available? ──yes──▶ Plan A (real grasp/align + execution video)
                      └──no──▶ Plan B (simulation / public data + RobOps verification)
```

## Alternate paths, RobOps proof, and report chapters

### 1. Task execution environment and data path

As a substitute for real-robot motion, present task results via one or both of the following:

| Alternate path | What it verifies | Procedure |
| --- | --- | --- |
| MuJoCo simulator | Closed-loop control and metrics in the tabletop grasp/align scene | [simulation.md](simulation.en.md) (output: `outputs/eval/sim_rollout.mp4`) |
| LeRobot public datasets | ACT training and inference smoke on public data such as SO-100 | [training.md](training.en.md) · [dataset.md](dataset.en.md) |

Example MuJoCo evaluation video export:

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,dev]"
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun
# Output: outputs/eval/sim_rollout.mp4
```

### 2. Demonstrating RobOps pipeline verifiability

Even without a real robot, verify that the software pipeline runs against the contract and document that in the materials:

- rosbag2 → LeRobot conversion ([dataset.md](dataset.en.md))
- Quality validator for timestamp sync and frame dropouts
- Continuous integration via GitHub Actions ([ci.md](ci.en.md))
- Strict I/O management via `configs/contract.yaml`

### 3. Report narrative policy

Per course policy, hardware trouble or failed runs can still be evaluated if you document root-cause analysis, operational reflections, and technical discussion:

- Chapter 5: replace quantitative eval with simulation or public-data results, and state clearly that this is Plan B degraded verification.
- Chapter 6: organize hardware delay/failure status, why the alternate method was chosen, and what was learned technically.
- Chapter 8: combine simulation footage with RobOps (Rerun trajectory views, CI logs) in the presentation video.

Report draft: [PhysicalAI-Applied1-202609 in utokyo-ai-courses](https://github.com/yohei1126/utokyo-ai-courses/tree/main/PhysicalAI-Applied1-202609) ([`説明資料_PAI最終課題_yohei1126.en.md`](https://github.com/yohei1126/utokyo-ai-courses/blob/main/PhysicalAI-Applied1-202609/説明資料_PAI最終課題_yohei1126.en.md))

## Related docs

- Overall submission requirements: [submission.md](https://github.com/yohei1126/utokyo-ai-courses/blob/main/PhysicalAI-Applied1-202609/report/submission.en.md)
- Alignment evaluation API: [evaluation.md](evaluation.en.md)
