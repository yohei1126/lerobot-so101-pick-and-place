# Documentation index

Start with setup, then dataset → training → simulation; use hardware and bring-up when moving to the arm.

| Document | Scope |
| --- | --- |
| [setup.md](setup.en.md) | Docker and host Python setup; contract config overview |
| [dataset.md](dataset.en.md) | Test rosbag2 generation, synthetic data, MuJoCo expert collection, LeRobotDataset conversion and QA |
| [training.md](training.en.md) | ACT training, checkpoints, and inference smoke checks |
| [act_so101_trial_smoke_20261019.md](act_so101_trial_smoke_20261019.en.md) | ACT smoke training on real trial3 datasets (2026-10-19, facts) |
| [real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.en.md) | Real pick-sponge main (clean28) dataset summary and overnight ACT notes (2026-10-23, facts) |
| [ros2_inference.md](ros2_inference.en.md) | ROS 2 Humble nodes, mock inference, Rerun visualization |
| [simulation.md](simulation.en.md) | MuJoCo closed-loop eval, interactive viewer, video export |
| [evaluation.md](evaluation.en.md) | Planar position / yaw / success aggregation (`eval_alignment`) API |
| [units.md](units.en.md) | Sim/contract radians vs real LeRobot degrees and gripper 0–100 |
| [sim_to_real_act.md](sim_to_real_act.en.md) | Phase 2-2: sim-trained ACT on real SO-101 (dry-run / slow live) |
| [results/README.md](results/README.en.md) | Closed-loop eval logs and pending placeholders (including post50) |
| [figures/README.md](figures/README.en.md) | Regenerating report figures (loss curve, histograms, initial XY, rollout) |
| [e2e.md](e2e.en.md) | End-to-end pipeline from data collection through inference |
| [hardware.md](hardware.en.md) | SO-ARM101 / Feetech udev, connection dry-run, sim-aligned workspace, purchased gear |
| [real_robot_bringup.md](real_robot_bringup.en.md) | Mac / LeRobot 0.6.1 SO-101 Leader/Follower bring-up, table layout, demo recording (`scripts/record_real_so101.sh`) |
| [real_robot_deploy.md](real_robot_deploy.en.md) | Real-trained ACT / SmolVLA dry-run → live (no unit conversion; safety clamps) |
| [ci.md](ci.en.md) | GitHub Actions CI and local lint/test |
| [submission.md](submission.en.md) | OmniCampus deliverables (PDF report, GitHub, YouTube) and checklist |
| [plan_b.md](plan_b.en.md) | Degraded operation with simulation and public data when hardware fails |
