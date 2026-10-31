# 23LC512 SQI SRAM on an 8052 external data bus

Two GAL16V8s let an 8052 use a Microchip 23LC512 (64 KB serial SRAM, SQI
mode) as ordinary external data memory: `MOVX` reads and writes work
unchanged. The 8052 has no wait-state input, so the sequencer GAL generates
the 8052's clock and slows it to about 4 MHz while a transfer runs, which
stretches `/RD` and `/WR`. It never stops the clock, so the 8052 does not
need to be fully static. It must accept clocks down to 3.5 MHz.

This is a design study. It has been simulated, not built.

## Parts

| Part | Role |
|---|---|
| GAL16V8 (-10 or faster), `seq.v` | Sequencer: SCK, /CS, nibble number K, 8052 clock, power-up init |
| GAL16V8, `sio.v` | Drives SIO with command nibbles, write data and the EQIO command |
| 74AC138 | Decodes K 8-11 to enable the address buffers |
| 2 × 74AC244 | Address nibbles onto SIO: A15-8 from P2, A7-0 from the latch |
| 74AC574 | Collects the two read nibbles and drives P0 while /RD is low |
| 74HC573 | The usual 8052 address latch |
| 27.75 MHz oscillator | Master clock: the 8052 runs at 13.875 MHz between transfers |
| 4 × 10 kΩ | Pull-ups on SIO0-3 |

## Connections

Sequencer (`seq.yaml`, registered mode): pin 1 master clock, 2 `/RD`,
3 `/WR`, 4 RST (the 8052's reset input), 11 to ground. Outputs: 19 SCK,
18-15 K0-K3, 14 `/CS`, 13 CPUCLK to the 8052's XTAL1 (XTAL2 open on CMOS
parts), 12 PEND.

SIO driver (`sio.yaml`, complex mode): pins 1-4 K0-K3, 5 PEND, 6-9 P0.0-3,
11 P0.4, 13-15 P0.5-7. Outputs: 19 SIO0, 18 SIO1, 17 SIO2, 12 SIO3.

74AC138: A = K0, B = K1, C = K2, G1 = K3, `/G2A` = K2, `/G2B` = ground. The
state search placed the address nibbles at K 10, 11, 8 and 9
(`encoding.py`), so Y2 enables A15-12, Y3 A11-8, Y0 A7-4 and Y1 A3-0.

74AC574: CLK = SCK, D0-3 = SIO0-3, D4-7 = Q0-3, Q0-7 = P0.0-7,
`/OE` = `/RD`. Each rising SCK shifts a nibble in. The feedback goes through
the output pins, which are enabled during the whole read. After the last
two data nibbles, P0 holds the byte.

## How a transfer runs

1. The sequencer sees `/RD` or `/WR` low on a master clock edge and pulls
   `/CS` low. Only `/CS` depends on these asynchronous inputs.
2. It sends READ (`0x03`) or WRITE (`0x02`) as two nibbles, then four
   address nibbles.
3. For a write it sends two data nibbles. For a read it waits two dummy
   cycles, then clocks in two data nibbles. Each read nibble gets two low SCK
   states, so the RAM's 25 ns output delay fits.
4. It holds `/CS` low for one more state (tCSH), then raises it.
5. It waits until `/RD` and `/WR` are both high, then returns to idle.

SCK runs at 13.875 MHz. A read keeps `/CS` low for 23 master clocks
(0.83 µs) and a write for 17 (0.61 µs).

At power-up every GAL register reads 1, which sets PEND. When the 8052
leaves reset, the sequencer sends EQIO (`0x38`) in SPI mode to switch the
RAM to SQI, keeping HOLD (SIO3) high, and clears PEND. A warm reset leaves
the RAM in SQI mode.

## Fitting

The sequencer's state is 5 bits of `t` (SCK is its low bit), `/CS` and
PEND. With a straightforward state assignment, five of its eight registers
needed 9 to 11 product terms. `gen/search.py` searches the free choices
with unreachable states as don't-cares:

- which K each command and data nibble uses within its decoder region
- the order of the address nibbles and of the EQIO bits
- the read data states
- the waiting states
- the pattern of the 8052 clock

It found assignments where every register fits. `gen/gen.py` writes the
minimized next-state equations into `seq.v`, because Yosys cannot use
don't-cares.

| Sequencer register | Product terms (of 8) |
|---|---|
| SCK, K1 | 7 |
| K0, K2, K3 | 6 |
| /CS | 5 |
| PEND | 2 |
| CPUCLK | 8 |

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
- The 23LC512 model covers SPI and SQI, sequential mode and HOLD. It checks
  tCSS, tCSH, tCSD and SIO contention.
- The 8052 runs random `MOVX` reads and writes, clocked from CPUCLK.

The 8052's requirements are Intel's formulas, with each period taken as the
actual, stretched one:

- read data valid at most 5 periods − 165 ns after `/RD` falls
- write data held until 7 periods − 150 ns after `/WR` falls

The timing assumes GAL16V8-10 (7 ns clock to output) and a 74AC574 (9 ns).

Results over 3 × 100,000 master clocks (about 3,600 transfers):

- Every byte read back is correct.
- There is no SIO contention.
- The RAM enters SQI mode at power-up.
- The 8052's clock periods stay between 72 and 252 ns.
- The worst read margin is 6 ns and the worst write margin is 200 ns.

## Limitations

- **The read margin is small.** It assumes the sequencer sees `/RD` on the
  first master clock edge after the 8052 drives it, that is within about
  20 ns after the XTAL1 edge. If the 8052 is slower, a read loses a master
  clock (36 ns) and misses Intel's limit. If your 8052 accepts slower
  clocks, longer slow phases restore the margin.
- **The address buffers need AC or ACT logic.** The '138 to '244 enable
  path must settle within one master clock before SCK rises. HC parts are
  too slow.
- **Turnaround overlap.** When K goes from the address region (K 8-11) to
  the SIO driver's region, the '244 releases SIO a few ns after the GAL
  starts driving. With AC parts the overlap is a few ns, but it is not
  zero.
- **Timers stretch too.** The 8052's timers count stretched clocks, so
  timing loops drift by the time spent in transfers.
