"""성공 기준 1: Fable 예제 프로그램들이 인터프리터로 정상 실행된다."""
from conftest import run_fable


def test_hello():
    out = run_fable("examples/hello.fb")
    assert "Hello, Fable!" in out
    assert "2 plus 3, times 4 = 20" in out
    assert "sqrt(2) is about 1.414" in out
    assert "items: [10, 20, 30, 40] (len 4)" in out


def test_fizzbuzz():
    lines = run_fable("examples/fizzbuzz.fb").strip().split("\n")
    assert len(lines) == 15
    assert lines[2] == "Fizz"
    assert lines[4] == "Buzz"
    assert lines[14] == "FizzBuzz"
    assert lines[0] == "1"


def test_primes():
    out = run_fable("examples/primes.fb")
    assert "[2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]" in out
    assert "count: 15" in out
