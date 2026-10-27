#!/usr/bin/env python3
"""Read-only preflight before SO-101 teleop or lerobot-record on macOS.

Prints PASS or FAIL for the Leader port, Follower port, wrist camera, and
top camera. Exits non-zero when any check fails. Does not open a motor bus,
command motion, or write a dataset.

Defaults match scripts/record_real_so101.sh (tty nodes, not cu nodes):

  Leader    /dev/tty.usbmodem5B790143611   (5V)   PORT_LEADER
  Follower  /dev/tty.usbmodem5B8E1163071   (12V)  PORT_FOLLOWER
  wrist     OpenCV index 0                        WRIST_INDEX
  top       OpenCV index 1                        TOP_INDEX

macOS also creates /dev/cu.usbmodem* for the same adapter. LeRobot in this
repo uses the tty node. A cu-only sibling is reported and still fails, so a
moved or half-present adapter is not treated as the record path.

The camera check prefers one OpenCV frame from the lerobot-hw venv (the
indices lerobot-record uses). Without OpenCV it lists cameras with
system_profiler / ffmpeg avfoundation and grabs one ffmpeg frame when ffmpeg
is installed. avfoundation index order can differ from OpenCV. A listed
Continuity Camera, iPhone camera, or iPad camera is a hard failure.

Other tty.usbmodem* / cu.usbmodem* nodes are listed and are not auto-selected.
Auto-picking a port can swap Leader and Follower (see the bring-up notes).

Env:
  LEROBOT_HW_ROOT or LEROBOT_HW   venv at $HW/.venv (default ~/work/lerobot-hw)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Same paths and OpenCV indices as scripts/record_real_so101.sh and
# port_pick_align.simulation.table_layout (wrist 0, top 1).
DEFAULT_LEADER_PORT = "/dev/tty.usbmodem5B790143611"
DEFAULT_FOLLOWER_PORT = "/dev/tty.usbmodem5B8E1163071"
DEFAULT_WRIST_INDEX = 0
DEFAULT_TOP_INDEX = 1

PASS = "PASS"
FAIL = "FAIL"

OPENCV_TIMEOUT_S = 8.0
FFMPEG_TIMEOUT_S = 8.0
NAME_SCAN_TIMEOUT_S = 20.0
FRAME_ATTEMPTS = 3
CAPTURE_WIDTH = 640
CAPTURE_HEIGHT = 480

_CONTINUITY = re.compile(r"continuity|\biphone\b|\bipad\b", re.IGNORECASE)
_AVF_DEVICE = re.compile(r"\[(\d+)\]\s+(.+?)\s*$")


@dataclass(frozen=True)
class Config:
    leader_port: str
    follower_port: str
    wrist_index: int
    top_index: int


@dataclass(frozen=True)
class ProbeResult:
    """One camera tool attempt. available=False means the tool was not used."""

    available: bool
    ok: bool
    detail: str


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    target: str
    detail: str

    @property
    def passed(self) -> bool:
        return self.status == PASS


class CameraBackend(Protocol):
    def probe(self, index: int) -> tuple[ProbeResult, ProbeResult]:
        """Return (opencv, ffmpeg) results for one OpenCV-style index."""

    def camera_names(self) -> list[str] | None:
        """Camera display names, or None when no name scan ran."""


def hw_root() -> Path:
    """Hardware workspace. LEROBOT_HW_ROOT wins, then LEROBOT_HW, then the default."""
    for key in ("LEROBOT_HW_ROOT", "LEROBOT_HW"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw).expanduser()
    return Path.home() / "work" / "lerobot-hw"


def sibling_path(path: str) -> str | None:
    """Map /dev/tty.usbmodem* <-> /dev/cu.usbmodem* (same adapter on macOS)."""
    node = Path(path)
    name = node.name
    if name.startswith("tty."):
        return str(node.with_name("cu." + name[4:]))
    if name.startswith("cu."):
        return str(node.with_name("tty." + name[3:]))
    return None


def list_usbmodem(dev_dir: Path) -> list[str]:
    """tty.usbmodem* and cu.usbmodem* names under dev_dir. Read-only."""
    try:
        entries = list(dev_dir.iterdir())
    except OSError:
        return []
    found: list[str] = []
    for entry in entries:
        name = entry.name
        if name.startswith(("tty.usbmodem", "cu.usbmodem")):
            found.append(str(entry))
    return sorted(found)


def _node_usable(path: str) -> tuple[bool, str]:
    try:
        st = os.stat(path)
    except OSError:
        return False, "not found"
    if stat.S_ISDIR(st.st_mode):
        return False, "not found"
    if not os.access(path, os.R_OK | os.W_OK):
        return False, "exists but is not readable and writable"
    return True, "present"


def check_port(name: str, path: str, nodes: list[str]) -> Check:
    """Presence of one serial node. Does not open the port."""
    target = path.strip()
    if not target:
        return Check(name, FAIL, target, "empty path")
    ok, detail = _node_usable(target)
    if ok:
        return Check(name, PASS, target, detail)
    if detail == "not found":
        sibling = sibling_path(target)
        if sibling and sibling != target:
            sib_ok, _sib_detail = _node_usable(sibling)
            if sib_ok:
                detail = (
                    f"not found; sibling {sibling} exists "
                    "(record_real_so101.sh uses the tty node unless PORT_* is set)"
                )
        others = [
            node for node in nodes if node != target and node != sibling_path(target)
        ]
        if others:
            shown = " ".join(others[:8])
            detail = f"{detail}; other usbmodem nodes: {shown}"
    return Check(name, FAIL, target, detail)


def port_checks(leader: str, follower: str, nodes: list[str]) -> list[Check]:
    checks = [
        check_port("Leader port", leader, nodes),
        check_port("Follower port", follower, nodes),
    ]
    if leader.strip() and leader.strip() == follower.strip():
        detail = "Leader and Follower paths are the same"
        checks = [Check(item.name, FAIL, item.target, detail) for item in checks]
    return checks


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer, got {raw!r}") from exc


def parse_args(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only SO-101 preflight (Leader/Follower serial nodes and "
            "wrist/top cameras). Does not move the arm or write a dataset."
        )
    )
    parser.add_argument(
        "--leader-port",
        default=None,
        help=f"Leader serial node (env PORT_LEADER, default {DEFAULT_LEADER_PORT})",
    )
    parser.add_argument(
        "--follower-port",
        default=None,
        help=f"Follower serial node (env PORT_FOLLOWER, default {DEFAULT_FOLLOWER_PORT})",
    )
    parser.add_argument(
        "--wrist-index",
        type=int,
        default=None,
        help=f"Wrist OpenCV index (env WRIST_INDEX, default {DEFAULT_WRIST_INDEX})",
    )
    parser.add_argument(
        "--top-index",
        type=int,
        default=None,
        help=f"Top OpenCV index (env TOP_INDEX, default {DEFAULT_TOP_INDEX})",
    )
    args = parser.parse_args(argv)
    leader = (
        args.leader_port
        if args.leader_port is not None
        else os.environ.get("PORT_LEADER")
    )
    follower = (
        args.follower_port
        if args.follower_port is not None
        else os.environ.get("PORT_FOLLOWER")
    )
    return Config(
        leader_port=(leader or DEFAULT_LEADER_PORT).strip(),
        follower_port=(follower or DEFAULT_FOLLOWER_PORT).strip(),
        wrist_index=(
            args.wrist_index
            if args.wrist_index is not None
            else _env_int("WRIST_INDEX", DEFAULT_WRIST_INDEX)
        ),
        top_index=(
            args.top_index
            if args.top_index is not None
            else _env_int("TOP_INDEX", DEFAULT_TOP_INDEX)
        ),
    )


def continuity_hits(names: list[str]) -> list[str]:
    return [name for name in names if _CONTINUITY.search(name)]


def continuity_check(names: list[str] | None) -> Check | None:
    if names is None:
        return None
    hits = continuity_hits(names)
    if hits:
        listed = ", ".join(hits)
        return Check(
            "continuity",
            FAIL,
            "camera name scan",
            f"turn Continuity Camera off and disconnect it; listed {listed}",
        )
    return Check("continuity", PASS, "camera name scan", "not listed")


def classify_camera(
    name: str,
    index: int,
    opencv: ProbeResult | None,
    ffmpeg: ProbeResult | None,
    listed_names: list[str] | None,
) -> Check:
    """PASS/FAIL for one camera. OpenCV is authoritative when it can run."""
    target = f"opencv index {index}"
    if index < 0:
        return Check(name, FAIL, target, "index must be >= 0")
    if opencv is not None and opencv.available:
        return Check(name, PASS if opencv.ok else FAIL, target, opencv.detail)
    if ffmpeg is not None and ffmpeg.available:
        detail = ffmpeg.detail
        if opencv is not None and not opencv.available:
            detail = f"{detail} ({opencv.detail})"
        if not ffmpeg.ok and listed_names:
            detail = f"{detail}; camera list: {', '.join(listed_names)}"
        return Check(name, PASS if ffmpeg.ok else FAIL, target, detail)
    if listed_names is not None:
        visible = [item for item in listed_names if item.strip()]
        if len(visible) >= 2:
            return Check(
                name,
                PASS,
                target,
                (
                    f"visible in camera list ({len(visible)} devices); "
                    "OpenCV frame not grabbed; avfoundation order can differ "
                    "from OpenCV indices"
                ),
            )
        shown = ", ".join(visible) if visible else "none"
        return Check(
            name,
            FAIL,
            target,
            f"fewer than 2 cameras listed ({shown}); frame not grabbed",
        )
    extra = opencv.detail if opencv is not None else "no camera probe available"
    return Check(name, FAIL, target, extra)


def evaluate(cfg: Config, backend: CameraBackend, nodes: list[str]) -> list[Check]:
    checks = port_checks(cfg.leader_port, cfg.follower_port, nodes)
    names = backend.camera_names()
    if cfg.wrist_index == cfg.top_index:
        detail = "wrist and top indices are the same"
        checks.append(
            Check("wrist cam", FAIL, f"opencv index {cfg.wrist_index}", detail)
        )
        checks.append(Check("top cam", FAIL, f"opencv index {cfg.top_index}", detail))
    else:
        for label, index in (
            ("wrist cam", cfg.wrist_index),
            ("top cam", cfg.top_index),
        ):
            opencv, ffmpeg = backend.probe(index)
            checks.append(classify_camera(label, index, opencv, ffmpeg, names))
    continuity = continuity_check(names)
    if continuity is not None:
        checks.append(continuity)
    return checks


def render(checks: list[Check], nodes: list[str], dev_dir: Path) -> str:
    lines = ["SO-101 preflight (read-only: no motor bus, no motion, no dataset)"]
    for check in checks:
        lines.append(
            f"{check.name:<14} {check.status:<4}  {check.target}  {check.detail}"
        )
    if nodes:
        lines.append(f"{'usbmodem':<14} info  {' '.join(nodes)}")
    else:
        lines.append(
            f"{'usbmodem':<14} info  no tty.usbmodem* or cu.usbmodem* nodes under {dev_dir}"
        )
    lines.append(
        "RESULT FAIL" if any(not check.passed for check in checks) else "RESULT PASS"
    )
    return "\n".join(lines) + "\n"


def _one_line(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3] + "..."


def _call_timeout(fn, timeout_s: float, label: str) -> ProbeResult:
    holder: list[ProbeResult | BaseException] = []

    def run() -> None:
        try:
            holder.append(fn())
        except BaseException as exc:  # noqa: BLE001 — report probe bugs as a failed check
            holder.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        return ProbeResult(True, False, f"{label} timed out after {timeout_s:.0f}s")
    if not holder:
        return ProbeResult(True, False, f"{label} returned nothing")
    item = holder[0]
    if isinstance(item, ProbeResult):
        return item
    return ProbeResult(True, False, _one_line(f"{label} {type(item).__name__}: {item}"))


def _quiet_cv2(cv2_module: object) -> None:
    utils = getattr(cv2_module, "utils", None)
    logging = getattr(utils, "logging", None) if utils is not None else None
    if logging is None:
        return
    level = getattr(logging, "LOG_LEVEL_ERROR", None)
    set_level = getattr(logging, "setLogLevel", None)
    if level is None or set_level is None:
        return
    try:
        set_level(level)
    except Exception:  # noqa: BLE001 — log-level API differs across OpenCV builds
        return


def _opencv_grab(index: int) -> ProbeResult:
    import cv2

    _quiet_cv2(cv2)
    api = getattr(cv2, "CAP_AVFOUNDATION", None) if sys.platform == "darwin" else None
    cap = cv2.VideoCapture(index) if api is None else cv2.VideoCapture(index, api)
    try:
        if not cap.isOpened():
            return ProbeResult(True, False, "opencv did not open the index")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
        got = None
        for _ in range(FRAME_ATTEMPTS):
            ok, frame = cap.read()
            if ok and frame is not None and getattr(frame, "size", 0):
                got = frame
                break
        if got is None:
            return ProbeResult(True, False, "opencv read returned no frame")
        height, width = got.shape[:2]
        return ProbeResult(True, True, f"opencv frame {width}x{height}")
    finally:
        cap.release()


def probe_opencv(index: int) -> ProbeResult:
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    try:
        import cv2  # noqa: F401
    except ImportError:
        return ProbeResult(False, False, "opencv not importable")
    return _call_timeout(lambda: _opencv_grab(index), OPENCV_TIMEOUT_S, "opencv")


def _ffmpeg_grab(ffmpeg: str, index: int) -> ProbeResult:
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "avfoundation",
        "-framerate",
        "30",
        "-video_size",
        f"{CAPTURE_WIDTH}x{CAPTURE_HEIGHT}",
        "-i",
        f"{index}:none",
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        timeout=FFMPEG_TIMEOUT_S,
        check=False,
    )
    if proc.returncode == 0:
        return ProbeResult(
            True,
            True,
            "ffmpeg avfoundation captured 1 frame (index order can differ from OpenCV)",
        )
    err = proc.stderr.decode("utf-8", "replace")
    tail = _one_line(err) if err.strip() else f"exit {proc.returncode}"
    return ProbeResult(True, False, f"ffmpeg avfoundation failed: {tail}")


def probe_ffmpeg(index: int) -> ProbeResult:
    if sys.platform != "darwin":
        return ProbeResult(False, False, "ffmpeg avfoundation is macOS-only")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return ProbeResult(False, False, "ffmpeg not found")
    try:
        return _ffmpeg_grab(ffmpeg, index)
    except subprocess.TimeoutExpired:
        return ProbeResult(
            True, False, f"ffmpeg avfoundation timed out after {FFMPEG_TIMEOUT_S:.0f}s"
        )
    except OSError as exc:
        return ProbeResult(True, False, _one_line(f"ffmpeg avfoundation failed: {exc}"))


def avfoundation_video_names(text: str) -> list[str]:
    """Parse `ffmpeg -f avfoundation -list_devices true` stderr."""
    names: list[str] = []
    in_video = False
    for line in text.splitlines():
        lower = line.lower()
        if "video devices" in lower:
            in_video = True
            continue
        if "audio devices" in lower:
            in_video = False
            continue
        if not in_video:
            continue
        match = _AVF_DEVICE.search(line)
        if match:
            names.append(match.group(2).strip())
    return names


def names_from_profiler_json(payload: str) -> list[str]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    names: list[str] = []
    entries = data.get("SPCameraDataType", [])
    if not isinstance(entries, list):
        return []
    for item in entries:
        if isinstance(item, dict) and item.get("_name"):
            names.append(str(item["_name"]))
    return names


def _names_from_system_profiler() -> list[str]:
    if sys.platform != "darwin" or shutil.which("system_profiler") is None:
        return []
    proc = subprocess.run(
        ["system_profiler", "SPCameraDataType", "-json"],
        capture_output=True,
        timeout=NAME_SCAN_TIMEOUT_S,
        check=False,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    return names_from_profiler_json(proc.stdout)


def _names_from_ffmpeg() -> list[str]:
    if sys.platform != "darwin":
        return []
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-f",
            "avfoundation",
            "-list_devices",
            "true",
            "-i",
            "",
        ],
        capture_output=True,
        timeout=NAME_SCAN_TIMEOUT_S,
        check=False,
        text=True,
    )
    return avfoundation_video_names((proc.stderr or "") + "\n" + (proc.stdout or ""))


class LiveBackend:
    """OpenCV frame, then ffmpeg, plus a macOS camera-name scan. No motor bus."""

    def probe(self, index: int) -> tuple[ProbeResult, ProbeResult]:
        opencv = probe_opencv(index)
        if opencv.available:
            return opencv, ProbeResult(False, False, "ffmpeg not run")
        return opencv, probe_ffmpeg(index)

    def camera_names(self) -> list[str] | None:
        if sys.platform != "darwin":
            return None
        try:
            names = _names_from_system_profiler()
            if not names:
                names = _names_from_ffmpeg()
        except (OSError, subprocess.TimeoutExpired):
            return None
        return names


def maybe_reexec_venv() -> None:
    """Re-run with the lerobot-hw venv when this interpreter has no OpenCV."""
    if os.environ.get("SO101_PREFLIGHT_NO_REEXEC") == "1":
        return
    if probe_opencv_importable():
        return
    py = hw_root() / ".venv" / "bin" / "python"
    if not py.is_file():
        return
    try:
        if Path(sys.executable).resolve() == py.resolve():
            return
    except OSError:
        return
    os.environ["SO101_PREFLIGHT_NO_REEXEC"] = "1"
    os.execv(str(py), [str(py), *sys.argv])


def probe_opencv_importable() -> bool:
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return True


def main(
    argv: list[str] | None = None,
    *,
    backend: CameraBackend | None = None,
    dev_dir: Path | None = None,
) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        parse_args(argv)
    if backend is None:
        maybe_reexec_venv()
    cfg = parse_args(argv)
    devices = dev_dir if dev_dir is not None else Path("/dev")
    nodes = list_usbmodem(devices)
    checks = evaluate(cfg, backend or LiveBackend(), nodes)
    sys.stdout.write(render(checks, nodes, devices))
    sys.stdout.flush()
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
