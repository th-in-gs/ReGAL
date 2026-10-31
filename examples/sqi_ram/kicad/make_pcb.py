# Lays out sqi_ram.kicad_pcb: places the footprints of the schematic's
# netlist, routes it with Freerouting and adds ground pours.
#
#   python make_pcb.py place     writes sqi_ram.kicad_pcb (unrouted) and
#                                sqi_ram.dsn
#   python make_pcb.py route     runs Freerouting (FREEROUTING_JAR, run with
#                                JAVA, Java 25 for Freerouting 2.5) on it
#   python make_pcb.py import    reads sqi_ram.ses into sqi_ram.kicad_pcb,
#                                adds ground pours and runs DRC
#   python make_pcb.py drc       runs DRC only
#
# Needs KiCad's pcbnew Python module (KiCad 7 or later).

import os
import re
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from check_schematic import netlist  # noqa: E402
from make_schematic import find, parse  # noqa: E402

FOOTPRINT_DIR = os.environ.get("KICAD_FOOTPRINT_DIR",
                               "/usr/share/kicad/footprints")
PCB = os.path.join(HERE, "sqi_ram.kicad_pcb")

WIDTH, HEIGHT = 95, 72          # board, mm

# Footprint origin (pin 1) of each part, in mm, and rotation in degrees.
# Top row: P0 side (74AC574, SIO GAL) and the sequencer with its
# oscillator. Bottom row: address buffers, decoder and RAM. SIO runs in
# the channel between the rows.
PLACEMENT = {
    "J1": (5.08, 13.97, 0),
    "U6": (17.78, 10.16, 0),
    "U2": (33.02, 10.16, 0),
    "U1": (55.88, 10.16, 0),
    "X1": (72.39, 19.05, 0),
    "U5": (17.78, 43.18, 0),
    "U4": (33.02, 43.18, 0),
    "U3": (48.26, 43.18, 0),
    "U7": (63.5, 43.18, 0),
    "R1": (76.2, 43.18, 0),
    "R2": (76.2, 48.26, 0),
    "R3": (76.2, 53.34, 0),
    "R4": (76.2, 58.42, 0),
}
# Decoupling capacitor for each chip, just above it next to its VCC pin
DECOUPLING = {"C1": "U1", "C2": "U2", "C3": "U3", "C4": "U4", "C5": "U5",
              "C6": "U6", "C7": "U7"}
HOLES = [(3.5, 3.5), (WIDTH - 3.5, 3.5), (3.5, HEIGHT - 3.5),
         (WIDTH - 3.5, HEIGHT - 3.5)]


def mm(x):
    return pcbnew.FromMM(x)


def point(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def design():
    tree = netlist()
    comps = {}
    for comp in find(find(tree, "components")[0], "comp"):
        comps[find(comp, "ref")[0][1]] = (
            find(comp, "value")[0][1], find(comp, "footprint")[0][1],
            find(comp, "tstamps")[0][1])
    nets = {}
    for net in find(find(tree, "nets")[0], "net"):
        name = find(net, "name")[0][1]
        nodes = [(find(n, "ref")[0][1], find(n, "pin")[0][1])
                 for n in find(net, "node")]
        nodes = [n for n in nodes if not n[0].startswith("#")]
        if not name.startswith("unconnected-") and nodes:
            nets[name] = nodes
    return comps, nets


def load_footprint(fpid):
    lib, name = fpid.split(":")
    fp = pcbnew.FootprintLoad(os.path.join(FOOTPRINT_DIR, lib + ".pretty"),
                              name)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def build_board():
    comps, nets = design()
    board = pcbnew.BOARD()

    settings = board.GetDesignSettings()
    settings.m_TrackMinWidth = mm(0.2)
    settings.m_ViasMinSize = mm(0.6)
    settings.m_MinThroughDrill = mm(0.3)
    settings.m_MinClearance = mm(0.2)
    settings.m_CopperEdgeClearance = mm(0.5)
    classes = settings.m_NetSettings
    default = classes.m_DefaultNetClass
    default.SetTrackWidth(mm(0.25))
    default.SetClearance(mm(0.2))
    default.SetViaDiameter(mm(0.7))
    default.SetViaDrill(mm(0.35))
    power = pcbnew.NETCLASS("Power")
    power.SetTrackWidth(mm(0.5))
    power.SetClearance(mm(0.2))
    power.SetViaDiameter(mm(0.8))
    power.SetViaDrill(mm(0.4))
    classes.m_NetClasses["Power"] = power

    netinfo = {}
    for name in nets:
        item = pcbnew.NETINFO_ITEM(board, name)
        board.Add(item)
        if name in ("VCC", "GND"):
            item.SetNetClass(power)
        netinfo[name] = item

    pad_net = {node: name for name, nodes in nets.items() for node in nodes}

    positions = dict(PLACEMENT)
    for cap, chip in DECOUPLING.items():
        # Above the chip, from its VCC pin (top right) leftwards
        x, y, _ = positions[chip]
        right = 7.62 if chip != "U7" else 7.62
        positions[cap] = (x + right - 5.0, y - 4.445, 0)
    positions["C3"] = (positions["U3"][0] + 2.62, positions["U3"][1] - 4.445,
                       0)

    for ref, (value, fpid, tstamp) in sorted(comps.items()):
        fp = load_footprint(fpid)
        fp.SetReference(ref)
        fp.SetValue(value)
        # Link to the schematic symbol, for Update PCB from Schematic
        fp.SetPath(pcbnew.KIID_PATH("/" + tstamp))
        x, y, angle = positions[ref]
        fp.SetPosition(point(x, y))
        fp.SetOrientationDegrees(angle)
        for pad in fp.Pads():
            net = pad_net.get((ref, pad.GetNumber()))
            if net is not None:
                pad.SetNet(netinfo[net])
                if ref == "J1" and net == "GND":
                    # Routing can leave room for only one thermal spoke
                    # between header pins: connect them to the pours solidly
                    pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        board.Add(fp)

    for i, (x, y) in enumerate(HOLES):
        fp = load_footprint("MountingHole:MountingHole_3.2mm_M3")
        fp.SetReference("H%d" % (i + 1))
        fp.SetPosition(point(x, y))
        board.Add(fp)

    corners = [(0, 0), (WIDTH, 0), (WIDTH, HEIGHT), (0, HEIGHT)]
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(point(x0, y0))
        seg.SetEnd(point(x1, y1))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    text = pcbnew.PCB_TEXT(board)
    text.SetText("8052 to 23LC512 SQI SRAM")
    text.SetPosition(point(WIDTH / 2 + 10, HEIGHT - 3))
    text.SetLayer(pcbnew.F_SilkS)
    text.SetTextSize(pcbnew.VECTOR2I(mm(1.5), mm(1.5)))
    board.Add(text)
    return board


def import_session(board, path):
    # Tracks and vias from a Specctra session file written by Freerouting
    ses = parse(open(path).read())
    routes = find(ses, "routes")[0]
    res = find(routes, "resolution")[0]
    scale = {"um": 1e-3, "mm": 1.0, "mil": 0.0254, "inch": 25.4}[res[1]] / \
        float(res[2])
    layers = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    nets = {n.GetNetname(): n for n in board.GetNetInfo().NetsByName()
            .values()}
    count = [0, 0]
    for net in find(find(routes, "network_out")[0], "net"):
        item = nets[net[1]]
        for wire in find(net, "wire"):
            path_ = find(wire, "path")[0]
            layer, width = layers[path_[1]], float(path_[2]) * scale
            xy = [float(v) * scale for v in path_[3:]]
            pts = [(xy[i], -xy[i + 1]) for i in range(0, len(xy), 2)]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(point(x0, y0))
                track.SetEnd(point(x1, y1))
                track.SetWidth(mm(width))
                track.SetLayer(layer)
                track.SetNet(item)
                board.Add(track)
                count[0] += 1
        for via in find(net, "via"):
            # Padstack names are like Via[0-1]_700:350_um
            size, drill = via[1].split("_")[1].split(":")
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(point(float(via[2]) * scale,
                                -float(via[3]) * scale))
            v.SetWidth(mm(float(size) / 1000))
            v.SetDrill(mm(float(drill) / 1000))
            v.SetNet(item)
            board.Add(v)
            count[1] += 1
    return count


def add_ground_pours(board):
    gnd = board.FindNet("GND")
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(gnd)
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in [(0.5, 0.5), (WIDTH - 0.5, 0.5),
                     (WIDTH - 0.5, HEIGHT - 0.5), (0.5, HEIGHT - 0.5)]:
            outline.Append(mm(x), mm(y))
        zone.SetMinThickness(mm(0.25))
        zone.SetLocalClearance(mm(0.3))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        zone.SetThermalReliefGap(mm(0.4))
        zone.SetThermalReliefSpokeWidth(mm(0.4))
        board.Add(zone)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def power_class_in_dsn(path):
    # KiCad 7 exports every net in the default class: move the supplies to
    # the Power class, for wider tracks
    text = open(path).read()
    default = text.index("(class kicad_default")
    end = text.index("(circuit", default)
    names = text[default:end].split()
    assert "VCC" in names and "GND" in names
    listed = " ".join(n for n in names if n not in ("VCC", "GND"))
    text = text[:default] + listed + "\n      " + text[end:]
    text = text.replace("(class Power", "(class Power GND VCC", 1)
    open(path, "w").write(text)


def power_class_in_project():
    # The project file holds net classes: tracks of the supplies are 0.5 mm
    import json
    path = os.path.join(HERE, "sqi_ram.kicad_pro")
    project = json.load(open(path))
    net = project.setdefault("net_settings", {})
    classes = net.setdefault("classes", [])
    default = next(c for c in classes if c["name"] == "Default")
    default.update({"track_width": 0.25, "clearance": 0.2,
                    "via_diameter": 0.7, "via_drill": 0.35})
    power = dict(default, name="Power", track_width=0.5, via_diameter=0.8,
                 via_drill=0.4)
    net["classes"] = [c for c in classes if c["name"] != "Power"] + [power]
    net["netclass_patterns"] = [{"netclass": "Power", "pattern": "VCC"},
                                {"netclass": "Power", "pattern": "GND"}]
    json.dump(project, open(path, "w"), indent=2)


def drc(board, path):
    # KiCad's DRC report: (violations, unconnected items)
    pcbnew.WriteDRCReport(board, path, pcbnew.EDA_UNITS_MILLIMETRES, True)
    text = open(path).read()
    found = [int(n) for n in re.findall(
        r"\*\* Found (\d+) (?:DRC violations|unconnected pads)", text)]
    return found


def main():
    if sys.argv[1] == "place":
        board = build_board()
        board.SetFileName(PCB)
        pcbnew.SaveBoard(PCB, board)
        dsn = os.path.join(HERE, "sqi_ram.dsn")
        assert pcbnew.ExportSpecctraDSN(board, dsn)
        power_class_in_dsn(dsn)
        power_class_in_project()
        print("wrote", PCB, "and", dsn)
    elif sys.argv[1] == "route":
        subprocess.run([
            os.environ.get("JAVA", "java"), "-jar",
            os.environ["FREEROUTING_JAR"],
            "-de", os.path.join(HERE, "sqi_ram.dsn"),
            "-do", os.path.join(HERE, "sqi_ram.ses"), "-mp", "100",
            "--gui.enabled=false",
            "--usage_and_diagnostic_data.disable_analytics=true",
            # Keep every track at its net class width
            "--router.automatic_neckdown=false"], check=True)
    elif sys.argv[1] == "import":
        board = pcbnew.LoadBoard(PCB)
        # Replace any earlier import
        for item in list(board.GetTracks()) + list(board.Zones()):
            board.Delete(item)
        tracks, vias = import_session(
            board, os.path.join(HERE, "sqi_ram.ses"))
        add_ground_pours(board)
        # Pads where the tracks leave room for only one thermal spoke
        # connect to the pour solidly instead
        report = os.path.join(HERE, "sqi_ram-drc.rpt")
        drc(board, report)
        starved = re.findall(r"starved_thermal\].*?\n(?:.*\n)*?.*PTH pad "
                             r"(\S+) \[GND\] of (\S+)", open(report).read())
        for number, ref in sorted(set(starved)):
            for pad in board.FindFootprintByReference(ref).Pads():
                if pad.GetNumber() == number:
                    pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
            print("solid zone connection for {} pad {}".format(ref, number))
        if starved:
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(PCB, board)
        print("imported {} track segments and {} vias into {}".format(
            tracks, vias, PCB))
    if sys.argv[1] in ("import", "drc"):
        board = pcbnew.LoadBoard(PCB)
        report = os.path.join(HERE, "sqi_ram-drc.rpt")
        print("DRC: violations, unconnected:", drc(board, report),
              "(see {})".format(report))


if __name__ == "__main__":
    main()
