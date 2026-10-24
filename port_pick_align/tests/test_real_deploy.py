"""CPU-only unit tests for real-robot deploy helpers (no hardware / cameras / MPS)."""

from __future__ import annotations

import argparse
import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from port_pick_align.deploy import act_real
from port_pick_align.deploy import real_common as rc
from port_pick_align.deploy.real_common import Clamp, action_dict, add_common_args, is_live


@pytest.mark.unit
def test_clamp_limits_arm_and_gripper() -> None:
    clamp = Clamp(max_deg=2.0, max_grip=3.0)
    state = np.zeros(6, dtype=np.float32)
    target = np.array([10.0, -10.0, 0.0, 0.0, 0.0, 50.0], dtype=np.float32)
    out = clamp(target, state)
    assert out[0] == pytest.approx(2.0)
    assert out[1] == pytest.approx(-2.0)
    assert out[5] == pytest.approx(3.0)
    # Second step uses last commanded target as reference.
    out2 = clamp(np.array([20.0, 0, 0, 0, 0, 100.0], dtype=np.float32), state)
    assert out2[0] == pytest.approx(4.0)
    assert out2[5] == pytest.approx(6.0)


@pytest.mark.unit
def test_clamp_disables_when_nonpositive() -> None:
    clamp = Clamp(max_deg=0.0, max_grip=-1.0)
    state = np.zeros(6, dtype=np.float32)
    target = np.array([40.0, -40.0, 1.0, 2.0, 3.0, 90.0], dtype=np.float32)
    out = clamp(target, state)
    assert out[:5] == pytest.approx(target[:5])
    assert out[5] == pytest.approx(90.0)


@pytest.mark.unit
def test_clamp_gripper_stays_in_0_100() -> None:
    clamp = Clamp(max_deg=50.0, max_grip=50.0)
    state = np.array([0, 0, 0, 0, 0, 95.0], dtype=np.float32)
    out = clamp(np.array([0, 0, 0, 0, 0, 200.0], dtype=np.float32), state)
    assert out[5] == pytest.approx(100.0)
    out2 = clamp(np.array([0, 0, 0, 0, 0, -50.0], dtype=np.float32), state)
    assert out2[5] == pytest.approx(50.0)  # from last=100 with grip cap 50 → 50, then clip


@pytest.mark.unit
def test_action_dict_uses_pos_keys() -> None:
    vec = np.arange(6, dtype=np.float32)
    d = action_dict(vec)
    assert list(d) == [f"{j}.pos" for j in rc.JOINTS]
    assert d["gripper.pos"] == pytest.approx(5.0)


@pytest.mark.unit
def test_common_args_default_is_dry_run() -> None:
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    args = ap.parse_args([])
    assert args.live is False
    assert args.dry_run is False
    assert is_live(args) is False
    assert args.max_delta_deg == pytest.approx(3.0)
    assert args.max_delta_gripper == pytest.approx(5.0)
    assert args.top_index == 1
    assert args.wrist_index == 0


@pytest.mark.unit
def test_common_args_live_and_exclusive() -> None:
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    live_args = ap.parse_args(["--live"])
    assert is_live(live_args) is True
    both = ap.parse_args(["--live", "--dry-run"])
    with pytest.raises(SystemExit, match="exclusive"):
        is_live(both)


@pytest.mark.unit
def test_act_real_parse_defaults() -> None:
    args = act_real.parse_args([])
    assert args.live is False
    assert args.offline_check is False
    assert args.n_action_steps == 10
    assert args.device == "mps"


@pytest.mark.unit
def test_hw_root_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEROBOT_HW_ROOT", str(tmp_path / "hw"))
    assert rc.hw_root() == tmp_path / "hw"
    monkeypatch.setenv("LEROBOT_LOG_DIR", str(tmp_path / "logs"))
    assert rc.log_dir() == tmp_path / "logs"


@pytest.mark.unit
def test_dry_run_never_calls_send_action(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeBus:
        def __init__(self) -> None:
            self.connected = False
            self.disconnect_kwargs: dict | None = None

        def connect(self) -> None:
            self.connected = True

        def disconnect(self, disable_torque: bool = True) -> None:
            self.disconnect_kwargs = {"disable_torque": disable_torque}
            self.connected = False

    class FakeCam:
        def connect(self) -> None:
            return None

        def disconnect(self) -> None:
            return None

    class FakeRobot:
        def __init__(self) -> None:
            self.bus = FakeBus()
            self.cameras = {"top": FakeCam(), "wrist": FakeCam()}
            self.send_calls: list[dict] = []
            self.connect_calls = 0

        def connect(self) -> None:
            self.connect_calls += 1

        def disconnect(self) -> None:
            return None

        def get_observation(self) -> dict:
            obs = {f"{j}.pos": 0.0 for j in rc.JOINTS}
            obs["top"] = np.zeros((4, 4, 3), dtype=np.uint8)
            obs["wrist"] = np.zeros((4, 4, 3), dtype=np.uint8)
            return obs

        def send_action(self, action: dict) -> None:
            self.send_calls.append(action)

    fake = FakeRobot()

    def fake_build(args, live: bool):
        assert live is False
        fake.bus.connect()
        for cam in fake.cameras.values():
            cam.connect()
        return fake

    monkeypatch.setattr(rc, "build_robot", fake_build)
    monkeypatch.setattr(rc, "install_sigterm", lambda: None)

    args = SimpleNamespace(
        live=False,
        dry_run=False,
        max_delta_deg=3.0,
        max_delta_gripper=5.0,
        fps=100.0,
        episode_time_s=0.05,
        print_every=1,
        save_video=False,
    )

    def step_fn(obs, state):
        return np.ones(6, dtype=np.float32) * 5.0, "test"

    rc.run_loop(args, "unit", step_fn)
    assert fake.send_calls == []
    assert fake.connect_calls == 0
    assert fake.bus.disconnect_kwargs == {"disable_torque": False}


@pytest.mark.unit
def test_live_calls_send_action(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRobot:
        def __init__(self) -> None:
            self.send_calls: list[dict] = []
            self.disconnected = False

        def get_observation(self) -> dict:
            obs = {f"{j}.pos": float(i) for i, j in enumerate(rc.JOINTS)}
            obs["top"] = np.zeros((2, 2, 3), dtype=np.uint8)
            obs["wrist"] = np.zeros((2, 2, 3), dtype=np.uint8)
            return obs

        def send_action(self, action: dict) -> None:
            self.send_calls.append(action)

        def disconnect(self) -> None:
            self.disconnected = True

    fake = FakeRobot()
    monkeypatch.setattr(rc, "build_robot", lambda args, live: fake)
    monkeypatch.setattr(rc, "install_sigterm", lambda: None)

    args = SimpleNamespace(
        live=True,
        dry_run=False,
        max_delta_deg=100.0,
        max_delta_gripper=100.0,
        fps=200.0,
        episode_time_s=0.03,
        print_every=99,
        save_video=False,
    )
    target = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], dtype=np.float32)
    rc.run_loop(args, "unit_live", lambda obs, st: (target, "ok"))
    assert len(fake.send_calls) >= 1
    assert "shoulder_pan.pos" in fake.send_calls[0]
    assert fake.disconnected is True


@pytest.mark.unit
def test_act_real_does_not_apply_sim_conversion() -> None:
    """ACT real runner must not import / call sim rad↔deg conversion helpers."""
    src_path = Path(inspect.getsourcefile(act_real))
    assert src_path is not None
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            for alias in node.names:
                imported.add(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    forbidden = {
        "port_pick_align.deploy.conversion",
        "port_pick_align.deploy.sim_policy_wrapper",
        "port_pick_align.deploy.run_sim_policy_on_real",
    }
    assert not (imported & forbidden), f"unexpected sim-deploy imports: {imported & forbidden}"
    # Source must document / avoid sim conversion keywords in call sites.
    source = src_path.read_text(encoding="utf-8")
    assert "sim_action_to_real" not in source
    assert "real_joints_to_sim" not in source
    assert "np.radians" not in source
    assert "np.degrees" not in source


@pytest.mark.unit
def test_act_predict_chunk_passes_state_without_unit_change() -> None:
    """State fed to the policy must stay in real units (no rad conversion)."""
    import torch

    captured: dict = {}

    class FakePolicy:
        def predict_action_chunk(self, batch):
            captured["batch"] = batch
            return torch.zeros(1, 4, 6, dtype=torch.float32)

    state = np.array([10.0, -20.0, 30.0, -5.0, 1.0, 40.0], dtype=np.float32)
    top = np.zeros((8, 8, 3), dtype=np.uint8)
    wrist = np.ones((8, 8, 3), dtype=np.uint8) * 128

    out = act_real.predict_chunk(FakePolicy(), top, wrist, state, "cpu")
    assert out.shape == (4, 6)
    fed = captured["batch"]["observation.state"].detach().cpu().numpy().reshape(-1)
    assert fed == pytest.approx(state, abs=1e-5)
