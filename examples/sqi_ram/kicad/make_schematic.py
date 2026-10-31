# Writes sqi_ram.kicad_sch, the schematic of the 8052 to 23LC512 interface,
# from the GAL pin assignments (../seq.yaml, ../sio.yaml) and the address
# nibble order (../encoding.py). Symbols come from the KiCad libraries
# (KICAD_SYMBOL_DIR, /usr/share/kicad/symbols by default) and are embedded
# in the schematic, except the 23LC512, which they do not have.
#
# Every pin gets a label at its connection point; the signals shared with
# the 8052 (AD0-7, A0-15, ~{RD}, ~{WR}, CPUCLK) are global labels, so that
# the sheet connects by name to the rest of the design.
#
# Usage: python make_schematic.py, then check with check_schematic.py

import os
import sys
import uuid

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from encoding import ADDRESS_K  # noqa: E402

SYMBOL_DIR = os.environ.get("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols")
PROJECT = "sqi_ram"

# Signals shared with the 8052 and its address latch
GLOBAL = {"AD%d" % i for i in range(8)} | {"A%d" % i for i in range(16)} | \
    {"~{RD}", "~{WR}", "CPUCLK"}

_uuid_ns = uuid.UUID("8f2b8c1e-3f7a-4a7e-9a59-5a1b2c3d4e5f")


def uid(*key):
    # Stable UUIDs, so that regenerating the schematic gives the same file
    return str(uuid.uuid5(_uuid_ns, "/".join(str(k) for k in key)))


# S-expressions ---------------------------------------------------------

class Sym(str):
    pass


def parse(text):
    pos = 0

    def skip():
        nonlocal pos
        while pos < len(text) and text[pos].isspace():
            pos += 1

    def item():
        nonlocal pos
        skip()
        if text[pos] == "(":
            pos += 1
            out = []
            while True:
                skip()
                if text[pos] == ")":
                    pos += 1
                    return out
                out.append(item())
        if text[pos] == '"':
            pos += 1
            out = []
            while text[pos] != '"':
                if text[pos] == "\\":
                    pos += 1
                out.append(text[pos])
                pos += 1
            pos += 1
            return "".join(out)
        start = pos
        while not text[pos].isspace() and text[pos] not in "()":
            pos += 1
        return Sym(text[start:pos])

    return item()


def dump(x, indent=0):
    if isinstance(x, list):
        inner = [dump(y, indent + 1) for y in x]
        flat = "(" + " ".join(inner) + ")"
        if len(flat) < 100 and "\n" not in flat:
            return flat
        pad = "\n" + "  " * (indent + 1)
        return "(" + inner[0] + "".join(pad + y for y in inner[1:]) + ")"
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, (int, float)):
        return ("%.4f" % x).rstrip("0").rstrip(".")
    return '"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"'


def find(x, head):
    return [y for y in x if isinstance(y, list) and y and y[0] == head]


def S(*items):
    return [Sym(items[0])] + list(items[1:])


def font(*extra):
    return S("effects", S("font", S("size", 1.27, 1.27)), *extra)


def hidden_font():
    return S("effects", S("font", S("size", 1.27, 1.27)), Sym("hide"))


# Library symbols -------------------------------------------------------

def library_symbol(lib, name):
    tree = parse(open(os.path.join(SYMBOL_DIR, lib + ".kicad_sym")).read())
    for sym in find(tree, "symbol"):
        if sym[1] == name:
            assert not find(sym, "extends"), name
            sym = [Sym("symbol"), lib + ":" + name] + sym[2:]
            return sym
    raise KeyError(name)


def sram_symbol():
    # 23LC512 in DIP-8, SOIC-8 or TSSOP-8 (datasheet DS20005155C, table 3-1)
    pins = [
        ("1", "~{CS}", "input", -10.16, 2.54, 0),
        ("6", "SCK", "input", -10.16, 0, 0),
        ("5", "SI/SIO0", "bidirectional", 10.16, 2.54, 180),
        ("2", "SO/SIO1", "bidirectional", 10.16, 0, 180),
        ("3", "SIO2", "bidirectional", 10.16, -2.54, 180),
        ("7", "~{HOLD}/SIO3", "bidirectional", 10.16, -5.08, 180),
        ("8", "VCC", "power_in", 0, 10.16, 270),
        ("4", "VSS", "power_in", 0, -10.16, 90),
    ]
    body = S("symbol", "23LC512_0_1",
             S("rectangle", S("start", -7.62, 7.62), S("end", 7.62, -7.62),
               S("stroke", S("width", 0.254), S("type", Sym("default"))),
               S("fill", S("type", Sym("background")))))
    pin_list = S("symbol", "23LC512_1_1")
    for number, name, kind, x, y, angle in pins:
        pin_list.append(S("pin", Sym(kind), Sym("line"), S("at", x, y, angle),
                          S("length", 2.54), S("name", name, font()),
                          S("number", number, font())))
    return S("symbol", "sqi_ram:23LC512", S("in_bom", Sym("yes")),
             S("on_board", Sym("yes")),
             S("property", "Reference", "U", S("at", -7.62, 8.89, 0),
               font(S("justify", Sym("left")))),
             S("property", "Value", "23LC512", S("at", 0, -8.89, 0),
               font(S("justify", Sym("left")))),
             S("property", "Footprint", "", S("at", 0, 0, 0), hidden_font()),
             S("property", "Datasheet",
               "https://ww1.microchip.com/downloads/en/DeviceDoc/"
               "20005155C.pdf", S("at", 0, 0, 0), hidden_font()),
             body, pin_list)


def pins_of(symbol):
    # number -> (x, y, angle, name, hidden) in symbol coordinates (y up)
    out = {}

    def walk(x):
        for y in x:
            if isinstance(y, list) and y and y[0] == "pin":
                at = find(y, "at")[0]
                number = find(y, "number")[0][1]
                name = find(y, "name")[0][1]
                out[number] = (float(at[1]), float(at[2]), int(float(at[3])),
                               name, Sym("hide") in y)
            elif isinstance(y, list):
                walk(y)
    walk(symbol)
    return out


# Design ----------------------------------------------------------------

def load_yaml(name):
    with open(os.path.join(HERE, "..", name)) as f:
        return yaml.safe_load(f)["pins"]


def connections():
    # (reference, pin number) -> net, for every part
    conn = {}

    seq = load_yaml("seq.yaml")
    names = {"MCLK": "MCLK", "RD_n": "~{RD}", "WR_n": "~{WR}", "SCK": "SCK",
             "CS_n": "~{CS}", "CPUCLK": "CPUCLK", "PEND": "PEND"}
    for signal, pin in seq.items():
        conn[("U1", str(pin))] = names.get(signal, signal)
    conn[("U1", "11")] = "GND"            # /OE of the registered outputs

    sio = load_yaml("sio.yaml")
    for signal, pin in sio.items():
        if signal.startswith("D"):
            net = "AD" + signal[1:]
        else:
            net = names.get(signal, signal)
        conn[("U2", str(pin))] = net

    # 74AC138: Y(K & 3) enables the address nibble at K (8-11)
    conn.update({("U3", "1"): "K0", ("U3", "2"): "K1", ("U3", "3"): "K2",
                 ("U3", "4"): "K2", ("U3", "5"): "GND", ("U3", "6"): "K3"})
    y_pins = ["15", "14", "13", "12"]
    enable = {}
    for nibble, k in enumerate(ADDRESS_K):
        net = "~{EN_A%d-%d}" % (15 - 4 * nibble, 12 - 4 * nibble)
        conn[("U3", y_pins[k & 3])] = net
        enable[nibble] = net

    # 74AC244s: nibble bit i to SIOi. U4: A15-12 (group 1), A11-8 (2);
    # U5: A7-4 (1), A3-0 (2)
    group_pins = {1: ("1", ["2", "4", "6", "8"], ["18", "16", "14", "12"]),
                  2: ("19", ["11", "13", "15", "17"], ["9", "7", "5", "3"])}
    for nibble in range(4):
        ref = "U4" if nibble < 2 else "U5"
        oe, a_pins, y_pins_244 = group_pins[1 + nibble % 2]
        conn[(ref, oe)] = enable[nibble]
        for i in range(4):
            conn[(ref, a_pins[i])] = "A%d" % (12 - 4 * nibble + i)
            conn[(ref, y_pins_244[i])] = "SIO%d" % i

    # 74AC574: shifts a nibble in on each rising SCK, Q drives P0 in reads
    conn.update({("U6", "1"): "~{RD}", ("U6", "11"): "SCK"})
    for i in range(8):
        conn[("U6", str(2 + i))] = "SIO%d" % i if i < 4 else "AD%d" % (i - 4)
        conn[("U6", str(19 - i))] = "AD%d" % i

    # 23LC512
    conn.update({("U7", "1"): "~{CS}", ("U7", "6"): "SCK",
                 ("U7", "5"): "SIO0", ("U7", "2"): "SIO1",
                 ("U7", "3"): "SIO2", ("U7", "7"): "SIO3",
                 ("U7", "8"): "VCC", ("U7", "4"): "GND"})

    # 32 MHz oscillator, DIP-8 can: pin 1 enable (high or open)
    conn.update({("X1", "1"): "VCC", ("X1", "4"): "GND",
                 ("X1", "5"): "MCLK", ("X1", "8"): "VCC"})

    # SIO pull-ups
    for i in range(4):
        conn[("R%d" % (i + 1), "1")] = "VCC"
        conn[("R%d" % (i + 1), "2")] = "SIO%d" % i

    # Supply pins of the logic chips
    for ref, gnd, vcc in [("U1", "10", "20"), ("U2", "10", "20"),
                          ("U3", "8", "16"), ("U4", "10", "20"),
                          ("U5", "10", "20"), ("U6", "10", "20")]:
        conn[(ref, gnd)] = "GND"
        conn[(ref, vcc)] = "VCC"

    # Decoupling, one per chip
    for i in range(7):
        conn[("C%d" % (i + 1), "1")] = "VCC"
        conn[("C%d" % (i + 1), "2")] = "GND"
    return conn


# Pins left unconnected on purpose: the sequencer's spare inputs (the
# GAL16V8 holds unused inputs with internal pull-ups or pin keepers) and the
# 74AC138's unused outputs
NO_CONNECT = {("U1", str(p)) for p in range(4, 10)} | \
    {("U3", p) for p in ("7", "9", "10", "11")}


PARTS = [
    # reference, lib, symbol, value, footprint, position (mm)
    ("U1", "Logic_Programmable", "GAL16V8", "GAL16V8 seq",
     "Package_DIP:DIP-20_W7.62mm_Socket", (60, 60)),
    ("U2", "Logic_Programmable", "GAL16V8", "GAL16V8 sio",
     "Package_DIP:DIP-20_W7.62mm_Socket", (60, 130)),
    ("U3", "74xx", "74HC138", "74AC138",
     "Package_DIP:DIP-16_W7.62mm", (140, 60)),
    ("U4", "74xx", "74HC244", "74AC244",
     "Package_DIP:DIP-20_W7.62mm", (140, 125)),
    ("U5", "74xx", "74HC244", "74AC244",
     "Package_DIP:DIP-20_W7.62mm", (220, 125)),
    ("U6", "74xx", "74LS574", "74AC574",
     "Package_DIP:DIP-20_W7.62mm", (300, 125)),
    ("U7", "sqi_ram", "23LC512", "23LC512",
     "Package_DIP:DIP-8_W7.62mm", (300, 55)),
    ("X1", "Oscillator", "CXO_DIP8", "32MHz",
     "Oscillator:Oscillator_DIP-8", (220, 55)),
] + [
    ("R%d" % (i + 1), "Device", "R", "10k",
     "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal",
     (340 + 10.16 * i, 50)) for i in range(4)
] + [
    ("C%d" % (i + 1), "Device", "C", "100n",
     "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
     (40 + 15.24 * i, 185)) for i in range(7)
]


def value_at(name, x, y, angle):
    # Value text of a power symbol, beyond its end
    if name == "PWR_FLAG":
        return x, y - 5.08, 0
    dx, dy = {0: (0, 1), 90: (1, 0), 180: (0, -1), 270: (-1, 0)}[angle]
    if name == "VCC":
        dx, dy = -dx, -dy
    reach = 5.08 if name == "GND" else 3.81
    return x + dx * reach, y + dy * reach, 0


def place_label(net, x, y, pin_angle, key):
    # Text leads away from the symbol: a pin pointing right (angle 0) has its
    # connection point on the left
    angle = {0: 180, 180: 0, 90: 270, 270: 90}[pin_angle]
    justify = {0: "left", 180: "right", 90: "left", 270: "right"}[angle]
    if net in ("VCC", "GND"):
        return None
    if net in GLOBAL:
        return S("global_label", net, S("shape", Sym("bidirectional")),
                 S("at", x, y, angle), S("fields_autoplaced"),
                 font(S("justify", Sym(justify))), S("uuid", uid(*key)),
                 S("property", "Intersheetrefs", "${INTERSHEET_REFS}",
                   S("at", x, y, 0), hidden_font()))
    return S("label", net, S("at", x, y, angle), S("fields_autoplaced"),
             font(S("justify", Sym(justify), Sym("bottom"))),
             S("uuid", uid(*key)))


def build():
    conn = connections()
    root = uid("root")
    libs = {}
    for ref, lib, name, value, fp, at in PARTS:
        key = lib + ":" + name
        if key not in libs:
            libs[key] = sram_symbol() if lib == "sqi_ram" else \
                library_symbol(lib, name)
    for name in ("VCC", "GND", "PWR_FLAG"):
        libs["power:" + name] = library_symbol("power", name)

    items = []
    power_count = [0]

    def power(name, x, y, key, angle=0):
        power_count[0] += 1
        ref = "#PWR%02d" % power_count[0] if name != "PWR_FLAG" else \
            "#FLG%02d" % power_count[0]
        sym = libs["power:" + name]
        pins = pins_of(sym)
        items.append(S(
            "symbol", S("lib_id", "power:" + name), S("at", x, y, angle),
            S("unit", 1), S("in_bom", Sym("yes")), S("on_board", Sym("yes")),
            S("dnp", Sym("no")), S("uuid", uid(*key)),
            S("property", "Reference", ref, S("at", x, y + 3.81, 0),
              hidden_font()),
            S("property", "Value", name, S("at", *value_at(name, x, y, angle)),
              font()),
            S("property", "Footprint", "", S("at", x, y, 0), hidden_font()),
            S("property", "Datasheet", "", S("at", x, y, 0), hidden_font()),
            *[S("pin", n, S("uuid", uid(*key, "pin", n))) for n in pins],
            S("instances", S("project", PROJECT,
                             S("path", "/" + root, S("reference", ref),
                               S("unit", 1))))))

    for ref, lib, name, value, fp, (x, y) in PARTS:
        sym = libs[lib + ":" + name]
        pins = pins_of(sym)
        props = {p[1]: p for p in find(sym, "property")}
        ref_at = find(props["Reference"], "at")[0]
        val_at = find(props["Value"], "at")[0]
        items.append(S(
            "symbol", S("lib_id", lib + ":" + name), S("at", x, y, 0),
            S("unit", 1), S("in_bom", Sym("yes")), S("on_board", Sym("yes")),
            S("dnp", Sym("no")), S("uuid", uid(ref)),
            S("property", "Reference", ref,
              S("at", x + float(ref_at[1]), y - float(ref_at[2]), 0),
              font()),
            S("property", "Value", value,
              S("at", x + float(val_at[1]), y - float(val_at[2]), 0),
              font()),
            S("property", "Footprint", fp, S("at", x, y, 0), hidden_font()),
            S("property", "Datasheet", "", S("at", x, y, 0), hidden_font()),
            *[S("pin", n, S("uuid", uid(ref, "pin", n))) for n in pins],
            S("instances", S("project", PROJECT,
                             S("path", "/" + root, S("reference", ref),
                               S("unit", 1))))))

        for number, (px, py, angle, pin_name, hidden) in sorted(pins.items()):
            sx, sy = x + px, y - py
            net = conn.get((ref, number))
            if net is None:
                assert (ref, number) in NO_CONNECT, (ref, number)
                if not hidden:
                    items.append(S("no_connect", S("at", sx, sy),
                                   S("uuid", uid(ref, number, "nc"))))
                continue
            if hidden:
                # Hidden power pins join the VCC and GND nets by name
                assert net == pin_name, (ref, number, net, pin_name)
                continue
            if net in ("VCC", "GND"):
                # Point the symbol away from the part: GND points down and
                # VCC up when not rotated (rotation is counterclockwise)
                away = {0: "left", 180: "right", 90: "down", 270: "up"}[angle]
                rotation = {"GND": {"down": 0, "up": 180, "left": 270,
                                    "right": 90},
                            "VCC": {"up": 0, "down": 180, "left": 90,
                                    "right": 270}}[net][away]
                power(net, sx, sy, (ref, number), rotation)
                continue
            items.append(place_label(net, sx, sy, angle, (ref, number)))

    # The supply comes from the rest of the design
    for net, x in (("VCC", 30), ("GND", 50)):
        power(net, x, 35, ("flag", net))
        power("PWR_FLAG", x + 7.62, 35, ("flag", net, "flag"))
        items.append(S("wire", S("pts", S("xy", x, 35), S("xy", x + 7.62, 35)),
                       S("stroke", S("width", 0), S("type", Sym("default"))),
                       S("uuid", uid("flag", net, "wire"))))

    notes = [
        "8052 to 23LC512 SQI SRAM (see ../README.md)",
        "U1 sequencer: program with seq.jed. U2 SIO driver: program with "
        "sio.jed.",
        "A0-A7 come from the 8052's address latch, A8-A15 from P2, AD0-AD7 "
        "are P0.",
        "CPUCLK drives the 8052's XTAL1 (XTAL2 open on CMOS parts): remove "
        "its crystal.",
        "Use 74AC or 74ACT logic, not HC: the address enable path is "
        "timing-critical.",
        "The first MOVX after power-up must write 88h to 9998h (EQIO).",
    ]
    for i, text in enumerate(notes):
        items.append(S("text", text, S("at", 30, 220 + 5.08 * i, 0),
                       font(S("justify", Sym("left"), Sym("bottom"))),
                       S("uuid", uid("note", i))))

    sch = S("kicad_sch", S("version", 20230121),
            S("generator", Sym("eeschema")), S("uuid", root),
            S("paper", "A3"),
            S("title_block", S("title", "8052 to 23LC512 SQI SRAM"),
              S("comment", 1, "Generated by make_schematic.py")),
            S("lib_symbols", *libs.values()),
            *items,
            S("sheet_instances", S("path", "/", S("page", "1"))))
    return sch


def main():
    out = os.path.join(HERE, PROJECT + ".kicad_sch")
    with open(out, "w") as f:
        f.write(dump(build()) + "\n")
    print("wrote", out)

    # Project library with the 23LC512, which the KiCad libraries lack
    sym = sram_symbol()
    sym[1] = "23LC512"
    with open(os.path.join(HERE, PROJECT + ".kicad_sym"), "w") as f:
        f.write(dump(S("kicad_symbol_lib", S("version", 20220914),
                       S("generator", Sym("make_schematic")), sym)) + "\n")
    with open(os.path.join(HERE, "sym-lib-table"), "w") as f:
        f.write(dump(S("sym_lib_table", S(
            "lib", S("name", PROJECT), S("type", "KiCad"),
            S("uri", "${KIPRJMOD}/" + PROJECT + ".kicad_sym"),
            S("options", ""), S("descr", "23LC512 serial SRAM")))) + "\n")


if __name__ == "__main__":
    main()
