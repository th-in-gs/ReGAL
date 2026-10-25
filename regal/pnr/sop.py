# Sum-of-products algebra used to inline internal signals into macro cells.
#
# A product term is a frozenset of (netname, polarity) literals, polarity
# being True for the signal itself and False for its complement. A SOP is a
# list of product terms: [] is constant 0 and [frozenset()] is constant 1.
# Operations return None once a SOP grows past MAX_TERMS, far more than a
# macro cell can hold, to keep the expansion bounded.

from regal.espresso import espresso

MAX_TERMS = 64


def literal(netname, polarity=True):
    return [frozenset([(netname, polarity)])]


def simplify(sop):
    # Drop duplicate and absorbed terms (a term absorbs any superset of it)
    # while keeping the original order
    out = []
    for term in sop:
        if term not in out:
            out.append(term)
    return [t for t in out if not any(o < t for o in out)]


def sop_or(*sops):
    out = []
    for sop in sops:
        if sop is None:
            return None
        out += sop
    out = simplify(out)
    return out if len(out) <= MAX_TERMS else None


def sop_and(a, b):
    if a is None or b is None:
        return None
    out = []
    for ta in a:
        for tb in b:
            term = ta | tb
            if any((name, not pol) in term for name, pol in term):
                continue
            out.append(term)
            if len(out) > MAX_TERMS * 4:
                return None
    out = simplify(out)
    return out if len(out) <= MAX_TERMS else None


def sop_not(sop):
    return minimize(sop, complement=True)


def minimize(sop, complement=False):
    # Two-level minimization of a SOP (or of its complement if asked)
    if sop is None:
        return None
    names = sorted({name for term in sop for name, _ in term})
    cubes = []
    for term in sop:
        polarities = dict(term)
        cubes.append("".join(
            "-" if name not in polarities else "1" if polarities[name] else "0"
            for name in names
        ))

    result = []
    for cube in espresso(len(names), cubes, complement):
        result.append(frozenset(
            (name, c == "1") for name, c in zip(names, cube) if c != "-"
        ))
    return result
