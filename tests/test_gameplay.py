"""성공 기준 4: 채굴/설치/저장이 자동 테스트로 검증된다.

실제 검증 로직은 Fable로 작성된 tests/*.fb 프로그램이 수행하고,
여기서는 그 프로그램을 실행해 PASS/FAIL을 수거한다.
"""
from conftest import run_fable


def _check_output(out, expected_at_least):
    lines = out.strip().split("\n")
    fails = [ln for ln in lines if ln.startswith("FAIL")]
    passes = [ln for ln in lines if ln.startswith("PASS")]
    assert not fails, f"failures: {fails}"
    assert len(passes) >= expected_at_least
    assert "ALL_OK" in out


def test_raycast_geometry():
    _check_output(run_fable("tests/raycast_test.fb"), 14)


def test_dig_put_save_load(tmp_path):
    save_file = tmp_path / "roundtrip.fbw"
    _check_output(run_fable("tests/logic_test.fb", str(save_file)), 21)
    assert save_file.exists()
