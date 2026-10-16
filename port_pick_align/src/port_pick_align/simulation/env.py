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
# Gripper hinge does not pinch fingers; sticky attach approximates grasp when closed.
# Attach uses the measured joint so the grasp frame is the closed pose. Release
# uses the command and stays at OPEN: expert demos command 0.0 and 1.2, and a
# lower open threshold would also drop the box on a smeared carry command.
# Commands between CLOSE and OPEN keep the current grasp.
GRIPPER_CLOSE_THRESH = 0.45
GRIPPER_OPEN_THRESH = 0.90
# Attach only once the hinge is nearly shut. Attaching on the close command
# latches the box while the finger is still open, then the rest of the close
# twists it. 0.05 rad is the closed pose the yaw plan models.
GRIPPER_ATTACH_POS = 0.05
# Midpoint kept for dataset scans that split the binary expert commands.
GRIPPER_CLOSED_THRESH = GRIPPER_CLOSE_THRESH
ATTACH_XY_M = 0.12
ATTACH_Z_M = 0.15


def _wrap_pi(angle: float) -> float:
    """Wrap radians to ``(-pi, pi]``."""
    return float((float(angle) + np.pi) % (2.0 * np.pi) - np.pi)


def _yaw_from_matrix(rotation: np.ndarray) -> float:
    matrix = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    return float(np.arctan2(matrix[1, 0], matrix[0, 0]))


def box_reset_options(*, randomize_box: bool) -> dict[str, Any]:
    """Reset options for a fixed spawn or an unknown initial box pose.

    Randomization covers planar position and yaw. Passing ``box_yaw`` would pin
    the yaw, so the randomized path omits that key.
    """
    if randomize_box:
        return {"randomize_box": True}
    return {"randomize_box": False, "box_yaw": 0.0}


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
        render_cameras: bool = True,
        include_goal_in_state: bool = False,
    ) -> None:
        import mujoco

        self._mujoco = mujoco
        self.contract = contract if contract is not None else load_contract()
        cams = self.contract["cameras"]
        self.render_width = int(render_width or cams["top"]["width"])
        self.render_height = int(render_height or cams["top"]["height"])
        self.control_hz = float(control_hz)
        self.max_episode_steps = int(max_episode_steps)
        self.render_cameras = bool(render_cameras)
        # Off by default: the ACT contract state is 6 joint positions. The goal is
        # shown by the opaque pad. Set this to concatenate goal xy/yaw onto state.
        self.include_goal_in_state = bool(include_goal_in_state)

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
        self._box_qpos_adr = int(self.model.jnt_qposadr[self._box_jnt_id])
        self._box_dof_adr = int(self.model.jnt_dofadr[self._box_jnt_id])
        self._arm_dof_indices = [
            int(self.model.jnt_dofadr[self.model.joint(name).id]) for name in JOINT_NAMES[:5]
        ]

        self._n_substeps = max(1, int(round(1.0 / (self.control_hz * self.model.opt.timestep))))
        self._top_renderer: Any | None = None
        self._wrist_renderer: Any | None = None
        self._step_count = 0
        self._rng = np.random.default_rng()
        self._grasping = False
        self._grasp_offset: np.ndarray | None = None
        # Box rotation relative to the EE site at the moment of attachment.
        self._grasp_rot: np.ndarray | None = None
        self._box_placed = False
        self._placed_xy: np.ndarray | None = None

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

            state_low = self._limits[:, 0]
            state_high = self._limits[:, 1]
            if self.include_goal_in_state:
                state_low = np.concatenate([state_low, [-2.0, -2.0, -np.pi]])
                state_high = np.concatenate([state_high, [2.0, 2.0, np.pi]])
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
                        state_low.astype(np.float32),
                        state_high.astype(np.float32),
                        (int(state_low.shape[0]),),
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
        self._grasping = False
        self._grasp_offset = None
        self._grasp_rot = None
        self._box_placed = False
        self._placed_xy = None

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
        if options is not None and "box_yaw" in options:
            box_yaw = float(options["box_yaw"])
        elif options is not None and not options.get("randomize_box", True):
            box_yaw = 0.0
        else:
            box_yaw = float(self._rng.uniform(-0.3, 0.3))
        if options and "box_xy" in options:
            box_xy = np.asarray(options["box_xy"], dtype=np.float64).reshape(2)

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

        self._update_sticky_grasp(float(clipped[5]))
        if self._box_placed and self._placed_xy is not None:
            self._place_box_on_table(self._placed_xy)
        self._step_count += 1
        obs = self._get_obs()
        info = self._info()
        terminated = False
        truncated = self._step_count >= self.max_episode_steps
        reward = self._reward(info)
        return obs, reward, terminated, truncated, info

    def _ee_rotation_for_joints(self, joints: np.ndarray) -> np.ndarray:
        """End-effector rotation at ``joints``. Restores the simulator afterward."""
        qpos_bak = self.data.qpos.copy()
        qvel_bak = self.data.qvel.copy()
        try:
            commanded = np.asarray(joints, dtype=np.float64).reshape(6)
            for index, adr in enumerate(self._joint_qpos_addrs):
                self.data.qpos[adr] = float(commanded[index])
            self._mujoco.mj_forward(self.model, self.data)
            return self._ee_rotation().copy()
        finally:
            self.data.qpos[:] = qpos_bak
            self.data.qvel[:] = qvel_bak
            self._mujoco.mj_forward(self.model, self.data)

    def plan_transport_joints(
        self,
        grasp_xyz: np.ndarray,
        carry_xyz: np.ndarray,
        place_xyz: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return grasp, carry, and place joint targets with yaw-aligned wrists.

        The box orientation is locked to the gripper at attachment, so the wrist
        in the grasp target chooses that offset. Carry and place then share one
        wrist angle. The scripted policy commands these vectors directly: a fresh
        IK later in the episode would start from a different posture and miss the
        orientation this search measured. Joint limits leave about 16 deg on the
        worst spawn in the training randomization.
        """
        q_grasp = np.asarray(self.solve_ik(grasp_xyz), dtype=np.float64)
        q_carry = np.asarray(self.solve_ik(carry_xyz), dtype=np.float64)
        q_place = np.asarray(self.solve_ik(place_xyz), dtype=np.float64)
        box_rot = np.asarray(self.data.xmat[self._box_body_id], dtype=np.float64).reshape(3, 3)
        lo = float(self._limits[4, 0])
        hi = float(self._limits[4, 1])
        grid = np.linspace(lo, hi, 25)

        def rotation(base: np.ndarray, roll: float) -> np.ndarray:
            trial = np.array(base, dtype=np.float64, copy=True)
            trial[4] = float(roll)
            # The site sits on the gripper hinge. Measure the closed grip, which
            # is the angle latched at attachment and held through transport.
            trial[5] = 0.0
            return self._ee_rotation_for_joints(trial)

        grasp_rots = [rotation(q_grasp, float(roll)) for roll in grid]
        carry_rots = [rotation(q_carry, float(roll)) for roll in grid]
        place_rots = [rotation(q_place, float(roll)) for roll in grid]

        def score(pre_roll: float, transport_roll: float) -> float:
            relative = rotation(q_grasp, pre_roll).T @ box_rot
            carry_yaw = _yaw_from_matrix(rotation(q_carry, transport_roll) @ relative)
            place_yaw = _yaw_from_matrix(rotation(q_place, transport_roll) @ relative)
            return max(abs(_wrap_pi(carry_yaw)), abs(_wrap_pi(place_yaw)))

        best_score = float("inf")
        best_pre = float(grid[len(grid) // 2])
        best_roll = best_pre
        for i, pre in enumerate(grid):
            relative = grasp_rots[i].T @ box_rot
            for j, roll in enumerate(grid):
                carry_yaw = _yaw_from_matrix(carry_rots[j] @ relative)
                place_yaw = _yaw_from_matrix(place_rots[j] @ relative)
                candidate = max(abs(_wrap_pi(carry_yaw)), abs(_wrap_pi(place_yaw)))
                if candidate < best_score:
                    best_score = float(candidate)
                    best_pre = float(pre)
                    best_roll = float(roll)
        step = float(grid[1] - grid[0])
        for _ in range(4):
            step *= 0.5
            for d_pre, d_roll in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
                pre = float(np.clip(best_pre + d_pre, lo, hi))
                roll = float(np.clip(best_roll + d_roll, lo, hi))
                candidate = score(pre, roll)
                if candidate < best_score:
                    best_score = candidate
                    best_pre = pre
                    best_roll = roll

        def with_wrist(base: np.ndarray, roll: float) -> np.ndarray:
            joints = np.asarray(base, dtype=np.float32).reshape(6).copy()
            joints[4] = np.float32(roll)
            return joints

        return (
            with_wrist(q_grasp, best_pre),
            with_wrist(q_carry, best_roll),
            with_wrist(q_place, best_roll),
        )

    def retarget_transport_joints(
        self,
        carry_xyz: np.ndarray,
        place_xyz: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Re-aim carry and place wrists using the grasp that actually latched.

        The box can rotate slightly before the fingers finish closing, so the
        wrist chosen at spawn is no longer the one that faces the pad. Called
        once grasping is true. Carry and place still share one wrist.
        """
        if not self._grasping or self._grasp_rot is None:
            raise RuntimeError("retarget_transport_joints requires an active grasp")
        q_carry = np.asarray(self.solve_ik(carry_xyz), dtype=np.float64)
        q_place = np.asarray(self.solve_ik(place_xyz), dtype=np.float64)
        grasp_rot = np.asarray(self._grasp_rot, dtype=np.float64).reshape(3, 3)
        lo = float(self._limits[4, 0])
        hi = float(self._limits[4, 1])
        grid = np.linspace(lo, hi, 25)

        def rotation(base: np.ndarray, roll: float) -> np.ndarray:
            trial = np.array(base, dtype=np.float64, copy=True)
            trial[4] = float(roll)
            trial[5] = 0.0
            return self._ee_rotation_for_joints(trial)

        def yaw_error(base: np.ndarray, roll: float) -> float:
            yaw = _yaw_from_matrix(rotation(base, roll) @ grasp_rot)
            return abs(_wrap_pi(yaw))

        best_score = float("inf")
        best_roll = float(grid[len(grid) // 2])
        for roll in grid:
            candidate = max(yaw_error(q_carry, float(roll)), yaw_error(q_place, float(roll)))
            if candidate < best_score:
                best_score = candidate
                best_roll = float(roll)
        step = float(grid[1] - grid[0])
        for _ in range(4):
            step *= 0.5
            for delta in (step, -step):
                roll = float(np.clip(best_roll + delta, lo, hi))
                candidate = max(yaw_error(q_carry, roll), yaw_error(q_place, roll))
                if candidate < best_score:
                    best_score = candidate
                    best_roll = roll

        def with_wrist(base: np.ndarray) -> np.ndarray:
            joints = np.asarray(base, dtype=np.float32).reshape(6).copy()
            joints[4] = np.float32(best_roll)
            return joints

        return with_wrist(q_carry), with_wrist(q_place)

    def solve_ik(
        self,
        target_xyz: np.ndarray | list[float],
        *,
        n_iter: int = 25,
        step_size: float = 0.55,
        tol: float = 0.015,
    ) -> np.ndarray:
        """Jacobian IK for EE site (arm joints only). Restores qpos after solve."""
        target = np.asarray(target_xyz, dtype=np.float64).reshape(3)
        qpos_bak = self.data.qpos.copy()
        qvel_bak = self.data.qvel.copy()
        try:
            for _ in range(n_iter):
                self._mujoco.mj_forward(self.model, self.data)
                cur = np.asarray(self.data.site_xpos[self._ee_site_id], dtype=np.float64)
                err = target - cur
                if float(np.linalg.norm(err)) < tol:
                    break
                jacp = np.zeros((3, self.model.nv))
                self._mujoco.mj_jacSite(self.model, self.data, jacp, None, self._ee_site_id)
                j = jacp[:, self._arm_dof_indices]
                dq, _, _, _ = np.linalg.lstsq(j, err * step_size, rcond=None)
                for i, adr in enumerate(self._joint_qpos_addrs[:5]):
                    lo, hi = float(self._limits[i, 0]), float(self._limits[i, 1])
                    self.data.qpos[adr] = float(np.clip(self.data.qpos[adr] + float(dq[i]), lo, hi))
            self._mujoco.mj_forward(self.model, self.data)
            return self._joint_positions().copy()
        finally:
            self.data.qpos[:] = qpos_bak
            self.data.qvel[:] = qvel_bak
            self._mujoco.mj_forward(self.model, self.data)

    def _place_box_on_table(
        self,
        xy: np.ndarray | None = None,
        *,
        yaw: float = 0.0,
    ) -> None:
        """Snap box to table top at ``xy`` / ``yaw`` with zero velocity."""
        adr = self._box_qpos_adr
        if xy is None:
            xy = np.asarray(self.data.qpos[adr : adr + 2], dtype=np.float64)
        else:
            xy = np.asarray(xy, dtype=np.float64).reshape(2)
        half = float(np.cos(yaw / 2.0))
        qz = float(np.sin(yaw / 2.0))
        self.data.qpos[adr] = float(xy[0])
        self.data.qpos[adr + 1] = float(xy[1])
        self.data.qpos[adr + 2] = TABLE_Z + 0.02 + BOX_HALF_Z
        self.data.qpos[adr + 3 : adr + 7] = [half, 0.0, 0.0, qz]
        self.data.qvel[self._box_dof_adr : self._box_dof_adr + 6] = 0.0
        self._mujoco.mj_forward(self.model, self.data)

    def _ee_rotation(self) -> np.ndarray:
        return np.asarray(self.data.site_xmat[self._ee_site_id], dtype=np.float64).reshape(3, 3)

    def _box_near_ee(self) -> bool:
        ee = np.asarray(self.data.site_xpos[self._ee_site_id], dtype=np.float64)
        box = np.asarray(self.data.xpos[self._box_body_id], dtype=np.float64)
        return (
            float(np.linalg.norm(ee[:2] - box[:2])) <= ATTACH_XY_M
            and abs(float(ee[2] - box[2])) <= ATTACH_Z_M
        )

    def _begin_grasp(self) -> None:
        """Latch a rigid grasp: world XY tracks the EE, orientation stays on the gripper."""
        ee_mat = self._ee_rotation()
        box_mat = np.asarray(self.data.xmat[self._box_body_id], dtype=np.float64).reshape(3, 3)
        self._grasping = True
        # Zero XY offset so the box center follows the IK target. Z is just under the tip.
        self._grasp_offset = np.array([0.0, 0.0, -0.02], dtype=np.float64)
        self._grasp_rot = ee_mat.T @ box_mat

    def _stick_box_to_ee(self) -> None:
        assert self._grasp_offset is not None and self._grasp_rot is not None
        ee = np.asarray(self.data.site_xpos[self._ee_site_id], dtype=np.float64)
        new_pos = ee + self._grasp_offset
        new_rot = self._ee_rotation() @ self._grasp_rot
        quat = np.zeros(4, dtype=np.float64)
        self._mujoco.mju_mat2Quat(quat, np.ascontiguousarray(new_rot, dtype=np.float64).reshape(9))
        adr = self._box_qpos_adr
        self.data.qpos[adr : adr + 3] = new_pos
        self.data.qpos[adr + 3 : adr + 7] = quat
        self.data.qvel[self._box_dof_adr : self._box_dof_adr + 6] = 0.0
        self._mujoco.mj_forward(self.model, self.data)

    def _release_grasp(self) -> None:
        """Place on the pad when close; otherwise set the box down where it is."""
        target_xy = np.asarray(self.data.site_xpos[self._target_site_id][:2], dtype=np.float64)
        box_xy = np.asarray(self.data.xpos[self._box_body_id][:2], dtype=np.float64)
        place_xy = (
            target_xy.copy() if float(np.linalg.norm(box_xy - target_xy)) < 0.10 else box_xy.copy()
        )
        self._place_box_on_table(place_xy)
        self._box_placed = True
        self._placed_xy = place_xy
        self._grasping = False
        self._grasp_offset = None
        self._grasp_rot = None

    def _update_sticky_grasp(self, gripper_cmd: float) -> None:
        """Attach once the joint has closed; keep holding until the command is open."""
        if self._grasping:
            if gripper_cmd >= GRIPPER_OPEN_THRESH:
                self._release_grasp()
                return
            self._stick_box_to_ee()
            return

        gripper_pos = float(self._joint_positions()[5])
        if gripper_pos > GRIPPER_ATTACH_POS or not self._box_near_ee():
            return
        self._begin_grasp()
        self._stick_box_to_ee()

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
        if self.render_cameras:
            top = self._render_camera("top")
            wrist = self._render_camera("wrist")
        else:
            h, w = self.render_height, self.render_width
            top = np.zeros((h, w, 3), dtype=np.uint8)
            wrist = np.zeros((h, w, 3), dtype=np.uint8)
        state = self._joint_positions()
        if self.include_goal_in_state:
            goal_xy, goal_yaw = self.target_pose()
            state = np.concatenate(
                [state, np.array([goal_xy[0], goal_xy[1], goal_yaw], dtype=np.float32)]
            ).astype(np.float32)
        return {
            "top": top,
            "wrist": wrist,
            "state": state,
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
            "grasping": self._grasping,
        }

    def _reward(self, info: dict[str, Any]) -> float:
        dist = float(np.linalg.norm(info["box_xy"] - info["target_xy"]))
        return -dist

    def render(self) -> np.ndarray:
        return self._render_camera("top")
