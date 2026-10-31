# Checks sqi_ram.kicad_sch with KiCad itself: exports its netlist with
# kicad-cli, then checks that
#  - every pin is on the net make_schematic.py meant, and unused pins are
#    alone,
#  - every part has a footprint whose pads match its pins,
#  - following the netlist alone, the address buffers put each address
#    nibble on SIO0-3 in bit order at the K where the sequencer expects it
#    (encoding.py), the 74AC574 shifts SIO into P0 as bench.py models it,
#    and the RAM's pins are where the 23LC512 datasheet puts them.

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from encoding import ADDRESS_K  # noqa: E402
from make_schematic import NO_CONNECT, connections, find, parse  # noqa: E402,E501

FOOTPRINT_DIR = os.environ.get("KICAD_FOOTPRINT_DIR",
                               "/usr/share/kicad/footprints")


def netlist():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "sqi_ram.net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out,
                        os.path.join(HERE, "sqi_ram.kicad_sch")],
                       check=True, capture_output=True)
        return parse(open(out).read())


def main():
    tree = netlist()
    pin_net = {}
    for net in find(find(tree, "nets")[0], "net"):
        name = find(net, "name")[0][1].lstrip("/")
        for node in find(net, "node"):
            pin_net[(find(node, "ref")[0][1], find(node, "pin")[0][1])] = name

    errors = []
    expected = connections()
    for key, net in sorted(expected.items()):
        if pin_net.get(key) != net:
            errors.append("{} pin {}: {} instead of {}".format(
                key[0], key[1], pin_net.get(key), net))
    for key, net in sorted(pin_net.items()):
        if key in expected or key[0].startswith("#"):
            continue
        if key not in NO_CONNECT:
            errors.append("{} pin {} is not connected as intended ({})"
                          .format(*key, net))
        elif not net.startswith("unconnected-"):
            errors.append("{} pin {} unexpectedly on {}".format(*key, net))

    # Footprints
    for comp in find(find(tree, "components")[0], "comp"):
        ref = find(comp, "ref")[0][1]
        fp = find(comp, "footprint")
        if not fp:
            errors.append("{} has no footprint".format(ref))
            continue
        lib, name = fp[0][1].split(":")
        path = os.path.join(FOOTPRINT_DIR, lib + ".pretty",
                            name + ".kicad_mod")
        pads = set(re.findall(r'\(pad "(\d+)"', open(path).read()))
        pins = {p for r, p in pin_net if r == ref}
        if pins - pads:
            errors.append("{}: pins {} have no pad in {}".format(
                ref, sorted(pins - pads), name))

    # Address nibbles, from the netlist only
    net_pins = {}
    for key, net in pin_net.items():
        net_pins.setdefault(net, set()).add(key)
    decoder_in = {"A0": "1", "A1": "2", "A2": "3", "~E0": "4", "~E1": "5",
                  "E2": "6"}
    y_pin = ["15", "14", "13", "12", "11", "10", "9", "7"]
    groups = [("1", ["2", "4", "6", "8"], ["18", "16", "14", "12"]),
              ("19", ["11", "13", "15", "17"], ["9", "7", "5", "3"])]
    for nibble, k in enumerate(ADDRESS_K):
        level = {"K%d" % i: (k >> i) & 1 for i in range(4)}
        level["GND"] = 0
        v = {name: level[pin_net[("U3", pin)]]
             for name, pin in decoder_in.items()}
        assert v["E2"] and not v["~E0"] and not v["~E1"], k
        select = v["A0"] | v["A1"] << 1 | v["A2"] << 2
        enable = pin_net[("U3", y_pin[select])]
        enabled = [(ref, g) for ref in ("U4", "U5") for g in groups
                   if pin_net[(ref, g[0])] == enable]
        if len(enabled) != 1:
            errors.append("K {} enables {} buffer halves".format(
                k, len(enabled)))
            continue
        ref, (_, a_pins, y_pins) = enabled[0]
        for i in range(4):
            source = pin_net[(ref, a_pins[i])]
            target = pin_net[(ref, y_pins[i])]
            want = "A%d" % (12 - 4 * nibble + i)
            if (source, target) != (want, "SIO%d" % i):
                errors.append("K {}: {} drives {}, expected {} on SIO{}"
                              .format(k, source, target, want, i))

    # 74AC574: D0-3 from SIO0-3, D4-7 from Q0-3, Q0-7 on AD0-7, clocked by
    # SCK and enabled by /RD
    for i in range(8):
        d = pin_net[("U6", str(2 + i))]
        q = pin_net[("U6", str(19 - i))]
        if q != "AD%d" % i:
            errors.append("U6 Q{} on {}".format(i, q))
        source = "SIO%d" % i if i < 4 else pin_net[("U6", str(19 - i + 4))]
        if d != source:
            errors.append("U6 D{} on {}, expected {}".format(i, d, source))
    if (pin_net[("U6", "11")], pin_net[("U6", "1")]) != ("SCK", "~{RD}"):
        errors.append("U6 clock or enable miswired")

    # 23LC512 pinout (DS20005155C, table 3-1)
    ram = {"1": "~{CS}", "2": "SIO1", "3": "SIO2", "4": "GND", "5": "SIO0",
           "6": "SCK", "7": "SIO3", "8": "VCC"}
    for pin, net in ram.items():
        if pin_net.get(("U7", pin)) != net:
            errors.append("U7 pin {} on {}".format(pin, pin_net.get(
                ("U7", pin))))

    nets = {n for n in net_pins if not n.startswith("unconnected-")}
    print("{} parts, {} nets, {} unconnected pins".format(
        len(find(find(tree, "components")[0], "comp")), len(nets),
        len(net_pins) - len(nets)))
    for e in errors:
        print("ERROR", e)
    print("OK" if not errors else "{} errors".format(len(errors)))
    return not errors


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
