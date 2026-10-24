# Document index

Technical documents under this directory are organized by area: environment setup, data pipeline, training, inference, simulation, and submission artifacts.

| Document | Scope and main content |
| --- | --- |
| [setup.md](setup.en.md) | Docker container and host Python virtualenv setup; overview of the contract config |
| [dataset.md](dataset.en.md) | Test rosbag2 generation, synthetic data, MuJoCo demonstration collection, conversion to LeRobotDataset, and quality validation |
| [training.md](training.en.md) | ACT model training, checkpoint saving, and inference smoke checks |
| [act_so101_trial_smoke_20261019.md](act_so101_trial_smoke_20261019.en.md) | ACT smoke training results on real-robot trial3 data (2026-10-19, factual record) |
| [ros2_inference.md](ros2_inference.en.md) | ROS 2 Humble node layout, mock inference pipeline, Rerun visualization integration |
| [simulation.md](simulation.en.md) | Closed-loop control evaluation in MuJoCo, interactive viewer, and video export |
| [evaluation.md](evaluation.en.md) | Planar position error, yaw error, and success-rate aggregation module (`eval_alignment`) API |
| [units.md](units.en.md) | Conversion between sim/contract radians and real-robot LeRobot degrees / gripper 0–100 |
| [sim_to_real_act.md](sim_to_real_act.en.md) | Phase 2-2: dry-run / low-speed live of sim-trained ACT on real SO-101 |
| [results/README.md](results/README.en.md) | Measured closed-loop evaluation logs and unmeasured placeholders (including post50 official) |
| [figures/README.md](figures/README.en.md) | Regenerating report figures (training curves, histograms, initial XY, rollouts) |
| [e2e.md](e2e.en.md) | End-to-end pipeline test from data collection through inference |
| [hardware.md](hardware.en.md) | SO-ARM101 and Feetech servo Linux udev setup, connection dry-run, sim-aligned work-area layout, purchased equipment |
| [real_robot_bringup.md](real_robot_bringup.en.md) | Real SO-101 Leader/Follower bring-up with Mac / LeRobot 0.6.1 (port ID, calibration, teleop, cameras) |
| [ci.md](ci.en.md) | GitHub Actions CI workflow layout and local static analysis / test procedure |
| [submission.md](submission.en.md) | OmniCampus submission specs (PDF report, GitHub, YouTube video) and checklist |
| [plan_b.md](plan_b.en.md) | Degraded operation using simulation and public data when the real robot is unavailable |
