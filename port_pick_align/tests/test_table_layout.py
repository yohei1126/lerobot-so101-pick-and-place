"""Issue #90 table layout: measured 2026-10-26 distances and the sim-frame map."""

from __future__ import annotations

import pytest

from port_pick_align.simulation.table_layout import (
    FOLLOWER_FROM_LEFT_CM,
    FOLLOWER_FROM_LEFT_IS_APPROXIMATE,
    FOLLOWER_FROM_RIGHT_CM,
    LEADER_FROM_LEFT_CM,
    LEADER_FROM_RIGHT_CM,
    OPENCV_TOP_INDEX,
    OPENCV_WRIST_INDEX,
    PAPER_DEPTH_CM,
    PAPER_FROM_FRONT_CM,
    PAPER_FROM_RIGHT_CM,
    PAPER_WIDTH_CM,
    SPONGE_DEPTH_CM,
    SPONGE_FROM_FRONT_CM,
    SPONGE_FROM_RIGHT_CM,
    SPONGE_WIDTH_CM,
    TABLE_DEPTH_CM,
    TABLE_WIDTH_CM,
    TOP_CAMERA_FROM_FRONT_CM,
    TOP_CAMERA_FROM_RIGHT_CM,
    base_span_u,
    layout_points,
    to_sim_frame,
    u_from_right,
)

pytestmark = pytest.mark.unit


def test_sot_distances_match_issue_90() -> None:
    assert TABLE_WIDTH_CM == 140.0
    assert TABLE_DEPTH_CM == 70.0
    assert LEADER_FROM_LEFT_CM == 27.0
    assert LEADER_FROM_RIGHT_CM == 101.0
    assert FOLLOWER_FROM_LEFT_CM == 68.0
    assert FOLLOWER_FROM_LEFT_IS_APPROXIMATE is True
    assert FOLLOWER_FROM_RIGHT_CM == 61.0
    assert TOP_CAMERA_FROM_RIGHT_CM == 0.0
    assert TOP_CAMERA_FROM_FRONT_CM == 16.0
    assert (PAPER_FROM_RIGHT_CM, PAPER_FROM_FRONT_CM) == (69.0, 27.0)
    assert (PAPER_WIDTH_CM, PAPER_DEPTH_CM) == (20.0, 30.0)
    assert (SPONGE_FROM_RIGHT_CM, SPONGE_FROM_FRONT_CM) == (54.0, 44.0)
    assert (SPONGE_WIDTH_CM, SPONGE_DEPTH_CM) == (6.0, 11.0)
    assert OPENCV_WRIST_INDEX == 0
    assert OPENCV_TOP_INDEX == 1


def test_sim_frame_uses_follower_midpoint_and_front_edge() -> None:
    points = layout_points()
    origin = points["follower_origin"]
    assert origin.u_cm == pytest.approx(73.5)
    assert origin.v_cm == 0.0
    assert (origin.x_cm, origin.y_cm) == pytest.approx((0.0, 0.0))

    # Implied spans: opposite edges, not a single measured point.
    assert base_span_u(LEADER_FROM_LEFT_CM, LEADER_FROM_RIGHT_CM) == pytest.approx(
        (27.0, 39.0, 33.0)
    )
    assert base_span_u(FOLLOWER_FROM_LEFT_CM, FOLLOWER_FROM_RIGHT_CM) == pytest.approx(
        (68.0, 79.0, 73.5)
    )

    paper = points["paper"]
    assert paper.u_cm == pytest.approx(u_from_right(69.0))
    assert (paper.x_cm, paper.y_cm) == pytest.approx((27.0, 2.5))
    assert (paper.x_m, paper.y_m) == pytest.approx((0.27, 0.025))

    sponge = points["sponge"]
    assert (sponge.u_cm, sponge.v_cm) == pytest.approx((86.0, 44.0))
    assert (sponge.x_cm, sponge.y_cm) == pytest.approx((44.0, -12.5))
    assert (sponge.x_m, sponge.y_m) == pytest.approx((0.44, -0.125))

    camera = points["top_camera"]
    assert (camera.u_cm, camera.v_cm) == pytest.approx((140.0, 16.0))
    assert (camera.x_cm, camera.y_cm) == pytest.approx((16.0, -66.5))
    assert (camera.x_m, camera.y_m) == pytest.approx((0.16, -0.665))

    leader = points["leader_mid"]
    assert (leader.x_cm, leader.y_cm) == pytest.approx((0.0, 40.5))
    assert to_sim_frame(leader.u_cm, leader.v_cm) == pytest.approx((leader.x_cm, leader.y_cm))
