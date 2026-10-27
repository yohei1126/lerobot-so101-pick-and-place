"""Unit tests for scripts/preflight_real_so101.py (no arm, no cameras)."""

from __future__ import annotations

import importlib.util
import re
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LAYOUT = (
    REPO_ROOT / "port_pick_align" / "src" / "port_pick_align" / "simulation" / "table_layout.py"
)
SCRIPT = REPO_ROOT / "scripts" / "preflight_real_so101.py"
SHELL = REPO_ROOT / "scripts" / "preflight_real_so101.sh"
RECORD = REPO_ROOT / "scripts" / "record_real_so101.sh"

_SPEC = importlib.util.spec_from_file_location("preflight_real_so101", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
preflight = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = preflight
_SPEC.loader.exec_module(preflight)

_BASH4 = (
    re.compile(r"\bmapfile\b"),
    re.compile(r"\breadarray\b"),
    re.compile(r"\bdeclare\s+-A\b"),
    re.compile(r"\$\{[^}]+,,\}"),
    re.compile(r"\$\{[^}]+\^\^\}"),
    re.compile(r"\bdeclare\s+-n\b"),
)

_MOTOR_APIS = (
    "send_action",
    "FeetechMotorsBus",
    "robot.connect",
    "imwrite",
)


class FakeBackend:
    def __init__(
        self,
        *,
        opencv: object | None = None,
        ffmpeg: object | None = None,
        names: list[str] | None = None,
        per_index: dict | None = None,
    ) -> None:
        self.opencv = opencv
        self.ffmpeg = ffmpeg
        self.names = names
        self.per_index = per_index or {}
        self.probed: list[int] = []

    def probe(self, index: int):
        self.probed.append(index)
        if index in self.per_index:
            return self.per_index[index]
        return self.opencv, self.ffmpeg

    def camera_names(self) -> list[str] | None:
        return self.names


def _ok(detail: str) -> object:
    return preflight.ProbeResult(True, True, detail)


def _bad(detail: str, *, available: bool = True) -> object:
    return preflight.ProbeResult(available, False, detail)


def _cfg(leader: str, follower: str, wrist: int = 0, top: int = 1):
    return preflight.Config(leader, follower, wrist, top)


@pytest.mark.unit
def test_defaults_match_record_script_and_table_layout() -> None:
    text = RECORD.read_text(encoding="utf-8")
    assert preflight.DEFAULT_LEADER_PORT in text
    assert preflight.DEFAULT_FOLLOWER_PORT in text
    assert "index_or_path: 0" in text
    assert "index_or_path: 1" in text
    layout = LAYOUT.read_text(encoding="utf-8")
    assert f"OPENCV_WRIST_INDEX = {preflight.DEFAULT_WRIST_INDEX}" in layout
    assert f"OPENCV_TOP_INDEX = {preflight.DEFAULT_TOP_INDEX}" in layout
    assert preflight.DEFAULT_WRIST_INDEX == 0
    assert preflight.DEFAULT_TOP_INDEX == 1
    assert preflight.DEFAULT_LEADER_PORT != preflight.DEFAULT_FOLLOWER_PORT
    assert preflight.DEFAULT_LEADER_PORT.startswith("/dev/tty.usbmodem")
    assert preflight.DEFAULT_FOLLOWER_PORT.startswith("/dev/tty.usbmodem")


@pytest.mark.unit
def test_script_does_not_reference_motor_or_dataset_writes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in _MOTOR_APIS:
        assert token not in text


@pytest.mark.unit
def test_shell_is_bash32_and_prefers_hw_venv() -> None:
    text = SHELL.read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    offenders = [pat.pattern for pat in _BASH4 if pat.search(body)]
    assert not offenders
    assert "LEROBOT_HW_ROOT" in text
    assert "LEROBOT_HW" in text
    assert "preflight_real_so101.py" in text
    assert SHELL.stat().st_mode & stat.S_IXUSR


@pytest.mark.unit
def test_missing_leader_fails_and_sibling_is_reported(tmp_path: Path) -> None:
    sibling = tmp_path / "cu.usbmodem5B790143611"
    sibling.write_text("", encoding="utf-8")
    tty = tmp_path / "tty.usbmodem5B790143611"
    nodes = preflight.list_usbmodem(tmp_path)
    check = preflight.check_port("Leader port", str(tty), nodes)
    assert check.status == preflight.FAIL
    assert str(sibling) in check.detail
    assert "tty node" in check.detail


@pytest.mark.unit
def test_present_ports_pass_and_same_path_fails(tmp_path: Path) -> None:
    leader = tmp_path / "tty.usbmodemLEADER"
    follower = tmp_path / "tty.usbmodemFOLLOWER"
    leader.write_text("", encoding="utf-8")
    follower.write_text("", encoding="utf-8")
    checks = preflight.port_checks(str(leader), str(follower), [])
    assert [item.status for item in checks] == [preflight.PASS, preflight.PASS]
    same = preflight.port_checks(str(leader), str(leader), [])
    assert [item.status for item in same] == [preflight.FAIL, preflight.FAIL]
    assert "same" in same[0].detail


@pytest.mark.unit
def test_unreadable_port_fails(tmp_path: Path) -> None:
    node = tmp_path / "tty.usbmodemLOCKED"
    node.write_text("", encoding="utf-8")
    node.chmod(0)
    try:
        check = preflight.check_port("Follower port", str(node), [])
        assert check.status == preflight.FAIL
        assert "not readable" in check.detail
    finally:
        node.chmod(0o644)


@pytest.mark.unit
def test_directory_is_not_a_port(tmp_path: Path) -> None:
    node = tmp_path / "tty.usbmodemDIR"
    node.mkdir()
    check = preflight.check_port("Leader port", str(node), [])
    assert check.status == preflight.FAIL
    assert check.detail.startswith("not found")


@pytest.mark.unit
def test_env_defaults_and_cli_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT_LEADER", "/dev/tty.usbmodemFROMENV")
    monkeypatch.setenv("PORT_FOLLOWER", "/dev/tty.usbmodemFOLLOWENV")
    monkeypatch.setenv("WRIST_INDEX", "4")
    monkeypatch.setenv("TOP_INDEX", "5")
    cfg = preflight.parse_args([])
    assert cfg.leader_port == "/dev/tty.usbmodemFROMENV"
    assert cfg.follower_port == "/dev/tty.usbmodemFOLLOWENV"
    assert cfg.wrist_index == 4
    assert cfg.top_index == 5
    overridden = preflight.parse_args(
        ["--leader-port", "/dev/tty.custom", "--wrist-index", "0", "--top-index", "1"]
    )
    assert overridden.leader_port == "/dev/tty.custom"
    assert overridden.follower_port == "/dev/tty.usbmodemFOLLOWENV"
    assert overridden.wrist_index == 0
    assert overridden.top_index == 1


@pytest.mark.unit
def test_bad_index_env_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOP_INDEX", "nope")
    with pytest.raises(SystemExit):
        preflight.parse_args([])


@pytest.mark.unit
def test_opencv_result_is_authoritative() -> None:
    names = ["USB2.0_CAM1", "C920", "FaceTime HD Camera"]
    passed = preflight.classify_camera(
        "wrist cam",
        0,
        _ok("opencv frame 640x480"),
        _ok("ffmpeg should be ignored"),
        names,
    )
    assert passed.status == preflight.PASS
    assert "opencv frame" in passed.detail
    failed = preflight.classify_camera(
        "top cam",
        1,
        _bad("opencv did not open the index"),
        _ok("ffmpeg avfoundation captured 1 frame"),
        names,
    )
    assert failed.status == preflight.FAIL
    assert "opencv did not open" in failed.detail
    assert "ffmpeg" not in failed.detail


@pytest.mark.unit
def test_ffmpeg_and_list_fallbacks() -> None:
    missing = _bad("opencv not importable", available=False)
    ffmpeg_pass = preflight.classify_camera(
        "wrist cam",
        0,
        missing,
        _ok("ffmpeg avfoundation captured 1 frame"),
        ["A", "B"],
    )
    assert ffmpeg_pass.status == preflight.PASS
    assert "avfoundation" in ffmpeg_pass.detail
    listed = preflight.classify_camera("top cam", 1, missing, missing, ["USB2.0_CAM1", "C920"])
    assert listed.status == preflight.PASS
    assert "OpenCV frame not grabbed" in listed.detail
    short = preflight.classify_camera("top cam", 1, missing, missing, ["FaceTime HD Camera"])
    assert short.status == preflight.FAIL
    none = preflight.classify_camera("wrist cam", 0, missing, missing, None)
    assert none.status == preflight.FAIL


@pytest.mark.unit
def test_same_index_does_not_open_cameras() -> None:
    class Boom(FakeBackend):
        def probe(self, index: int):
            raise AssertionError(index)

    checks = preflight.evaluate(_cfg("/dev/a", "/dev/b", wrist=1, top=1), Boom(names=[]), [])
    cams = [item for item in checks if item.name.endswith("cam")]
    assert [item.status for item in cams] == [preflight.FAIL, preflight.FAIL]


@pytest.mark.unit
def test_continuity_names_fail_the_run() -> None:
    sample = """
[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] FaceTime HD Camera
[AVFoundation indev @ 0x1] [1] USB2.0_CAM1
[AVFoundation indev @ 0x1] [2] C920
[AVFoundation indev @ 0x1] [3] Yohei iPhone Camera
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone
"""
    names = preflight.avfoundation_video_names(sample)
    assert names == ["FaceTime HD Camera", "USB2.0_CAM1", "C920", "Yohei iPhone Camera"]
    assert preflight.continuity_hits(names) == ["Yohei iPhone Camera"]
    assert preflight.continuity_hits(["Continuity Camera", "C920"]) == ["Continuity Camera"]
    assert preflight.continuity_hits(["FaceTime HD Camera", "USB2.0_CAM1"]) == []
    check = preflight.continuity_check(names)
    assert check is not None and check.status == preflight.FAIL
    clear = preflight.continuity_check(["USB2.0_CAM1", "C920"])
    assert clear is not None and clear.status == preflight.PASS
    assert preflight.continuity_check(None) is None


@pytest.mark.unit
def test_profiler_json_names() -> None:
    payload = '{"SPCameraDataType":[{"_name":"C920"},{"_name":"USB2.0_CAM1"},{"other":1}]}'
    assert preflight.names_from_profiler_json(payload) == ["C920", "USB2.0_CAM1"]
    assert preflight.names_from_profiler_json("not-json") == []


@pytest.mark.unit
def test_main_pass_and_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    leader = tmp_path / "tty.usbmodemLEADER"
    follower = tmp_path / "tty.usbmodemFOLLOWER"
    leader.write_text("", encoding="utf-8")
    follower.write_text("", encoding="utf-8")
    backend = FakeBackend(
        opencv=_ok("opencv frame 640x480"),
        names=["USB2.0_CAM1", "C920"],
    )
    code = preflight.main(
        [
            "--leader-port",
            str(leader),
            "--follower-port",
            str(follower),
            "--wrist-index",
            "0",
            "--top-index",
            "1",
        ],
        backend=backend,
        dev_dir=tmp_path,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Leader port    PASS" in out
    assert "Follower port  PASS" in out
    assert "wrist cam      PASS" in out
    assert "top cam        PASS" in out
    assert "continuity     PASS" in out
    assert "RESULT PASS" in out
    assert "read-only" in out
    assert backend.probed == [0, 1]

    code = preflight.main(
        ["--leader-port", str(tmp_path / "missing"), "--follower-port", str(follower)],
        backend=backend,
        dev_dir=tmp_path,
    )
    failed = capsys.readouterr().out
    assert code == 1
    assert "Leader port    FAIL" in failed
    assert "RESULT FAIL" in failed


@pytest.mark.unit
def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        preflight.main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "PORT_LEADER" in text
    assert "WRIST_INDEX" in text
