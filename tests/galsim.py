import itertools
import random
import re

from regal.pnr.gal import Gal16v8


class Gal16v8Sim:
    # Functional model of a GAL16V8 programmed with a JEDEC file, following
    # the fuse conventions of regal.pnr.gal (a 0 fuse connects a column)

    def __init__(self, path):
        self.fuses = [0] * 2194
        with open(path, "r") as f:
            for offset, bits in re.findall(r"L(\d+) ([01]+) \*", f.read()):
                for i, bit in enumerate(bits):
                    self.fuses[int(offset) + i] = int(bit)

        syn, ac0 = self.fuses[2192], self.fuses[2193]
        self.mode = {(1, 0): "simple", (1, 1): "complex",
                     (0, 1): "registered"}[(syn, ac0)]
        self.gal = Gal16v8(self.mode)
        self.registered = [
            ci for ci in range(8)
            if self.mode == "registered" and self.fuses[2120 + ci] == 0
        ]
        self.state = {self.gal.cells[ci].outpad: 0 for ci in self.registered}

    def _term(self, ci, row, values):
        if not self.fuses[2128 + ci * 8 + row]:
            return 0
        line = self.fuses[(ci * 8 + row) * 32:(ci * 8 + row + 1) * 32]
        term = 1
        for i, pad in enumerate(self.gal.inpads):
            value = values.get(pad, 0)
            if line[2 * i] == 0:
                term &= value
            if line[2 * i + 1] == 0:
                term &= 1 - value
        return term

    def _sum(self, ci, rows, values):
        value = 0
        for row in rows:
            value |= self._term(ci, row, values)
        return value if self.fuses[2048 + ci] else 1 - value

    def outputs(self, inputs):
        # Pin values for the given input pin values, with combinational
        # feedback settled. Disabled outputs read as None.
        values = dict(inputs)
        values.update(self.state)
        for _ in range(16):
            settled = dict(values)
            for ci, cell in enumerate(self.gal.cells):
                pad = cell.outpad
                if ci in self.registered or pad in inputs:
                    continue
                if self.mode == "simple":
                    settled[pad] = self._sum(ci, range(8), values)
                elif self._term(ci, 0, values):
                    settled[pad] = self._sum(ci, range(1, 8), values)
                else:
                    settled[pad] = None
            if settled == values:
                return values
            values = settled
        raise AssertionError("combinational feedback does not settle")

    def clock(self, inputs):
        values = self.outputs(inputs)
        self.state = {
            self.gal.cells[ci].outpad: self._sum(ci, range(8), values)
            for ci in self.registered
        }


def assert_equivalent(expected, actual, pins, ports, cycles=2000):
    # Check that two JEDEC files behave the same on the output pins assigned
    # in pins, exhaustively for combinational designs and over random input
    # sequences for registered ones
    sim_expected = Gal16v8Sim(expected)
    sim_actual = Gal16v8Sim(actual)
    assert sim_expected.mode == sim_actual.mode

    inputs = [n for n in pins if n in ports and
              ports[n]["direction"] == "input" and
              not (sim_actual.mode == "registered" and pins[n] == 1)]
    outputs = [n for n in pins if n in ports and
               ports[n]["direction"] == "output"]

    if sim_actual.mode == "registered":
        rng = random.Random(0)
        stimuli = ([rng.randrange(2) for _ in inputs] for _ in range(cycles))
    else:
        stimuli = itertools.product([0, 1], repeat=len(inputs))

    for step, stimulus in enumerate(stimuli):
        values = {pins[n]: v for n, v in zip(inputs, stimulus)}
        got = sim_actual.outputs(values)
        want = sim_expected.outputs(values)
        for name in outputs:
            assert got[pins[name]] == want[pins[name]], \
                "{} differs at step {} with inputs {}".format(
                    name, step, dict(zip(inputs, stimulus)))
        if sim_actual.mode == "registered":
            sim_actual.clock(values)
            sim_expected.clock(values)
