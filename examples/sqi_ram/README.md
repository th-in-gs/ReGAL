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
| GAL16V8 (-10 or faster), `seq.v` | Sequencer: SCK, /CS, nibble number K, 8052 clock |
| GAL16V8, `sio.v` | Drives SIO with command nibbles and write data |
| 74AC138 | Decodes K 8-11 to enable the address buffers |
| 2 × 74AC244 | Address nibbles onto SIO: A15-8 from P2, A7-0 from the latch |
| 74AC574 | Collects the two read nibbles and drives P0 while /RD is low |
| 74HC573 | The usual 8052 address latch |
| 27.75 MHz oscillator | Master clock: the 8052 runs at 13.875 MHz between transfers |
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
state search placed the address nibbles at K 9, 10, 8 and 11
(`encoding.py`), so Y1 enables A15-12, Y2 A11-8, Y0 A7-4 and Y3 A3-0.

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
4. It holds `/CS` low for one more state (tCSH), then raises it.
5. It waits until `/RD` and `/WR` are both high, then returns to idle.

The datasheet's note that "the first byte read after the address will be
a dummy byte" suggests the RAM may already drive SIO during the dummy
cycles, so nothing else drives them then.

SCK runs at 13.875 MHz. A read keeps `/CS` low for 23 master clocks
(0.83 µs) and a write for 17 (0.61 µs).

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

The 8052 clock pattern is fixed: 2-3-4-3-4... master clocks per phase,
the longest pattern that keeps every period within 7 master clocks (the
first slow phase can follow a fast one).

The search found assignments where every register fits. `gen/gen.py` writes the
minimized next-state equations into `seq.v`, because Yosys cannot use
don't-cares.

| Sequencer register | Product terms (of 8) |
|---|---|
| K0, CPUCLK | 6 |
| K2 | 5 |
| SCK, K3 | 4 |
| K1, /CS, PEND | 3 |

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
  drives SIO from the read dummy cycles on. It checks
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
- The first write switches the RAM to SQI mode.
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
- **Turnaround overlap.** After the address, the '244 releases SIO a few
  ns after the next driver starts: the SIO GAL with write data, or the RAM
  with the read dummy byte. With AC parts the overlap is a few ns, but it
  is not zero.
- **The first `MOVX` must be the EQIO write.** Any other transfer before it
  goes to a RAM that is still in SPI mode.
- **Timers stretch too.** The 8052's timers count stretched clocks, so
  timing loops drift by the time spent in transfers.
