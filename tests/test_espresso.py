import random

import pytest

from regal.espresso import espresso, fit


def _value(cubes, point):
    return any(all(c == "-" or int(c) == (point >> i) & 1
                   for i, c in enumerate(cube))
               for cube in cubes)


def _random_function(rng):
    n = rng.randint(1, 8)
    cubes = ["".join(rng.choice("01--") for _ in range(n))
             for _ in range(rng.randint(0, 10))]
    return n, cubes, rng.random() < 0.5


@pytest.mark.parametrize("seed", range(4))
def test_espresso(seed):
    rng = random.Random(seed)
    for _ in range(100):
        n, cubes, complement = _random_function(rng)
        result = espresso(n, cubes, complement)
        for point in range(1 << n):
            assert _value(result, point) == \
                (_value(cubes, point) != complement)
        # Irredundant: each cube covers a point that the others miss
        for i, cube in enumerate(result):
            rest = result[:i] + result[i + 1:]
            assert not all(_value(rest, point) for point in range(1 << n)
                           if _value([cube], point))


@pytest.mark.parametrize("seed", range(4))
def test_fit(seed):
    rng = random.Random(seed)
    for _ in range(50):
        n, cubes, complement = _random_function(rng)
        size = len(espresso(n, cubes, complement))
        for limit in range(max(size - 1, 0), size + 1):
            result = fit(n, cubes, limit, complement)
            if result is None:
                continue
            assert len(result) <= limit
            for point in range(1 << n):
                assert _value(result, point) == \
                    (_value(cubes, point) != complement)
        # A cover as large as the heuristic one always exists
        assert fit(n, cubes, size, complement) is not None


def test_fit_impossible():
    # Parity of 5 inputs needs 16 products
    cubes = [format(m, "05b") for m in range(32) if bin(m).count("1") % 2]
    assert fit(5, cubes, 8) is None
    assert len(fit(5, cubes, 16)) == 16
