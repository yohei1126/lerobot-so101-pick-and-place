#!/usr/bin/env python3
"""Draw the SO-101 tabletop layout guide into ``docs/images/``.

Planar geometry matches the simplified MuJoCo scene, not a real SO-101 CAD
model. Sources:

- ``port_pick_align/src/port_pick_align/simulation/assets/so101_tabletop.xml``
- ``port_pick_align/src/port_pick_align/simulation/env.py``
- ``port_pick_align/src/port_pick_align/evaluation/eval_alignment.py``

Coordinates are centimetres. The origin is the arm-base centre, +x is forward,
and +y is left. Run from anywhere:

    python scripts/draw_layout_guide.py
"""

from __future__ import annotations

import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "images"

# so101_tabletop.xml / env.py (metres in the model, centimetres here).
TABLE_Z_M = 0.42
TOP_CAM_Z_M = 1.05
TOP_CAM_XY_CM = (25.0, 0.0)
TOP_CAM_VFOV_DEG = 55.0
IMAGE_ASPECT = 640 / 480  # configs/contract.yaml
BOX_CENTER_CM = (28.0, -8.0)
BOX_SIZE_CM = (5.0, 4.0)
BOX_XY_JITTER_CM = 4.0
GOAL_CENTER_CM = (35.0, 12.0)
GOAL_SIZE_CM = (8.0, 6.0)
SUCCESS_RADIUS_CM = 2.5  # DEFAULT_ALIGN_POS_MM = 25
REACH_CM = 42.0
PAN_DEG = 110.0


def _top_camera_half_extents_cm() -> tuple[float, float]:
    """Return (half-width x, half-height y) of the top-camera footprint on the table.

    MuJoCo ``fovy`` is the vertical FOV. With ``xyaxes="1 0 0 0 1 0"`` the camera
    y axis is world +y, so the vertical FOV spans y and the horizontal FOV spans x.
    """
    height_cm = (TOP_CAM_Z_M - TABLE_Z_M) * 100.0
    half_y = height_cm * math.tan(math.radians(TOP_CAM_VFOV_DEG / 2.0))
    half_x = half_y * IMAGE_ASPECT
    return half_x, half_y


def _cjk_font_family() -> str:
    from matplotlib import font_manager as fm

    names = {font.name for font in fm.fontManager.ttflist}
    for candidate in ("Noto Sans CJK JP", "WenQuanYi Micro Hei", "Droid Sans Fallback"):
        if candidate in names:
            return candidate
    cjk = sorted(name for name in names if "CJK" in name)
    if cjk:
        return cjk[0]
    return "DejaVu Sans"


def draw() -> tuple[Path, Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon, Rectangle, Wedge

    plt.rcParams["font.family"] = _cjk_font_family()
    half_x, half_y = _top_camera_half_extents_cm()
    cam_x, cam_y = TOP_CAM_XY_CM
    box_x, box_y = BOX_CENTER_CM
    goal_x, goal_y = GOAL_CENTER_CM

    fig = plt.figure(figsize=(17, 11))
    ax = fig.add_axes((0.03, 0.08, 0.55, 0.84))
    sx = fig.add_axes((0.62, 0.45, 0.36, 0.47))
    lx = fig.add_axes((0.62, 0.03, 0.36, 0.38))
    lx.axis("off")

    ax.add_patch(
        Rectangle(
            (-10, -30),
            70,
            60,
            fc="#d9c7a8",
            ec="#7a5c3a",
            lw=2,
            label="テーブル 70×60cm",
        )
    )
    ax.add_patch(
        Wedge(
            (0, 0),
            REACH_CM,
            -PAN_DEG,
            PAN_DEG,
            fc="#4a7bd422",
            ec="#4a7bd4",
            ls="--",
            lw=1.5,
            label="到達範囲の目安 (sim 幾何最大 ~42cm, pan ±110°)",
        )
    )
    ax.add_patch(
        Circle((0, 0), 4, fc="#3f6fbf", ec="k", label="アーム基部 (原点, Φ8cm)")
    )
    ax.add_patch(
        Rectangle(
            (cam_x - half_x, cam_y - half_y),
            2 * half_x,
            2 * half_y,
            fill=False,
            ec="purple",
            ls=":",
            lw=2,
            label="上カメラ視野 (テーブル面, 約87×66cm)",
        )
    )
    ax.plot(cam_x, cam_y, marker="X", ms=16, color="purple")
    ax.annotate(
        "上カメラ真下\n(25, 0) 高さ105cm",
        (cam_x, cam_y),
        (14, 4),
        color="purple",
        fontsize=10,
    )
    jitter = BOX_XY_JITTER_CM
    ax.add_patch(
        Rectangle(
            (box_x - jitter, box_y - jitter),
            2 * jitter,
            2 * jitter,
            fc="#ff990033",
            ec="#e07000",
            lw=2.5,
            label="箱 初期配置範囲 (中心 ±4cm, yaw ±17°)",
        )
    )
    ax.add_patch(
        Rectangle(
            (box_x - BOX_SIZE_CM[0] / 2, box_y - BOX_SIZE_CM[1] / 2),
            BOX_SIZE_CM[0],
            BOX_SIZE_CM[1],
            fc="#e07000",
            ec="k",
            alpha=0.8,
            label="箱 5×4×4cm (中心28,-8)",
        )
    )
    ax.add_patch(
        Rectangle(
            (goal_x - GOAL_SIZE_CM[0] / 2, goal_y - GOAL_SIZE_CM[1] / 2),
            GOAL_SIZE_CM[0],
            GOAL_SIZE_CM[1],
            fc="#33cc5555",
            ec="green",
            lw=2.5,
            label="ゴール 8×6cm 枠 (中心35,12, yaw 0°)",
        )
    )
    ax.plot([33, 37], [12, 12], "g", lw=2)
    ax.plot([35, 35], [10, 14], "g", lw=2)
    ax.add_patch(
        Circle(
            (goal_x, goal_y),
            SUCCESS_RADIUS_CM,
            fill=False,
            ec="green",
            ls="--",
            label="成功判定 位置誤差 <2.5cm (yaw <15°)",
        )
    )
    for point, text, offset in (
        ((box_x, box_y), "(28, −8)", (29, -17)),
        ((goal_x, goal_y), "(35, 12)", (36, 17)),
    ):
        ax.annotate(text, point, offset, fontsize=11, arrowprops={"arrowstyle": "->"})
    ax.annotate("", (box_x, -22), (0, -22), arrowprops={"arrowstyle": "<->"})
    ax.text(box_x / 2, -24.5, "28cm", ha="center")
    ax.annotate("", (goal_x, 24), (0, 24), arrowprops={"arrowstyle": "<->"})
    ax.text(goal_x / 2, 25, "35cm", ha="center")
    ax.annotate("", (45, goal_y), (45, 0), arrowprops={"arrowstyle": "<->"})
    ax.text(46, goal_y / 2, "12cm")
    ax.annotate("", (45, box_y), (45, 0), arrowprops={"arrowstyle": "<->"})
    ax.text(46, box_y / 2, "8cm")
    ax.annotate(
        "", (12, 0), (0, 0), arrowprops={"arrowstyle": "->", "color": "r", "lw": 2}
    )
    ax.text(12.5, -1.5, "+x (前方)", color="r")
    ax.annotate(
        "", (0, 12), (0, 0), arrowprops={"arrowstyle": "->", "color": "g", "lw": 2}
    )
    ax.text(-2, 13, "+y (左)", color="g")
    ax.set_xlim(-22, 72)
    ax.set_ylim(-36, 36)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_xticks(range(-20, 71, 10))
    ax.set_xlabel("x [cm] (アーム基部中心が原点)")
    ax.set_ylabel("y [cm]")
    ax.set_title("上面図 (縮尺 cm) — 実機セットアップ配置ガイド", fontsize=15)
    ax.legend(loc="lower right", fontsize=8.5, framealpha=0.9)

    sx.add_patch(Rectangle((-10, -4), 70, 4, fc="#d9c7a8", ec="#7a5c3a"))
    sx.text(40, -3, "テーブル天板 (z=0)", fontsize=9)
    sx.add_patch(Rectangle((-4, 0), 8, 3, fc="#3f6fbf"))
    sx.plot([0, 0, 14, 22], [3, 19, 19, 19], "o-", color="#3f6fbf", lw=4)
    sx.text(-9, 8, "肩 7cm\n上腕 12cm\n前腕 14cm", fontsize=8)
    sx.add_patch(
        Rectangle((box_x - BOX_SIZE_CM[0] / 2, 0), BOX_SIZE_CM[0], 4, fc="#e07000")
    )
    sx.text(24, 5, "箱 4cm高", fontsize=9)
    sx.plot([31, 39], [0.2, 0.2], "g", lw=5)
    sx.text(32, 1.5, "ゴール", color="green", fontsize=9)
    sx.plot(cam_x, 63, "s", ms=14, color="purple")
    sx.text(
        27,
        62,
        "上カメラ (C920 想定)\nテーブル面から 63cm\n(床から105cm) 真下向き",
        color="purple",
        fontsize=9,
    )
    sx.add_patch(
        Polygon(
            [[cam_x, 63], [cam_x - half_x, 0], [cam_x + half_x, 0]],
            fc="#80008015",
            ec="purple",
            ls=":",
        )
    )
    sx.annotate("", (cam_x, 0), (cam_x, 63), arrowprops={"arrowstyle": "<->"})
    sx.text(
        48, 30, "x方向 水平FOV≈69°\n(y方向 垂直FOV 55°)", fontsize=9, color="purple"
    )
    sx.set_xlim(-22, 72)
    sx.set_ylim(-5, 70)
    sx.set_aspect("equal")
    sx.grid(alpha=0.3)
    sx.set_xlabel("x [cm]")
    sx.set_ylabel("z [cm] (天板から)")
    sx.set_title("側面図 (x–z)", fontsize=14)

    note = """【テープ目印】
 ・オレンジ枠 8×8cm: 箱の初期配置範囲 (中心 x=28, y=−8)
 ・緑の十字+枠 8×6cm: ゴール (中心 x=35, y=12, 向き x軸平行)
 ・紫の×: 上カメラの真下 (x=25, y=0)
【推奨物体】 約5×4×4cm のスポンジ/ブロック (sim: 30g)
【カメラ】 モデルは 上カメラ(top)＋手首カメラ(wrist) の
  2入力 (各640×480, 30fps) を前提。C920 1台のみの場合は
  上カメラに使用し、手首カメラは別途必要 (未装着だと分布外)。
  手首カメラ: グリッパ根元 前2cm・上4cm, 下向き約30°, FOV 60°
【注意】 sim のアームは簡易モデル (実SO-101と寸法差あり)。
  到達範囲は目安。テーブル寸法/高さ(42cm)は sim 値。"""
    lx.text(
        0,
        1,
        note,
        va="top",
        fontsize=10.5,
        linespacing=1.5,
        bbox={"fc": "#f7f7f7", "ec": "gray"},
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUT_DIR / "so101_layout_guide.png"
    pdf_path = OUT_DIR / "so101_layout_guide.pdf"
    fig.savefig(png_path, dpi=130)
    fig.savefig(pdf_path)
    plt.close(fig)
    return png_path, pdf_path


def main() -> None:
    png_path, pdf_path = draw()
    print(png_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
