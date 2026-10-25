"""Real SO-101 table layout (Issue #90) and the map into the sim frame.

Source of truth: measured 2026-10-26 ~00:36 SGT. This supersedes the
2026-10-25 ~23:28 measurements and the 2026-10-22 figures.

``so101_tabletop.xml`` still implements an older simplified scene (70×60 cm
table, nadir camera, small box and pad). Do not read those geom positions as
the real table. Bring-up, live eval, and any future sim align use this module.
"""

from __future__ import annotations

from dataclasses import dataclass

# Measured 2026-10-26. Distances are centimetres.
TABLE_WIDTH_CM = 140.0
TABLE_DEPTH_CM = 70.0

# Both edges of each base are recorded. left + right is not the table width:
# the two numbers are opposite sides of the base, not one point.
LEADER_FROM_LEFT_CM = 27.0
LEADER_FROM_RIGHT_CM = 101.0
# The 2026-10-26 note writes this left distance as approximately 68 cm.
FOLLOWER_FROM_LEFT_CM = 68.0
FOLLOWER_FROM_LEFT_IS_APPROXIMATE = True
FOLLOWER_FROM_RIGHT_CM = 61.0

PAPER_FROM_RIGHT_CM = 69.0
PAPER_FROM_FRONT_CM = 27.0
PAPER_WIDTH_CM = 20.0
PAPER_DEPTH_CM = 30.0

SPONGE_FROM_RIGHT_CM = 54.0
SPONGE_FROM_FRONT_CM = 44.0
SPONGE_WIDTH_CM = 6.0
SPONGE_DEPTH_CM = 11.0

# Clamped on the table's right edge. Aimed so paper, sponge, and the follower
# are in frame. Height and tilt were not part of this remeasure.
TOP_CAMERA_FROM_RIGHT_CM = 0.0
TOP_CAMERA_FROM_FRONT_CM = 16.0

# After the 2026-10-25 cable swap; still current on 2026-10-26.
OPENCV_WRIST_INDEX = 0
OPENCV_TOP_INDEX = 1

SOT_ID = "2026-10-26"
SOT_ISSUE = 90


@dataclass(frozen=True)
class TablePoint:
    """One reference point in table coordinates and in the sim frame.

    Table axes (centimetres):
        ``u_cm`` is from the left edge toward the right (0 .. width).
        ``v_cm`` is from the front edge toward the back (0 .. depth).

    Sim frame (centimetres), same axis directions as the MuJoCo arm base:
        origin is the follower-base midpoint on the front edge.
        ``x_cm`` is forward (increasing ``v``), away from the front edge.
        ``y_cm`` is left (decreasing ``u``).
    """

    name: str
    u_cm: float
    v_cm: float
    x_cm: float
    y_cm: float

    @property
    def x_m(self) -> float:
        return self.x_cm / 100.0

    @property
    def y_m(self) -> float:
        return self.y_cm / 100.0


def u_from_right(from_right_cm: float) -> float:
    """Convert a distance from the right edge into ``u`` (from the left)."""
    return TABLE_WIDTH_CM - from_right_cm


def base_span_u(from_left_cm: float, from_right_cm: float) -> tuple[float, float, float]:
    """Return ``(u_left, u_right, u_mid)`` for a base measured from both edges.

    ``from_left`` is the left side of the base. ``from_right`` is the right
    side. The midpoint is the sim-frame reference for that base. It is implied
    by the two edge measurements, not a separately measured center.
    """
    u_left = from_left_cm
    u_right = u_from_right(from_right_cm)
    if u_right < u_left:
        raise ValueError(
            f"base span is empty: from_left={from_left_cm}, from_right={from_right_cm}"
        )
    return u_left, u_right, (u_left + u_right) / 2.0


def follower_origin_uv() -> tuple[float, float]:
    """Sim-frame origin in table coordinates ``(u, v)``.

    Lateral: midpoint of the follower span (~68 cm from the left, 61 cm from
    the right). Forward: the front edge (``v = 0``). The 2026-10-26 note does
    not remeasure a front offset for the bases; they stay clamped on the front
    edge. An inset measured later would add the same constant to every ``x``
    and would not change ``y``.
    """
    _, _, u_mid = base_span_u(FOLLOWER_FROM_LEFT_CM, FOLLOWER_FROM_RIGHT_CM)
    return u_mid, 0.0


def to_sim_frame(u_cm: float, v_cm: float) -> tuple[float, float]:
    """Map a table point to sim-frame centimetres ``(x, y)``."""
    u0, v0 = follower_origin_uv()
    return v_cm - v0, u0 - u_cm


def _point(name: str, u_cm: float, v_cm: float) -> TablePoint:
    x_cm, y_cm = to_sim_frame(u_cm, v_cm)
    return TablePoint(name=name, u_cm=u_cm, v_cm=v_cm, x_cm=x_cm, y_cm=y_cm)


def layout_points() -> dict[str, TablePoint]:
    """Reference points for the 2026-10-26 source of truth.

    Paper, sponge, and the top camera use the measured (from-right, from-front)
    point. The issue records that point and the portrait size; it does not say
    the point is a corner. Leader and follower entries are span midpoints.
    """
    _, _, leader_u = base_span_u(LEADER_FROM_LEFT_CM, LEADER_FROM_RIGHT_CM)
    _, _, follower_u = base_span_u(FOLLOWER_FROM_LEFT_CM, FOLLOWER_FROM_RIGHT_CM)
    return {
        "leader_mid": _point("leader_mid", leader_u, 0.0),
        "follower_origin": _point("follower_origin", follower_u, 0.0),
        "paper": _point(
            "paper",
            u_from_right(PAPER_FROM_RIGHT_CM),
            PAPER_FROM_FRONT_CM,
        ),
        "sponge": _point(
            "sponge",
            u_from_right(SPONGE_FROM_RIGHT_CM),
            SPONGE_FROM_FRONT_CM,
        ),
        "top_camera": _point(
            "top_camera",
            u_from_right(TOP_CAMERA_FROM_RIGHT_CM),
            TOP_CAMERA_FROM_FRONT_CM,
        ),
    }
