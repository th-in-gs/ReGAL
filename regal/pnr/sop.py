# Sum-of-products algebra used to inline internal signals into macro cells.
#
# A product term is a frozenset of (netname, polarity) literals, polarity
# being True for the signal itself and False for its complement. A SOP is a
# list of product terms: [] is constant 0 and [frozenset()] is constant 1.
# Operations return None once a SOP grows past MAX_TERMS, far more than a
# macro cell can hold, to keep the expansion bounded.

from quine_mccluskey.qm import QuineMcCluskey

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
    if sop is None:
        return None
    # De Morgan: ~(t0 | t1 | ...) = ~t0 & ~t1 & ..., with ~t a sum of the
    # complemented literals of t
    out = [frozenset()]
    for term in sop:
        out = sop_and(out, [frozenset([(n, not p)]) for n, p in term])
        if out is None:
            return None
    return out


def minimize(sop, complement=False, max_vars=12):
    # Two-level minimization (of the complement if asked) through the truth
    # table. Returns None if there are too many variables to enumerate.
    if sop is None:
        return None
    names = sorted({name for term in sop for name, _ in term})
    if len(names) > max_vars:
        return None

    def value(term, minterm):
        return all(((minterm >> names.index(name)) & 1) == polarity
                   for name, polarity in term)

    ones = [m for m in range(1 << len(names))
            if any(value(term, m) for term in sop) != complement]
    if not ones:
        return []
    if len(ones) == 1 << len(names):
        return [frozenset()]

    result = []
    for implicant in sorted(QuineMcCluskey().simplify(ones,
                                                       num_bits=len(names))):
        term = []
        for i, c in enumerate(implicant):
            name = names[len(names) - 1 - i]
            if c != "-":
                term.append((name, c == "1"))
        result.append(frozenset(term))
    return result
