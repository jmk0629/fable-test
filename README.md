# Fable — 작은 언어와, 그 언어로만 만든 레이캐스팅 1인칭 게임

`interpreter.py`(순수 Python, 의존성 없음) 하나가 Fable 언어의 전부를 구현하고,
게임(월드, 플레이어, 레이캐스팅, 렌더링, 인벤토리, 저장)은 **전부 `.fb` Fable
소스**로 작성되어 있습니다. 인터프리터에는 게임 도메인 단어가 한 글자도 없으며
(`tests/test_purity.py`가 부분 문자열 수준으로 검사), 내장 함수는 사각형 그리기,
키 상태, 파일, 시계, 기본 수학뿐입니다.

## 실행

```sh
# 게임 (tkinter 창)
python3 interpreter.py src/main.fb

# 예제
python3 interpreter.py examples/hello.fb
python3 interpreter.py examples/fizzbuzz.fb
python3 interpreter.py examples/primes.fb

# 테스트 (요구: pytest)
python3 -m pytest tests/ -q
```

## 조작

| 키 | 동작 |
|---|---|
| W / S | 전진 / 후진 |
| A / D | 좌 / 우 회전 |
| E | 바라보는 블록 채굴 (기반암 제외, 사거리 6칸) |
| F | 바라보는 블록 면 앞에 선택한 블록 설치 |
| 1–5 | 핫바에서 블록 타입 선택 (잔디/흙/돌/나무/잎) |
| P / L | 월드+자세+인벤토리 저장 / 불러오기 (`save.fbw`) |
| Esc | 종료 |

## 성능 측정 기록 (2026-06-12, M-series Mac, Python 3.14)

- 실제 창 모드 6초 플레이: **46–53 FPS**
- 창 모드에서 회전하며 300프레임: 평균 19.8 ms/frame (**~50 FPS**)
- 헤드리스 120프레임(`--bench`): 평균 ~4.2 ms/frame
- 목표 10 FPS 대비 약 5배 여유. `tests/test_perf.py`가 회귀를 감시합니다.

옵션: `--seconds N`(N초 후 자동 종료, FPS를 stdout에 출력),
`--bench N`(N프레임 회전 벤치마크). 환경 변수 `FABLE_HEADLESS=1`(창 없이 실행),
`FABLE_DUMP=out.bmp`(프레임을 BMP로 래스터라이즈 — 시각 검증용).

## Fable 언어

동적 타입, 줄 단위 문장, C 비슷한 블록 문법. 확장자 `.fb`.

```text
# 주석
var x = 1.5                  # 전역(파일 최상위) 또는 지역(fn 안) 변수
fn dist(ax, ay, bx, by) {    # 함수 (최상위에만 정의)
  var dx = bx - ax
  var dy = by - ay
  return sqrt(dx * dx + dy * dy)
}
if x > 1 and x < 2 { print("between") } else { print("outside") }
while x < 10 { x = x + 1 }   # break / continue 지원
var a = [1, 2, 3]            # 배열, a[0] 인덱싱·대입
use "other.fb"               # 텍스트 include (중복 자동 제거)
```

값: 숫자(int/float), 문자열, 배열, `nil`, `true`/`false`(1/0).
연산자: `+ - * / %`, 비교, `and or not`(`&& || !`).

### 내장 함수 (전부 저수준)

- **그리기**: `gfx_open(w,h,scale,title)`, `gfx_rect(x,y,w,h,r,g,b)`,
  `gfx_text(x,y,s,r,g,b,size)`, `gfx_flush()`, `gfx_done()`
- **입력**: `key(name)` — 눌림 상태 0/1 (`"w"`, `"escape"`, …)
- **파일**: `read_text(path)`, `write_text(path,s)`
- **시간**: `clock_ms()`, `sleep_ms(n)`
- **수학**: `sin cos tan atan2 sqrt pow floor ceil abs min max pi()`
- **문자열/배열**: `str num len substr split arr push pop`
- **기타**: `print(v)`, `argv()`

3D 투영, 블록, 레이캐스팅을 아는 내장 함수는 없습니다. 난수조차 Fable 쪽
선형 합동 생성기(`src/world.fb`의 `rnd`)로 구현되어 있습니다.

## 구조

```
interpreter.py       렉서 → 파서 → 클로저 컴파일 트리 평가기 + 저수준 내장
examples/            언어 데모 (hello, fizzbuzz, primes)
src/state.fb         전역 게임 상태 (격자, 자세, 인벤토리, 레이캐스트 결과)
src/world.fb         격자 접근, LCG 난수, 절차적 지형, 저장/불러오기
src/raycast.fb       DDA 레이캐스팅 (격자 스텝, 거리, 면 판정, 직전 셀)
src/actions.fb       이동(축 분리 충돌), 회전, 채굴, 설치
src/render.fb        칼럼별 광선 → 거리 반비례 세로 스트립 + 안개/면 음영 + HUD
src/main.fb          메인 루프, 키 입력(엣지 검출), FPS 카운터
tests/*.fb           Fable로 작성된 검증 프로그램 (PASS/FAIL 출력)
tests/test_*.py      pytest 래퍼: 예제, 순수성 grep, 기하, 게임플레이, 성능
```

### 성능 비결

인터프리터는 AST를 매번 해석하지 않고 **Python 클로저로 미리 컴파일**합니다
(변수는 슬롯 인덱스로 해석, 이름 조회 없음). 렌더러는 240×150 내부 해상도를
픽셀 스케일 4로 키우고, 칼럼 폭 2픽셀 → 프레임당 광선 120개만 쏩니다.
