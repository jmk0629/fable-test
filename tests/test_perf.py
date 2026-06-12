"""성공 기준 5(헤드리스 측면): 게임 로직+렌더 계산이 충분히 빠른지.

창 없이 120프레임을 돌려 프레임당 평균 시간을 잰다. 실제 플레이는
tkinter 그리기 비용이 더해지므로 여유를 크게 잡아 50ms(=20FPS) 미만을
요구한다. (실제 창 모드 FPS는 README의 측정 기록 참고.)
"""
from conftest import run_fable


def test_headless_frame_time():
    out = run_fable("src/main.fb", "--bench", "120")
    avg_ms = None
    for line in out.strip().split("\n"):
        if line.startswith("bench_avg_ms"):
            avg_ms = float(line.split()[1])
    assert avg_ms is not None, f"no bench output:\n{out}"
    assert avg_ms < 50.0, f"frame too slow: {avg_ms}ms"
