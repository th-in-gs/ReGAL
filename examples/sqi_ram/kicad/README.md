# KiCad project

`sqi_ram.kicad_sch` is the interface as a KiCad 7 schematic, which KiCad 8
and 9 also open, and `sqi_ram.kicad_pcb` is a ready-routed board for it.
All parts are through-hole DIP packages, with sockets for the two GALs so
they can be reprogrammed.

## Opening it

Open `sqi_ram.kicad_pro` in KiCad. The symbols are embedded in the
schematic. The 23LC512, which the KiCad libraries lack, is also in the
project library `sqi_ram.kicad_sym`, which `sym-lib-table` adds.

Nets that connect to the 8052 use global labels:

| Label | Connect to |
|---|---|
| `AD0`-`AD7` | P0 |
| `A0`-`A7` | the outputs of the 8052's address latch |
| `A8`-`A15` | P2 |
| `~{RD}`, `~{WR}` | P3.7 and P3.6 |
| `CPUCLK` | XTAL1. Remove the crystal and its capacitors; on a CMOS 80C52 leave XTAL2 open (an NMOS 8052 is driven on XTAL2 instead) |
| `VCC`, `GND` | 5 V supply |

There are two ways to use it:

- **Add it to an existing design.** In the existing schematic, add a
  hierarchical sheet that uses `sqi_ram.kicad_sch`, and copy
  `sqi_ram.kicad_sym` and its `sym-lib-table` entry into that project.
  Global labels connect by name, so either name the 8052's nets as above or
  rename the labels here.
- **Use the board below.** It is a separate module that connects to the
  8052 board through the J1 header.

If you change the schematic, run Tools > Update PCB from Schematic (F8) in
the PCB editor: the footprints are linked to their symbols. Keep the
32 MHz oscillator, U1, SCK and the 23LC512 close together, and each chip's
100 nF capacitor right at its supply pins.

## PCB

`sqi_ram.kicad_pcb` is a 95 × 72 mm two-layer board, all through-hole,
with M3 mounting holes in the corners and ground pours on both sides.
`sqi_ram-gerbers.zip` holds the Gerbers and Excellon drill files to upload
to a board house.

| Rule | Value |
|---|---|
| Signal tracks | 0.25 mm |
| VCC and GND tracks | 0.5 mm |
| Clearance | 0.2 mm |
| Vias | 0.7 mm (0.35 mm drill), 0.8 mm (0.4 mm drill) on supplies |

Any standard two-layer service can make it.

The 8052 connects through J1, a 2×16 pin header:

| J1 pins | Signal |
|---|---|
| 1, 32 | VCC |
| 2, 29, 31 | GND |
| 3-10 | AD0-AD7 (P0) |
| 11-18 | A0-A7 (address latch outputs) |
| 19-26 | A8-A15 (P2) |
| 27, 28 | `/RD`, `/WR` |
| 30 | CPUCLK (to XTAL1), between two grounds |

Keep the cable to the 8052 board short (10 cm or less): it carries the
16 MHz clock and the data bus.

KiCad's DRC on the board finds no violations and no unconnected pads, and
every pad's net matches the schematic's netlist. The tracks are an
autorouter's: they work, but you may want to tidy them in KiCad.

### Rebuilding the board

```console
python make_pcb.py place     # unrouted board and sqi_ram.dsn
FREEROUTING_JAR=freerouting.jar python make_pcb.py route
python make_pcb.py import    # tracks from sqi_ram.ses, ground pours, DRC
```

`route` runs [Freerouting](https://freerouting.app) (2.5 needs Java 25) with
automatic neck-down off, so that every track keeps its net class width.
`import` reads Freerouting's session file and adds the ground pours. Where
the tracks leave room for only one thermal spoke, it connects the pad to
the pour solidly. `sqi_ram.ses` is committed, so `import` alone rebuilds
this board.

## Parts

| Ref | Part | Notes |
|---|---|---|
| U1 | GAL16V8 or ATF16V8B, 15 ns or faster | Sequencer: program with `../seq.jed` |
| U2 | GAL16V8 or ATF16V8B, 15 ns or faster | SIO driver: program with `../sio.jed` |
| U3 | 74AC138 or 74ACT138 | Not HC: the address enable path is timing-critical |
| U4, U5 | 74AC244 or 74ACT244 | Not HC, as above |
| U6 | 74AC574 or 74ACT574 | |
| U7 | 23LC512-I/P | 64 KB SPI/SQI SRAM, DIP-8 |
| X1 | 32 MHz oscillator, DIP-8 can, 5 V | |
| R1-R4 | 10 kΩ | SIO pull-ups |
| J1 | 2×16 pin header, 2.54 mm | To the 8052 board |
| C1-C7 | 100 nF | Decoupling |

GAL16V8s from Lattice are no longer made. The Microchip (Atmel) ATF16V8B is
the current equivalent and takes the same JEDEC files. Choose 10 ns parts
if you can: with 15 ns parts the address path has only about 4 ns to spare
at 32 MHz. Programmers such as the TL866II+ and T48 handle both.

## Software

The first `MOVX` after power-up must switch the RAM to SQI mode:

```asm
        MOV     DPTR, #9998h
        MOV     A, #88h
        MOVX    @DPTR, A
```

See `../README.md` for how the design works and its limitations.

## Regenerating

`make_schematic.py` writes the schematic from `../seq.yaml`, `../sio.yaml`
and `../encoding.py`. `check_schematic.py` exports the netlist with
`kicad-cli` and checks it against the design. It verifies:

- every pin's net
- that unused pins are only the intended ones
- footprint pads
- that each address nibble reaches SIO0-3 in bit order at the nibble number
  where the sequencer expects it
- the 74AC574 shift path
- the 23LC512 pinout

If you edit the schematic by hand, check it again with
`python check_schematic.py`.
