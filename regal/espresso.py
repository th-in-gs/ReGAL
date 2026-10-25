from pyeda.boolalg import espresso as _espresso

# Cube literal encoding used by pyeda's espresso
_ENCODE = {"0": 1, "1": 2, "-": 3}
_DECODE = {1: "0", 2: "1", 3: "-"}


def espresso(ninputs, cubes, complement=False):
    # Minimize a sum of products given as cubes: strings of "0", "1" and "-",
    # one character per input. With complement, the cubes describe where the
    # function is 0 and the minimized function is their complement.
    cover = set()
    for cube in cubes:
        assert len(cube) == ninputs
        cover.add((tuple(_ENCODE[c] for c in cube), (0 if complement else 1,)))

    if not cover:
        return ["-" * ninputs] if complement else []

    minimized = _espresso.espresso(
        ninputs, 1, cover,
        intype=_espresso.RTYPE if complement else _espresso.FTYPE
    )
    return sorted("".join(_DECODE[v] for v in cube) for cube, _ in minimized)
