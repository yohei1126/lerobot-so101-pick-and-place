#!/usr/bin/env python3
"""Draw the current SO-101 table layout into ``docs/images/``.

The figure is the 2026-10-26 source of truth (Issue #90), mapped from table-edge
measurements. It replaces the pre-2026-10-26 simplified MuJoCo guide. The old
figure is kept as ``so101_layout_guide_superseded_pre_20261026``.

    python scripts/draw_layout_guide.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "port_pick_align" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from port_pick_align.simulation.table_layout import (
    FOLLOWER_FROM_LEFT_CM,
    FOLLOWER_FROM_RIGHT_CM,
    LEADER_FROM_LEFT_CM,
    LEADER_FROM_RIGHT_CM,
    OPENCV_TOP_INDEX,
    OPENCV_WRIST_INDEX,
    PAPER_DEPTH_CM,
    PAPER_WIDTH_CM,
    SPONGE_DEPTH_CM,
    SPONGE_WIDTH_CM,
    TABLE_DEPTH_CM,
    TABLE_WIDTH_CM,
    TOP_CAMERA_FROM_FRONT_CM,
    base_span_u,
    layout_points,
)

OUT_DIR = REPO_ROOT / "docs" / "images"


def draw() -> tuple[Path, Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, Rectangle

    points = layout_points()
    paper = points["paper"]
    sponge = points["sponge"]
    camera = points["top_camera"]
    leader_left, leader_right, _ = base_span_u(
        LEADER_FROM_LEFT_CM, LEADER_FROM_RIGHT_CM
    )
    follower_left, follower_right, _ = base_span_u(
        FOLLOWER_FROM_LEFT_CM, FOLLOWER_FROM_RIGHT_CM
    )

    fig = plt.figure(figsize=(16, 10))
    ax = fig.add_axes((0.05, 0.08, 0.60, 0.78))
    note = fig.add_axes((0.66, 0.06, 0.32, 0.86))
    note.axis("off")

    ax.add_patch(
        Rectangle(
            (0, 0),
            TABLE_WIDTH_CM,
            TABLE_DEPTH_CM,
            fc="#f4efe4",
            ec="#7a5c3a",
            lw=2,
            zorder=0,
        )
    )
    # Bases sit on the front edge. The drawn thickness is only so the span is visible.
    ax.add_patch(
        Rectangle(
            (leader_left, 0),
            leader_right - leader_left,
            6,
            fc="#3f6fbf",
            ec="k",
            zorder=2,
        )
    )
    ax.add_patch(
        Rectangle(
            (follower_left, 0),
            follower_right - follower_left,
            6,
            fc="#1f4e79",
            ec="k",
            zorder=2,
        )
    )
    ax.add_patch(
        Rectangle(
            (paper.u_cm - PAPER_WIDTH_CM / 2, paper.v_cm - PAPER_DEPTH_CM / 2),
            PAPER_WIDTH_CM,
            PAPER_DEPTH_CM,
            fc="#f7f7f7",
            ec="#444",
            lw=1.5,
            zorder=2,
        )
    )
    ax.add_patch(
        Rectangle(
            (sponge.u_cm - SPONGE_WIDTH_CM / 2, sponge.v_cm - SPONGE_DEPTH_CM / 2),
            SPONGE_WIDTH_CM,
            SPONGE_DEPTH_CM,
            fc="#e0b000",
            ec="k",
            lw=1.2,
            zorder=3,
        )
    )
    ax.plot(camera.u_cm, camera.v_cm, marker="X", ms=14, color="purple", zorder=4)
    aim = FancyArrowPatch(
        (camera.u_cm - 2, camera.v_cm + 1),
        ((paper.u_cm + sponge.u_cm) / 2, (paper.v_cm + sponge.v_cm) / 2),
        arrowstyle="-|>",
        mutation_scale=14,
        color="purple",
        lw=1.4,
        linestyle="--",
        zorder=1,
    )
    ax.add_patch(aim)

    ax.text(
        (leader_left + leader_right) / 2,
        8,
        "Leader base\n27 cm from left\n101 cm from right\n5V",
        ha="center",
        va="bottom",
        fontsize=8,
        color="#1d3557",
    )
    ax.text(
        (follower_left + follower_right) / 2,
        8,
        "Follower base\n~68 cm from left\n61 cm from right\n12V",
        ha="center",
        va="bottom",
        fontsize=8,
        color="#1d3557",
    )
    ax.annotate(
        "Paper (goal)\n69 cm from right\n27 cm from front\nportrait 20×30 cm",
        (paper.u_cm, paper.v_cm),
        (paper.u_cm - 28, paper.v_cm + 8),
        fontsize=8,
        arrowprops={"arrowstyle": "->", "color": "#333"},
    )
    ax.annotate(
        "Sponge\n54 cm from right\n44 cm from front\nportrait 6×11 cm",
        (sponge.u_cm, sponge.v_cm),
        (sponge.u_cm + 6, sponge.v_cm + 8),
        fontsize=8,
        arrowprops={"arrowstyle": "->", "color": "#333"},
    )
    ax.annotate(
        "Top camera C920\nright edge, 16 cm from front\naimed at paper + sponge + follower",
        (camera.u_cm, camera.v_cm),
        (camera.u_cm - 46, camera.v_cm + 18),
        fontsize=8,
        color="purple",
        arrowprops={"arrowstyle": "->", "color": "purple"},
    )
    ax.text(
        TABLE_WIDTH_CM / 2,
        -6,
        "front edge",
        ha="center",
        va="top",
        fontsize=9,
    )
    ax.text(
        TABLE_WIDTH_CM / 2, TABLE_DEPTH_CM + 2, "back edge", ha="center", fontsize=9
    )
    ax.set_xlim(-8, TABLE_WIDTH_CM + 8)
    ax.set_ylim(-12, TABLE_DEPTH_CM + 10)
    ax.set_aspect("equal")
    ax.set_xlabel("from left edge [cm]")
    ax.set_ylabel("from front edge [cm]")
    ax.set_title(
        "SO-101 table layout — source of truth 2026-10-26 (Issue #90)\n"
        "140 cm wide × 70 cm deep. Footprints are centered on the measured point.",
        fontsize=12,
    )
    ax.grid(alpha=0.25)

    leader = points["leader_mid"]
    body = f"""Current layout (2026-10-26 ~00:36 SGT)
Table {TABLE_WIDTH_CM:.0f} × {TABLE_DEPTH_CM:.0f} cm.
Supersedes 2026-10-25 ~23:28 and 2026-10-22.

Sim frame
Origin: follower midpoint on the front edge.
+x forward (into the table), +y left.
Front offset of the bases was not remeasured (v = 0).

Item                  sim (x, y) cm
Leader midpoint       ({leader.x_cm:.1f}, {leader.y_cm:.1f})
Follower origin       (0, 0)
Paper point           ({paper.x_cm:.1f}, {paper.y_cm:.1f})
Sponge point          ({sponge.x_cm:.1f}, {sponge.y_cm:.1f})
Top camera            ({camera.x_cm:.1f}, {camera.y_cm:.1f})

Metres: divide by 100.
Code: simulation/table_layout.py

Cameras
Wrist on the follower gripper.
OpenCV wrist={OPENCV_WRIST_INDEX}, top={OPENCV_TOP_INDEX}
(2026-10-25 cable swap, still current).
Top camera is {TOP_CAMERA_FROM_FRONT_CM:.0f} cm from the front
on the right edge. Height was not remeasured.

Do not use
• 2026-10-22 (~134 cm, pole at 111 cm)
• 2026-10-25 ~23:28 (140×69; C920 28 cm
  from right; sponge 70/45; paper 82/26;
  follower 62 cm from right)
• MuJoCo scene: 70×60 cm, box (28, -8),
  goal (35, 12), nadir camera (25, 0)
"""
    note.text(
        0.02,
        0.98,
        body,
        va="top",
        ha="left",
        fontsize=8,
        family="DejaVu Sans",
        linespacing=1.25,
        bbox={"fc": "#f7f7f7", "ec": "gray", "boxstyle": "square,pad=0.4"},
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUT_DIR / "so101_layout_guide.png"
    pdf_path = OUT_DIR / "so101_layout_guide.pdf"
    fig.savefig(png_path, dpi=140)
    fig.savefig(pdf_path)
    plt.close(fig)
    return png_path, pdf_path


def main() -> None:
    png_path, pdf_path = draw()
    print(png_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
