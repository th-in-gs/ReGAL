# Two-level logic minimization.
#
# espresso() is a heuristic in the style of Espresso-II: cubes are expanded
# as far as the complement of the function allows, redundant cubes are
# removed, and reduce/expand/irredundant passes are repeated while the cover
# keeps shrinking. The result is irredundant, not necessarily minimum.
#
# fit() uses a SAT solver to find a cover with at most a given number of
# cubes, which is what a macro cell needs, when the heuristic misses one.
#
# Cubes are ints in positional notation: bits 2i and 2i+1 are set when
# variable i may be 0 and 1 respectively ("0" = 01, "1" = 10, "-" = 11).

from pysat.solvers import Solver


class _Cover:
    def __init__(self, ninputs):
        self.n = ninputs
        self.full = (1 << (2 * ninputs)) - 1
        self.low = sum(1 << (2 * i) for i in range(ninputs))

    def var(self, i):
        return 3 << (2 * i)

    def empty(self, cube):
        # Some variable can be neither 0 nor 1
        return (cube | (cube >> 1)) & self.low != self.low

    def conflicts(self, a, b):
        # Low bits of the variables for which cubes a and b do not intersect
        both = a & b
        return ~(both | (both >> 1)) & self.low

    def size(self, cube):
        # Number of free variables, larger cubes cover more
        return bin(cube & (cube >> 1) & self.low).count("1")

    def cofactor(self, cover, cube):
        # Restriction of cover to the subspace of cube
        free = ~cube & self.full
        return [c | free for c in cover if not self.empty(c & cube)]

    def _split_var(self, cover):
        # Variable restricted in most cubes, preferring binate ones, or None
        # if no variable is binate
        best = None
        for i in range(self.n):
            zeros = ones = 0
            for c in cover:
                bits = (c >> (2 * i)) & 3
                zeros += bits == 1
                ones += bits == 2
            if zeros and ones and \
               (best is None or zeros + ones > best[0]):
                best = (zeros + ones, i)
        return None if best is None else best[1]

    def _split_any(self, cover):
        # Variable restricted in most cubes
        counts = [sum(((c >> (2 * i)) & 3) != 3 for c in cover)
                  for i in range(self.n)]
        return max(range(self.n), key=lambda i: (counts[i], -i))

    def tautology(self, cover):
        if not cover:
            return False
        if self.full in cover:
            return True
        i = self._split_var(cover)
        if i is None:
            # A unate cover is a tautology only if it has the full cube
            return False
        zero = 1 << (2 * i)
        one = 2 << (2 * i)
        return self.tautology(self.cofactor(cover, self.full & ~one)) and \
            self.tautology(self.cofactor(cover, self.full & ~zero))

    def complement(self, cover):
        if not cover:
            return [self.full]
        if self.full in cover:
            return []
        if len(cover) == 1:
            cube = cover[0]
            result = []
            for i in range(self.n):
                m = self.var(i)
                if cube & m != m:
                    result.append((self.full & ~m) | (~cube & m))
            return result

        i = self._split_any(cover)
        m = self.var(i)
        zero = 1 << (2 * i)
        one = 2 << (2 * i)
        c0 = self.complement(self.cofactor(cover, self.full & ~one))
        c1 = self.complement(self.cofactor(cover, self.full & ~zero))

        # Cubes in both halves do not depend on the variable
        in_c1 = set(c1)
        result = [c if c in in_c1 else c & ~one for c in c0]
        in_c0 = set(c0)
        result += [c & ~zero for c in c1 if c not in in_c0]
        return self.single_cube_containment(result)

    def single_cube_containment(self, cover):
        result = []
        for c in sorted(set(cover), key=lambda c: (-self.size(c), c)):
            if not any(c & ~d == 0 for d in result):
                result.append(c)
        return result

    def expand(self, cover, offset):
        result = []
        for cube in sorted(cover, key=lambda c: (-self.size(c), c)):
            if any(cube & ~d == 0 for d in result):
                continue
            while True:
                # A variable can be raised unless it is the only conflict
                # with a cube of the offset
                blocked = 0
                for r in offset:
                    conflict = self.conflicts(cube, r)
                    if conflict & (conflict - 1) == 0:
                        blocked |= conflict
                candidates = [
                    i for i in range(self.n)
                    if cube & self.var(i) != self.var(i) and
                    not blocked & (1 << (2 * i))
                ]
                if not candidates:
                    break

                # Raise the variable that covers most other cubes
                def gain(i):
                    raised = cube | self.var(i)
                    return sum(c & ~raised == 0 for c in cover)
                best = max(candidates, key=lambda i: (gain(i), -i))
                cube |= self.var(best)
            result.append(cube)
        return self.single_cube_containment(result)

    def irredundant(self, cover):
        result = list(cover)
        for cube in sorted(cover, key=lambda c: (self.size(c), c)):
            rest = [c for c in result if c != cube]
            if self.tautology(self.cofactor(rest, cube)):
                result = rest
        return result

    def reduce(self, cover):
        # Shrink each cube to the smallest cube containing the part of it
        # that no other cube covers
        result = sorted(cover, key=lambda c: (-self.size(c), c))
        for k, cube in enumerate(result):
            rest = result[:k] + result[k + 1:]
            uncovered = self.complement(self.cofactor(rest, cube))
            supercube = 0
            for c in uncovered:
                supercube |= c
            result[k] = cube & supercube
        return [c for c in result if not self.empty(c)]

    def cost(self, cover):
        literals = sum(self.n - self.size(c) for c in cover)
        return (len(cover), literals)

    def minimize(self, cover, offset):
        cover = self.irredundant(self.expand(cover, offset))
        while True:
            candidate = self.irredundant(
                self.expand(self.reduce(cover), offset))
            if self.cost(candidate) >= self.cost(cover):
                return cover
            cover = candidate


def _parse(cube):
    value = 0
    for i, c in enumerate(cube):
        value |= {"0": 1, "1": 2, "-": 3}[c] << (2 * i)
    return value


def _format(cube, ninputs):
    return "".join("?01-"[(cube >> (2 * i)) & 3] for i in range(ninputs))


def espresso(ninputs, cubes, complement=False):
    # Minimize a sum of products given as cubes: strings of "0", "1" and "-",
    # one character per input. With complement, the cubes describe where the
    # function is 0 and the minimized function is their complement.
    space = _Cover(ninputs)
    cover = []
    for cube in cubes:
        assert len(cube) == ninputs
        cover.append(_parse(cube))
    cover = [c for c in cover if not space.empty(c)]

    offset = space.complement(cover)
    if complement:
        cover, offset = offset, cover
    if not cover:
        return []

    minimized = space.minimize(cover, offset)
    return sorted(_format(cube, ninputs) for cube in minimized)


# Conflicts allowed to the SAT solver for each attempt, so that hopeless
# fits give up instead of trying to prove that no cover exists
_FIT_BUDGET = 20000


def fit(ninputs, cubes, max_cubes, complement=False):
    # Find a sum of at most max_cubes products equal to the function given
    # as cubes (or to its complement), or None if there is none or it cannot
    # be found within the conflict budget. Exact, unlike espresso.
    #
    # Each product j is described by whether it allows variable i to be 0
    # and to be 1. Products must not intersect the offset, and must together
    # cover onset points, added one at a time from counterexamples.
    space = _Cover(ninputs)
    cover = [c for c in (_parse(cube) for cube in cubes)
             if not space.empty(c)]
    offset = space.complement(cover)
    if complement:
        cover, offset = offset, cover
    if not cover:
        return []

    def allows(j, i, value):
        return 1 + 2 * (j * ninputs + i) + value

    solver = Solver(name="glucose4")
    try:
        for r in offset:
            restricted = [(i, (r >> (2 * i)) & 3) for i in range(ninputs)
                          if (r >> (2 * i)) & 3 != 3]
            for j in range(max_cubes):
                solver.add_clause([-allows(j, i, bits >> 1)
                                   for i, bits in restricted])

        next_var = 1 + 2 * max_cubes * ninputs

        def cover_point(cube):
            # Require some product to contain one point of cube
            nonlocal next_var
            point = [0 if (cube >> (2 * i)) & 1 else 1
                     for i in range(ninputs)]
            covers = []
            for j in range(max_cubes):
                covers.append(next_var)
                for i, value in enumerate(point):
                    solver.add_clause([-next_var, allows(j, i, value)])
                next_var += 1
            solver.add_clause(covers)

        for cube in cover:
            cover_point(cube)

        while True:
            solver.conf_budget(_FIT_BUDGET)
            if not solver.solve_limited():
                return None
            model = set(l for l in solver.get_model() if l > 0)
            candidate = []
            for j in range(max_cubes):
                cube = 0
                for i in range(ninputs):
                    for value in (0, 1):
                        if allows(j, i, value) in model:
                            cube |= 1 << (2 * i + value)
                if not space.empty(cube):
                    candidate.append(cube)

            missing = space.complement(candidate)
            uncovered = [c & m for c in cover for m in missing
                         if not space.empty(c & m)]
            if not uncovered:
                break
            cover_point(uncovered[0])
    finally:
        solver.delete()

    # Tidy up: prime and irredundant, which never adds products
    candidate = space.irredundant(space.expand(candidate, offset))
    return sorted(_format(cube, ninputs) for cube in candidate)
