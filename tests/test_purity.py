"""성공 기준 2: interpreter.py에 게임 도메인 단어가 0회 등장한다.

대소문자 무시, '부분 문자열' 수준의 가장 엄격한 검사를 쓴다
(예: 'determine'에 든 'mine', 'pygame'에 든 'game'도 잡힌다).
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = ["block", "player", "inventory", "world", "craft", "mine", "game"]


def test_interpreter_knows_no_domain_words():
    with open(os.path.join(ROOT, "interpreter.py")) as fh:
        source = fh.read().lower()
    hits = {w: source.count(w) for w in FORBIDDEN if source.count(w)}
    assert not hits, f"domain words found in interpreter.py: {hits}"


def test_raycasting_lives_in_fable_source():
    """성공 기준 3: 레이캐스팅 로직은 Fable 소스에 있다."""
    with open(os.path.join(ROOT, "src", "raycast.fb")) as fh:
        src = fh.read()
    # DDA 핵심 요소: 격자 스텝, 거리 누적, 명중 기록
    for needle in ["fn cast(", "stepx", "tdx", "RC_DIST", "RC_SIDE"]:
        assert needle in src, f"raycast.fb is missing {needle!r}"
    with open(os.path.join(ROOT, "src", "render.fb")) as fh:
        rsrc = fh.read()
    # 세로 스트립 렌더: 칼럼 루프 + 거리 반비례 높이 + 스트립 사각형
    for needle in ["camx", "SH / d", "gfx_rect(c * COLW"]:
        assert needle in rsrc, f"render.fb is missing {needle!r}"
