import logging
import json

from regal.pnr.exception import PnrError

_logger = logging.getLogger("regal_pnr")
_logger.addHandler(logging.NullHandler())


class Netlist:
    def __init__(self, infile, top):
        with open(infile, "r") as f:
            self.netlist = json.load(f)
        self.top = self.netlist["modules"][top]

    def get_bits(self, netname):
        return self.top["netnames"][netname]["bits"]

    def get_bit(self, netname):
        bits = self.get_bits(netname)
        if len(bits) != 1:
            raise PnrError("Wire {} must be exactly 1 bit (is {})".
                           format(netname, len(bits)))
        return bits[0]

    def find_driver(self, bit):
        for cell_name, cell in self.top["cells"].items():
            for connection_name, bits in cell["connections"].items():
                if bit in bits and \
                   cell["port_directions"][connection_name] == "output":
                       _logger.debug(
                            "Found driver for bit %d: %s",
                            bit, cell_name
                        )
                       return cell
        return None

    def get_driver(self, bit):
        driver = self.find_driver(bit)
        if driver is None:
            raise PnrError("Cannot find a driver for bit {}".format(bit))
        return driver

    def get_input_netname(self, bit, pins):
        # Name of the assigned input port carrying this bit, if any. Used when
        # a bit is wired straight to an input without any cell in between
        # (e.g. "assign out = in;"), in which case the input port may share
        # the bit with other netnames.
        for name, port in self.top["ports"].items():
            if port["direction"] == "input" and name in pins and \
               port["bits"] == [bit]:
                return name
        return None

    def get_netname(self, bit, prefer=()):
        # A bit can carry several netnames: return one from prefer if possible
        names = [name for name, netname in self.top["netnames"].items()
                 if bit in netname["bits"]]
        if not names:
            raise PnrError("Cannot find netname for bit {}".format(bit))
        for name in names:
            if name in prefer:
                return name
        return names[0]

    def get_ios(self, pins):
        for netname, pin in pins.items():
            try:
                port = self.top["ports"][netname]
            except KeyError:
                _logger.warning("Port {} not assigned. Ignored".format(netname))
                continue

            yield netname, pin, port["direction"]
