# System simulation of the 8052 to 23LC512 SQI interface, at master clock
# resolution, using the fuse maps produced by ReGAL for the two GALs.
#
# Models: GAL fuse maps (tests/galsim.py), 74AC138, 74AC244s, 74AC574,
# 23LC512 (SPI and SQI, sequential mode) and the 8052 external data bus,
# clocked from CPUCLK. Timing requirements of the 8052 are Intel's
# formulas with each period taken as the actual, possibly stretched one:
#   read:  data valid at most 5 periods - 165 ns after /RD falls
#   write: data held until 7 periods - 150 ns after /WR falls
#          (tWLWH = 6T - 100 plus tWHQX = T - 50)
#
# Usage: python bench.py [cycles]

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tests"))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

from galsim import Gal16v8Sim  # noqa: E402

from encoding import ADDRESS_K  # noqa: E402

MASTER_NS = 1e3 / 27.75
GAL_TCO = 7          # GAL16V8-10 clock to output
AC574_TCO = 9        # 74AC574 clock to output
RAM_TCSS, RAM_TCSH, RAM_TCSD = 25, 50, 25

SEQ_PINS = dict(RD_n=2, WR_n=3, SCK=19, K0=18, K1=17, K2=16, K3=15,
                CS_n=14, CPUCLK=13, PEND=12)
SIO_PINS = dict(K0=1, K1=2, K2=3, K3=4, PEND=5, WR_n=6, D0=7, D1=8, D2=9,
                D3=11, D4=13, D5=14, D6=15, D7=16, SIO0=19, SIO1=18,
                SIO2=17, SIO3=12)


class Fail(Exception):
    pass


class Ram:
    # 23LC512: SPI at power-up, EQIO switches to SQI, sequential mode
    def __init__(self, rng):
        self.mem = [rng.randrange(256) for _ in range(65536)]
        self.sqi = False
        self.cs = False
        self.drive = self.releasing = None
        self.cs_rise_ns = -1e9

    def cs_change(self, low, now):
        if low and not self.cs:
            if now - self.cs_rise_ns < RAM_TCSD:
                raise Fail("CS high for less than tCSD")
            self.cs, self.clocks, self.bits, self.drive = True, 0, [], None
            self.cs_fall_ns = now
        elif not low and self.cs:
            if self.clocks and now - self.last_rise_ns < RAM_TCSH:
                raise Fail("CS hold time {:.0f} ns".format(
                    now - self.last_rise_ns))
            if not self.sqi:
                if self.bits[:8] == [0, 0, 1, 1, 1, 0, 0, 0] and \
                   len(self.bits) == 8:
                    self.sqi = True
                elif self.bits:
                    raise Fail("unexpected SPI command {}".format(self.bits))
            # Outputs are disabled up to tDIS = 20 ns after CS rises
            self.releasing, self.drive = self.drive, None
            self.cs = False
            self.cs_rise_ns = now

    def rise(self, sio, now):
        if not self.cs:
            return
        if self.clocks == 0 and now - self.cs_fall_ns < RAM_TCSS:
            raise Fail("CS setup time")
        self.last_rise_ns = now
        self.clocks += 1
        if not self.sqi:
            if sio[3] != 1:
                raise Fail("HOLD low in SPI mode")
            self.bits.append(sio[0])
            return
        if None in sio:
            if self.clocks <= 6 or (self.clocks <= 8 and self.cmd == 2):
                raise Fail("floating SIO sampled at clock {}".format(
                    self.clocks))
        nib = sum(b << i for i, b in enumerate(sio) if b is not None)
        c = self.clocks
        if c == 1:
            self.cmd = nib << 4
        elif c == 2:
            self.cmd |= nib
            if self.cmd not in (2, 3):
                raise Fail("unexpected SQI command {:02x}".format(self.cmd))
        elif c <= 6:
            self.addr = (self.addr << 4 | nib) if c > 3 else nib
        elif self.cmd == 2:
            if c % 2 == 1:
                self.hi = nib
            else:
                self.mem[self.addr] = self.hi << 4 | nib
                self.writes.append((self.addr, self.mem[self.addr]))
                self.addr = (self.addr + 1) & 0xffff

    def fall(self, rng):
        # Reads: the RAM is assumed to drive SIO from the dummy byte on
        if not self.cs or not self.sqi or self.cmd != 3 or self.clocks < 6:
            return
        k = self.clocks - 8
        if k < 0:
            self.drive = rng.randrange(16)
            return
        byte = self.mem[(self.addr + k // 2) & 0xffff]
        self.drive = (byte >> 4, byte & 15)[k % 2]


class Cpu:
    # External data bus of an 8052 executing random MOVX
    def __init__(self, rng, ram):
        self.rng, self.ram = rng, ram
        self.rst = True
        self.rd = self.wr = True
        self.edges = []          # times of CPUCLK rising edges
        self.gap = 200
        self.op = None
        self.done = 0
        self.model = list(ram.mem)

    def rising(self, now):
        self.edges.append(now)
        if self.rst:
            if len(self.edges) > 100:
                self.rst = False
                self.gap = 20
            return
        if self.op is None:
            self.gap -= 1
            if self.gap <= 0:
                write = self.rng.random() < 0.5
                addr = self.rng.randrange(65536)
                data = self.rng.randrange(256)
                if not self.ram.sqi:
                    # First transfer: EQIO, sent as a write of 0x88 to 0x9998
                    write, addr, data = True, 0x9998, 0x88
                self.op = dict(write=write, addr=addr, data=data,
                               start=len(self.edges) - 1)
                if write:
                    self.wr = False
                else:
                    self.rd = False
                self.ram.writes = []
            return
        n = len(self.edges) - 1 - self.op["start"]
        t0 = self.edges[self.op["start"]]
        if not self.op["write"] and n == 5:
            need = now - 165
            if self.p0_valid_ns is None or self.p0_valid_ns > need:
                raise Fail("read data late by {} ns".format(
                    None if self.p0_valid_ns is None
                    else round(self.p0_valid_ns - need)))
            self.margins.append(("read", need - self.p0_valid_ns))
            if self.p0 != self.model[self.op["addr"]]:
                raise Fail("read {:04x} gave {:02x}, expected {:02x}".format(
                    self.op["addr"], self.p0, self.model[self.op["addr"]]))
        if n == 6:
            self.rd = self.wr = True
        if self.op["write"] and n == 7 and self.done == 0:
            if not self.ram.sqi or self.ram.writes:
                raise Fail("the first write did not send EQIO")
        elif self.op["write"] and n == 7:
            # P0 data held until 7T - 150 after /WR falls
            held = now - 150
            if self.ram.writes != [(self.op["addr"], self.op["data"])]:
                raise Fail("write {:04x}={:02x} gave {}".format(
                    self.op["addr"], self.op["data"], self.ram.writes))
            self.margins.append(("write", held - (self.last_sample_ns + 10)))
            self.model[self.op["addr"]] = self.op["data"]
        if n >= 8:
            self.periods.append((now - t0) / n)
            self.op = None
            self.done += 1
            self.gap = self.rng.randrange(12, 40)


def run(cycles, seed=1):
    rng = random.Random(seed)
    seq = Gal16v8Sim(os.path.join(HERE, "seq.jed"))
    sio = Gal16v8Sim(os.path.join(HERE, "sio.jed"))
    # GAL registers read 1 at power-up
    seq.state = {pad: 1 for pad in seq.state}
    ram = Ram(rng)
    cpu = Cpu(rng, ram)
    cpu.margins, cpu.periods = [], []
    cpu.p0, cpu.p0_valid_ns = None, None
    capture = 0           # 74AC574 contents, Q7-0
    stats = dict(phases=[], cs_low=[])
    prev = dict(seq.outputs({}))
    bus = [1, 1, 1, 1]
    last_ck_edge, ck_level = 0.0, 1
    cs_fall = None

    for n in range(cycles):
        now = n * MASTER_NS
        values = {SEQ_PINS["RD_n"]: int(cpu.rd), SEQ_PINS["WR_n"]: int(cpu.wr)}
        seq.clock(values)
        out = seq.outputs(values)
        sig = {name: out[pin] for name, pin in SEQ_PINS.items()
               if name not in ("RD_n", "WR_n")}
        tq = now + GAL_TCO

        # SCK and CS edges, sampling the bus as it was before this edge
        if sig["CS_n"] != prev[SEQ_PINS["CS_n"]]:
            ram.cs_change(not sig["CS_n"], tq)
            if not sig["CS_n"]:
                cs_fall = now
            else:
                stats["cs_low"].append(round((now - cs_fall) / MASTER_NS))
        if sig["SCK"] and not prev[SEQ_PINS["SCK"]]:
            ram.rise(bus, tq)
            cpu.last_sample_ns = tq
            capture = (capture << 4 | (sum(
                (b if b is not None else 1) << i for i, b in enumerate(bus))))
            capture &= 0xff
            cpu.p0 = capture
            cpu.p0_valid_ns = tq + AC574_TCO
        elif not sig["SCK"] and prev[SEQ_PINS["SCK"]]:
            ram.fall(rng)
        if cpu.rd:
            cpu.p0_valid_ns = None

        # SIO bus after this edge
        k = sig["K0"] | sig["K1"] << 1 | sig["K2"] << 2 | sig["K3"] << 3
        op = cpu.op or dict(addr=0, data=0, write=False)
        d = op["data"] if op["write"] else rng.randrange(256)
        sin = {SIO_PINS["K%d" % i]: (k >> i) & 1 for i in range(4)}
        sin[SIO_PINS["PEND"]] = sig["PEND"]
        sin[SIO_PINS["WR_n"]] = int(cpu.wr)
        for i in range(8):
            sin[SIO_PINS["D%d" % i]] = (d >> i) & 1
        sout = sio.outputs(sin)
        drivers = [[] for _ in range(4)]
        for i in range(4):
            v = sout[SIO_PINS["SIO%d" % i]]
            if v is not None:
                drivers[i].append(("SIO GAL", v))
        if k in ADDRESS_K:
            shift = 12 - 4 * ADDRESS_K.index(k)
            for i in range(4):
                drivers[i].append(("244", (op["addr"] >> (shift + i)) & 1))
        for drive in (ram.drive, ram.releasing):
            if drive is not None:
                for i in range(4):
                    drivers[i].append(("RAM", (drive >> i) & 1))
        ram.releasing = None
        for i in range(4):
            if len(drivers[i]) > 1:
                raise Fail("SIO{} driven by {} at K={}".format(
                    i, [x[0] for x in drivers[i]], k))
        bus = [x[0][1] if x else None for x in drivers]

        # 8052 clock
        if sig["CPUCLK"] != ck_level:
            stats["phases"].append(round((now - last_ck_edge) / MASTER_NS))
            last_ck_edge, ck_level = now, sig["CPUCLK"]
            if ck_level:
                cpu.rising(tq)

        prev = out

    phases = stats["phases"][10:]
    return dict(
        transfers=cpu.done, sqi=ram.sqi,
        read_margin_ns=round(min(m for k, m in cpu.margins if k == "read")),
        write_margin_ns=round(min(m for k, m in cpu.margins if k == "write")),
        longest_phase=max(phases), shortest_phase=min(phases),
        longest_period_ns=round(max(
            a + b for a, b in zip(phases, phases[1:])) * MASTER_NS),
        cs_low_cycles=sorted(set(stats["cs_low"])),
        mean_movx_period_ns=round(sum(cpu.periods) / len(cpu.periods), 1)
        if cpu.periods else None,
    )


if __name__ == "__main__":
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 200000
    for seed in (1, 2, 3):
        print(run(cycles, seed))
