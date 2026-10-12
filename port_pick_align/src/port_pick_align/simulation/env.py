"""Gymnasium MuJoCo tabletop env for SO-101-class pick-and-align."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from port_pick_align.contract import load_contract

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_MJCF = ASSETS_DIR / "so101_tabletop.xml"

JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)

# Home pose: arm over table, open gripper.
DEFAULT_HOME = np.array([0.0, -0.6, 0.9, 0.6, 0.0, 1.2], dtype=np.float32)
TABLE_Z = 0.42
BOX_HALF_Z = 0.02


class PickAlignSimEnv:
    """Closed-loop pick-and-align environment (Gymnasium-compatible API).

    Observation dict:
      - top / wrist: uint8 BGR ``(H, W, 3)``
      - state: float32 joint positions ``(6,)``
    Action: float32 target joint positions ``(6,)`` (position actuators).
    """

    metadata = {"render_modes": ["rgb_array"]}

    def __init__(
        self,
        *,
        contract: dict[str, Any] | None = None,
        mjcf_path: Path | str | None = None,
        control_hz: float = 30.0,
        render_width: int | None = None,
        render_height: int | None = None,
        max_episode_steps: int = 300,
    ) -> None:
        import mujoco

        self._mujoco = mujoco
        self.contract = contract if contract is not None else load_contract()
        cams = self.contract["cameras"]
        self.render_width = int(render_width or cams["top"]["width"])
        self.render_height = int(render_height or cams["top"]["height"])
        self.control_hz = float(control_hz)
        self.max_episode_steps = int(max_episode_steps)

        path = Path(mjcf_path) if mjcf_path is not None else DEFAULT_MJCF
        self.model = mujoco.MjModel.from_xml_path(str(path))
        self.data = mujoco.MjData(self.model)

        self._joint_qpos_addrs = [self.model.joint(name).qposadr[0] for name in JOINT_NAMES]
        self._joint_ids = [self.model.joint(name).id for name in JOINT_NAMES]
        self._act_ids = [self.model.actuator(f"act_{name}").id for name in JOINT_NAMES]
        self._box_body_id = self.model.body("box").id
        self._ee_site_id = self.model.site("ee_site").id
        self._target_site_id = self.model.site("target_site").id
        self._box_jnt_id = self.model.joint("box_free").id
        self._box_qpos_adr = self.model.jnt_qposadr[self._box_jnt_id]

        self._n_substeps = max(1, int(round(1.0 / (self.control_hz * self.model.opt.timestep))))
        self._top_renderer: Any | None = None
        self._wrist_renderer: Any | None = None
        self._step_count = 0
        self._rng = np.random.default_rng()

        limits = self.contract["robot"]["joint_limits"]
        self._limits = np.array(
            [[float(limits[n][0]), float(limits[n][1])] for n in JOINT_NAMES],
            dtype=np.float32,
        )

        # Gymnasium-style spaces (lazy; avoid hard import at module load for non-sim installs).
        self.observation_space: Any | None = None
        self.action_space: Any | None = None
        try:
            import gymnasium as gym
            from gymnasium import spaces

            self.observation_space = spaces.Dict(
                {
                    "top": spaces.Box(
                        0,
                        255,
                        (self.render_height, self.render_width, 3),
                        dtype=np.uint8,
                    ),
                    "wrist": spaces.Box(
                        0,
                        255,
                        (self.render_height, self.render_width, 3),
                        dtype=np.uint8,
                    ),
                    "state": spaces.Box(
                        self._limits[:, 0],
                        self._limits[:, 1],
                        (6,),
                        dtype=np.float32,
                    ),
                }
            )
            self.action_space = spaces.Box(
                self._limits[:, 0],
                self._limits[:, 1],
                (6,),
                dtype=np.float32,
            )
            self.spec = None
            _ = gym  # silence unused if only spaces used
        except ImportError:
            pass

    def close(self) -> None:
        for renderer in (self._top_renderer, self._wrist_renderer):
            if renderer is not None:
                renderer.close()
        self._top_renderer = None
        self._wrist_renderer = None

    def _ensure_renderers(self) -> None:
        if self._top_renderer is None:
            self._top_renderer = self._mujoco.Renderer(
                self.model, height=self.render_height, width=self.render_width
            )
        if self._wrist_renderer is None:
            self._wrist_renderer = self._mujoco.Renderer(
                self.model, height=self.render_height, width=self.render_width
            )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._mujoco.mj_resetData(self.model, self.data)
        self._step_count = 0

        home = DEFAULT_HOME.copy()
        if options and "home" in options:
            home = np.asarray(options["home"], dtype=np.float32).reshape(6)

        for i, adr in enumerate(self._joint_qpos_addrs):
            self.data.qpos[adr] = float(home[i])
            self.data.ctrl[self._act_ids[i]] = float(home[i])

        # Randomize box XY on table near default spawn.
        box_xy = np.array([0.28, -0.08], dtype=np.float64)
        if options is None or options.get("randomize_box", True):
            box_xy = box_xy + self._rng.uniform(-0.04, 0.04, size=2)
        box_z = TABLE_Z + 0.02 + BOX_HALF_Z
        box_yaw = float(self._rng.uniform(-0.3, 0.3))
        if options and "box_xy" in options:
            box_xy = np.asarray(options["box_xy"], dtype=np.float64).reshape(2)
        if options and "box_yaw" in options:
            box_yaw = float(options["box_yaw"])

        # freejoint qpos: x y z qw qx qy qz
        adr = self._box_qpos_adr
        half = np.cos(box_yaw / 2.0)
        qz = np.sin(box_yaw / 2.0)
        self.data.qpos[adr : adr + 7] = [box_xy[0], box_xy[1], box_z, half, 0.0, 0.0, qz]
        self.data.qvel[:] = 0.0

        self._mujoco.mj_forward(self.model, self.data)
        obs = self._get_obs()
        return obs, self._info()

    def step(
        self, action: np.ndarray
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        cmd = np.asarray(action, dtype=np.float32).reshape(6)
        clipped = np.clip(cmd, self._limits[:, 0], self._limits[:, 1]).astype(np.float32)
        for i, act_id in enumerate(self._act_ids):
            self.data.ctrl[act_id] = float(clipped[i])

        for _ in range(self._n_substeps):
            self._mujoco.mj_step(self.model, self.data)

        self._step_count += 1
        obs = self._get_obs()
        info = self._info()
        terminated = False
        truncated = self._step_count >= self.max_episode_steps
        reward = self._reward(info)
        return obs, reward, terminated, truncated, info

    def _joint_positions(self) -> np.ndarray:
        return np.array(
            [float(self.data.qpos[adr]) for adr in self._joint_qpos_addrs],
            dtype=np.float32,
        )

    def _render_camera(self, camera_name: str) -> np.ndarray:
        self._ensure_renderers()
        renderer = self._top_renderer if camera_name == "top" else self._wrist_renderer
        assert renderer is not None
        renderer.update_scene(self.data, camera=camera_name)
        rgb = renderer.render()
        # MuJoCo returns RGB; convert to BGR to match ROS / infer helpers.
        return np.ascontiguousarray(rgb[:, :, ::-1])

    def _get_obs(self) -> dict[str, np.ndarray]:
        return {
            "top": self._render_camera("top"),
            "wrist": self._render_camera("wrist"),
            "state": self._joint_positions(),
        }

    def box_pose(self) -> tuple[np.ndarray, float]:
        """Return (xy, yaw_rad) of the box body."""
        xpos = self.data.xpos[self._box_body_id].copy()
        xmat = self.data.xmat[self._box_body_id].reshape(3, 3)
        yaw = float(np.arctan2(xmat[1, 0], xmat[0, 0]))
        return xpos[:2].astype(np.float64), yaw

    def target_pose(self) -> tuple[np.ndarray, float]:
        xpos = self.data.site_xpos[self._target_site_id].copy()
        return xpos[:2].astype(np.float64), 0.0

    def ee_xy(self) -> np.ndarray:
        return np.asarray(self.data.site_xpos[self._ee_site_id][:2], dtype=np.float64).copy()

    def box_z(self) -> float:
        return float(self.data.xpos[self._box_body_id][2])

    def _info(self) -> dict[str, Any]:
        box_xy, box_yaw = self.box_pose()
        target_xy, target_yaw = self.target_pose()
        return {
            "box_xy": box_xy,
            "box_yaw": box_yaw,
            "box_z": self.box_z(),
            "target_xy": target_xy,
            "target_yaw": target_yaw,
            "ee_xy": self.ee_xy(),
            "table_z": TABLE_Z,
            "step": self._step_count,
        }

    def _reward(self, info: dict[str, Any]) -> float:
        dist = float(np.linalg.norm(info["box_xy"] - info["target_xy"]))
        return -dist

    def render(self) -> np.ndarray:
        return self._render_camera("top")
