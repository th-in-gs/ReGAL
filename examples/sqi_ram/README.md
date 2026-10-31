# 23LC512 SQI SRAM on an 8052 external data bus

Two GAL16V8s let an 8052 use a Microchip 23LC512 (64 KB serial SRAM, SQI
mode) as ordinary external data memory: `MOVX` reads and writes work
unchanged. The 8052 has no wait-state input, so the sequencer GAL generates
the 8052's clock: 16 MHz normally, slowed to about 3.6 MHz while a
transfer runs, which stretches `/RD` and `/WR`. It never stops the clock,
so the 8052 does not need to be fully static. It must accept clocks down
to 3.5 MHz. SCK runs at 16 MHz, within the RAM's limit for both its
industrial (20 MHz) and extended (16 MHz) temperature grades.

This is a design study. It has been simulated, not built. `kicad/` has
the schematic, with footprints, and `seq.jed` and `sio.jed` are the fuse
maps to program the GALs with.

## Parts

| Part | Role |
|---|---|
| GAL16V8 (-10 or faster), `seq.v` | Sequencer: SCK, /CS, nibble number K, 8052 clock |
| GAL16V8, `sio.v` | Drives SIO with command nibbles and write data |
| 74AC138 | Decodes K 8-11 to enable the address buffers |
| 2 × 74AC244 | Address nibbles onto SIO: A15-8 from P2, A7-0 from the latch |
| 74AC574 | Collects the two read nibbles and drives P0 while /RD is low |
| 74HC573 | The usual 8052 address latch |
| 32 MHz oscillator | Master clock: the 8052 and SCK run at 16 MHz |
| 4 × 10 kΩ | Pull-ups on SIO0-3 |

## Connections

Sequencer (`seq.yaml`, registered mode): pin 1 master clock, 2 `/RD`,
3 `/WR`, 11 to ground. Outputs: 19 SCK,
18-15 K0-K3, 14 `/CS`, 13 CPUCLK to the 8052's XTAL1 (XTAL2 open on CMOS
parts), 12 PEND.

SIO driver (`sio.yaml`, complex mode): pins 1-4 K0-K3, 5 PEND, 6 `/WR`,
7-9 P0.0-2, 11 P0.3, 13-16 P0.4-7. Outputs: 19 SIO0, 18 SIO1, 17 SIO2,
12 SIO3.

74AC138: A = K0, B = K1, C = K2, G1 = K3, `/G2A` = K2, `/G2B` = ground. The
state search placed the address nibbles at K 8, 10, 11 and 9
(`encoding.py`), so Y0 enables A15-12, Y2 A11-8, Y3 A7-4 and Y1 A3-0.

74AC574: CLK = SCK, D0-3 = SIO0-3, D4-7 = Q0-3, Q0-7 = P0.0-7,
`/OE` = `/RD`. Each rising SCK shifts a nibble in. The feedback goes through
the output pins, which are enabled during the whole read. After the last
two data nibbles, P0 holds the byte.

## How a transfer runs

1. The sequencer sees `/RD` or `/WR` low on a master clock edge and pulls
   `/CS` low. Only `/CS` depends on these asynchronous inputs.
2. It sends READ (`0x03`) or WRITE (`0x02`) as two nibbles, then four
   address nibbles.
3. For a write it sends two data nibbles. For a read it lets the RAM have
   SIO for the two dummy cycles and then clocks in two data nibbles. Each
   read nibble gets two low SCK states, so the RAM's 25 ns output delay
   fits.
4. It holds `/CS` low with SCK high for one more state after a write, and
   three after a read, then raises it. One is enough for tCSH. The other
   two keep the 8052's clock slow until it has sampled the data.
5. It waits until `/RD` and `/WR` are both high, then returns to idle.
   After a read it waits at K 4, which nobody drives, because the RAM
   keeps driving SIO for up to 20 ns (tDIS) after `/CS` rises.

The datasheet's note that "the first byte read after the address will be
a dummy byte" suggests the RAM may already drive SIO during the dummy
cycles, so nothing else drives them then.

Each state is one master clock (31.25 ns). A read keeps `/CS` low for 25
states (0.78 µs) and a write for 17 (0.53 µs).

### Why not 20 MHz

SCK is a register that toggles every master clock, and so is the 8052's
clock between transfers. 20 MHz SCK would need a 40 MHz master clock and
the 8052 at a third of it (13.3 MHz). That needs another register, and
all eight are in use. 32 MHz runs the 8052 at its rated 16 MHz with SCK
at 16 MHz, and the read margin comes from slowing the 8052 anyway.

### Switching the RAM to SQI mode

The 23LC512 powers up in SPI mode, where it only reads SI (SIO0) and HOLD
(SIO3). At power-up every GAL register reads 1, which sets PEND. While
PEND is set, the SIO driver sends `1110` for both command nibbles. As a
result, the first transfer, a write of `0x88` to `0x9998`, puts EQIO
(`0x38`) on SI with HOLD high throughout. The RAM switches to SQI mode, and
PEND clears at the end of the transfer. The startup code must therefore
begin with:

```asm
        MOV     DPTR, #9998h
        MOV     A, #88h
        MOVX    @DPTR, A        ; EQIO: switch the 23LC512 to SQI mode
```

A warm reset leaves both the RAM and PEND as they were. If the startup
code runs this write again, the RAM is already in SQI mode and stores
`0x88` at `0x9998`, so reserve that byte.

## Fitting

The sequencer's state is 5 bits of `t` (SCK is its low bit), `/CS` and
PEND. The state assignment matters: with a straightforward one, an
earlier version of this design needed up to 11 product terms per
register. `gen/search.py` searches the free choices with unreachable
states as don't-cares:

- which K each command and data nibble uses within its region
- the order of the address nibbles
- the states for the dummy cycles, read data and CS hold
- the waiting states

The 8052 clock pattern is fixed: 2-6-3-6-3... master clocks per phase,
the slowest pattern that keeps every period within 9 master clocks
(281 ns, 3.56 MHz). The first slow phase can follow a fast one.

The search found assignments where every register fits. `gen/gen.py` writes the
minimized next-state equations into `seq.v`, because Yosys cannot use
don't-cares.

| Sequencer register | Product terms (of 8) |
|---|---|
| K0, CPUCLK | 7 |
| SCK | 6 |
| K1, K3, /CS | 5 |
| K2, PEND | 3 |

To rebuild:

```console
python gen/gen.py gen/encoding.json .
regal build -o seq.jed seq.yaml seq.v
regal build -o sio.jed sio.yaml sio.v
python bench.py
```

## Simulation

`bench.py` simulates the system at master clock resolution:

- Both GALs are simulated from their fuse maps.
- The 23LC512 model covers SPI and SQI, sequential mode and HOLD, and
  drives SIO from the read dummy cycles on and until tDIS after `/CS`
  rises. It checks tCSS, tCSH, tCSD and SIO contention.
- The 8052 runs random `MOVX` reads and writes, clocked from CPUCLK.

The 8052's requirements are Intel's formulas, with each period taken as the
actual, stretched one:

- read data valid at most 5 periods − 165 ns after `/RD` falls
- write data held until 7 periods − 150 ns after `/WR` falls

The timing assumes GAL16V8-10 (7 ns clock to output) and a 74AC574 (9 ns).

Results over 3 × 100,000 master clocks (about 3,550 transfers):

- Every byte read back is correct.
- There is no SIO contention.
- The first write switches the RAM to SQI mode.
- The 8052's clock periods stay between 62.5 and 281 ns.
- The worst read margin is 76 ns and the worst write margin is 215 ns.

A fourth run has the GALs see `/RD` and `/WR` one master clock late, as
if the 8052 were slow to drive them. It still passes: read margin 14 ns,
write margin 152 ns.

## Limitations

- **The 8052 runs at its maximum rated clock**, 16 MHz, between
  transfers. Baud rates change with the crystal: 16 MHz is not a
  standard UART frequency.
- **The address buffers need AC or ACT logic.** The '138 to '244 enable
  path must settle within one master clock before SCK rises. HC parts are
  too slow.
- **Turnaround overlap.** After the address, the '244 releases SIO a few
  ns after the next driver starts: the SIO GAL with write data, or the RAM
  with the read dummy byte. With AC parts the overlap is a few ns, but it
  is not zero.
- **The first `MOVX` must be the EQIO write.** Any other transfer before it
  goes to a RAM that is still in SPI mode.
- **Timers stretch too.** The 8052's timers count stretched clocks, so
  timing loops drift by the time spent in transfers.
