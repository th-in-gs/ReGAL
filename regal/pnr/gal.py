import logging
import sys

from datetime import datetime

from regal.pnr.exception import FitError, PnrError
from regal.pnr.jedec import Jedec
from regal.pnr.sop import MAX_TERMS, fit_exact, literal, minimize, sop_and, \
    sop_not, sop_or

_logger = logging.getLogger("regal_pnr")
_logger.addHandler(logging.NullHandler())


def _get_param(cell, name):
    # Recent Yosys versions write integer parameters as binary strings
    value = cell["parameters"][name]
    if isinstance(value, str):
        value = int(value, 2)
    return value


class Cell:
    def __init__(self, gal, gal_mode, outpad, inputs, depth=8):
        self.gal = gal
        self.gal_mode = gal_mode
        self.outpad = outpad
        self.inputs = inputs
        self.depth = depth
        self.width = len(inputs) * 2

        self.fuses_and_array = [1] * self.width * self.depth
        self.fuses_ptd = [1] * depth
        self.fuse_xor = 0

        if self.gal_mode in ["registered", "complex"]:
            self.fuse_ac1 = 1
        else:
            self.fuse_ac1 = 0

        self.used = False
        self.tristate = False

    def _write_terms(self, terms, pins):
        if frozenset() in terms:
            # Constant 1: an empty product term cannot be expressed in the
            # array (a line with no fuse blown is the unused, always false
            # line), so implement it as an inverted constant 0
            self.invert()
            terms = []

        if len(terms) > self.get_useable_depth():
            raise FitError(
                "Pin {} needs {} product terms, more than the {} a macro "
                "cell holds".format(
                    self.outpad, len(terms), self.get_useable_depth()
                )
            )

        for i, term in enumerate(terms):
            self._write_row(i + int(self.has_oe()), term, pins)

    def _write_row(self, row, term, pins):
        row *= self.width
        for netname, polarity in sorted(term):
            _logger.info("Connecting input %s%s to macro cell %d",
                         "" if polarity else "~", netname, self.outpad)
            try:
                inpad = pins[netname]
            except KeyError:
                raise PnrError(
                    "No IO assigned for netname {}".format(netname))

            try:
                index_input = self.inputs.index(inpad)
            except ValueError:
                raise PnrError(
                    "Pad {} cannot be assigned as input".format(inpad))

            self.fuses_and_array[row + index_input * 2 +
                                 int(not polarity)] = 0

    def configure_oe(self, netlist, bit, pins):
        # The output enable of a macro cell is its first product term
        _logger.info("Configuring output enable of macro cell %s",
                     self.outpad)
        if not self.has_oe():
            raise PnrError("Pin {} cannot be tri-stated in {} mode".format(
                self.outpad, self.gal_mode))
        self.tristate = True

        if bit == "1":
            return
        if bit == "0":
            terms = []
        else:
            terms = self.gal.expand(netlist, bit, pins)
            if terms is None:
                raise FitError("Output enable of pin {} is too large to "
                               "flatten into product terms".format(
                                   self.outpad))
            terms = minimize(terms)
        if len(terms) > 1:
            raise FitError(
                "Output enable of pin {} needs {} product terms, but a "
                "macro cell has only one for it".format(
                    self.outpad, len(terms)))

        if not terms:
            # Every input and its complement: never enabled
            self.fuses_and_array[:self.width] = [0] * self.width
        else:
            self._write_row(0, terms[0], pins)

    def configure_and_array(self, netlist, sop, pins):
        _logger.info("Configuring AND-array for macro cell {}".format(self.outpad))

        label = [n for n, pin in pins.items() if pin == self.outpad][0]
        terms = self.gal.expand_sop(netlist, sop, pins,
                                    self.get_useable_depth(), label)

        fitted = self.gal.fit(terms, self.get_useable_depth())
        if fitted is not None:
            terms, inverted = fitted
            if inverted:
                _logger.info("Using complement of macro cell %s function",
                             self.outpad)
                self.invert()

        self._write_terms(terms, pins)

    def configure_buffer(self, netname, pins):
        # Yosys optimizes "assign out = in;" down to a plain wire, leaving no
        # GAL_SOP cell to map, so use a single product term with the input
        _logger.info("Configuring macro cell %s as a buffer of %s",
                     self.outpad, netname)
        self._write_terms(literal(netname), pins)

    def _get_driver(self, netlist, bit, pins):
        # Returns None when the bit comes straight from an assigned input
        driver = netlist.find_driver(bit)
        if driver is None and netlist.get_input_netname(bit, pins) is None:
            raise PnrError("Cannot find a driver for bit {}".format(bit))
        return driver

    def _follow(self, netlist, bit, pins):
        # Driver of a signal feeding this macro cell, or the name of the
        # signal if it is assigned to a pin (input or feedback)
        netname = netlist.get_netname(bit, pins)
        if netname in pins:
            return None, netname
        return self._get_driver(netlist, bit, pins), None

    def invert(self):
        _logger.info("Inverting output of macro cell %s", self.outpad)
        self.fuse_xor ^= 1

    def set_registered(self, clock, pins):
        _logger.info(
            "Configure macro cell %s in registered mode (clock: %s)",
            self.outpad, clock
        )
        if self.gal_mode != "registered":
            raise PnrError(
                "GAL_DFF can only be synthesized in registered mode"
                " (current GAL mode: {})".format(self.gal_mode)
            )

        sysclk = None
        for netname, pin in pins.items():
            if pin == 1:
                sysclk = netname

        if clock != sysclk:
            raise PnrError(
                "{} is not mapped to a clock input "
                "(currently mapped to {} signal)".format(clock, sysclk)
            )
        self.fuse_ac1 = 0

    def has_oe(self):
        return (self.gal_mode == "complex") or \
            (self.gal_mode == "registered" and self.fuse_ac1)

    def get_useable_depth(self):
        return self.depth - int(self.has_oe())

    def configure(self, netlist, bit, pins):
        _logger.info("Configuring macro cell %s", self.outpad)

        self.fuse_xor = 1

        if type(bit) is int:
            source = None
            driver = self._get_driver(netlist, bit, pins)

            if driver is not None and driver["type"] == "GAL_DFF":
                clock = netlist.get_netname(driver["connections"]["C"][0])
                self.set_registered(clock, pins)
                bit = driver["connections"]["D"][0]
                driver, source = self._follow(netlist, bit, pins)

            if driver is not None and driver["type"] == "GAL_TRI":
                self.configure_oe(netlist, driver["connections"]["OE"][0],
                                  pins)
                bit = driver["connections"]["A"][0]
                driver, source = self._follow(netlist, bit, pins)
                if driver is not None and driver["type"] == "GAL_DFF":
                    raise PnrError(
                        "Registered pin {} can only be enabled by pin "
                        "11".format(self.outpad))

            if driver is not None and driver["type"] == "GAL_XOR":
                self.invert()
                bit = driver["connections"]["A"][0]
                driver, source = self._follow(netlist, bit, pins)

            if driver is not None and driver["type"] == "GAL_SOP":
                self.configure_and_array(netlist, driver, pins)
            elif driver is not None and driver["type"] != "GAL_DFF":
                raise PnrError("Unknown cell type: {}".format(driver["type"]))
            else:
                # Copy of a single signal: an input, a register or another
                # macro cell
                if source is None:
                    source = netlist.get_input_netname(bit, pins) or \
                        netlist.get_netname(bit, pins)
                self.configure_buffer(source, pins)
        elif bit == "1":
            self.invert()
        elif bit != "0":
            raise PnrError("Cannot assign value {} to outpad {}".format(
                bit, self.outpad
            ))

        self.used = True

    def configure_as_input(self):
        _logger.info("Configuring macro cell %s as input", self.outpad)
        self.fuses_ptd[0] = 0
        self.used = True


class Gal:
    def __init__(self, mode, inpads, outpads):
        self.inpads = inpads
        self.outpads = outpads
        self.mode = mode

        self.fuses_signature = [0] * 64
        if mode == "registered":
            self.fuse_syn = 0
            self.fuse_ac0 = 1
        elif mode == "complex":
            self.fuse_syn = 1
            self.fuse_ac0 = 1
        elif mode == "simple":
            self.fuse_syn = 1
            self.fuse_ac0 = 0
        else:
            raise ValueError("Invalid GAL mode: {}".format(mode))

        self._expansions = {}
        self._fits = {}
        # Product terms needed by each macro cell function, after inlining
        # and minimization (None if too large), to explain fit failures
        self._sizes = {}

        self.cells = []
        for outpad in outpads:
            self.cells.append(Cell(self, mode, outpad, self.inpads))

        _logger.info("GAL%dV%d configured in %s mode",
                     len(inpads), len(outpads), mode)

    def get_cell(self, outpad):
        for cell in self.cells:
            if cell.outpad == outpad:
                return cell
        raise KeyError

    def fit(self, terms, depth):
        # Implementation of a SOP in at most depth terms, possibly minimized
        # or complemented (the output XOR can invert it): (terms, inverted)
        # or None
        if terms is None:
            return None
        if len(terms) <= depth:
            return terms, False
        key = (tuple(terms), depth)
        if key not in self._fits:
            self._fits[key] = self._fit(terms, depth)
        return self._fits[key]

    def _fit(self, terms, depth):
        for inverted in (False, True):
            fitted = minimize(terms, inverted)
            if len(fitted) <= depth:
                return fitted, inverted
        # The heuristic can miss covers that fit, look for one exactly
        for inverted in (False, True):
            fitted = fit_exact(terms, depth, inverted)
            if fitted is not None:
                return fitted, inverted
        return None

    def _sop_terms(self, sop):
        # Product terms of a GAL_SOP cell as lists of (bit, polarity)
        table = _get_param(sop, "TABLE")
        width = _get_param(sop, "WIDTH")
        depth = _get_param(sop, "DEPTH")
        inputs = [sop["connections"]["I{}".format(j)][0] for j in range(width)]

        terms = []
        for k in range(depth):
            term = []
            for j, bit in enumerate(inputs):
                if bit == "0":
                    continue
                i = (k * width + j) * 2
                if table >> (i + 1) & 1:
                    term.append((bit, True))
                if table >> i & 1:
                    term.append((bit, False))
            terms.append(term)
        return terms

    def expand(self, netlist, bit, pins):
        # Function of a signal as a SOP of assigned signals, with every
        # internal combinational signal it depends on inlined. None if that
        # is not possible (unassigned inputs) or too large.
        if bit in self._expansions:
            return self._expansions[bit]
        self._expansions[bit] = None

        netname = netlist.get_netname(bit, pins)
        driver = netlist.find_driver(bit)
        if netname in pins:
            result = literal(netname)
        elif driver is None or driver["type"] == "GAL_DFF":
            result = None
        elif driver["type"] == "GAL_XOR":
            result = sop_not(
                self.expand(netlist, driver["connections"]["A"][0], pins))
        elif driver["type"] == "GAL_SOP":
            result = minimize(self.expand_sop(netlist, driver, pins))
        else:
            result = None

        self._expansions[bit] = result
        return result

    def expand_sop(self, netlist, sop, pins, depth=None, label=None):
        # SOP of a GAL_SOP cell in terms of assigned signals, with all
        # internal signals inlined (None if impossible). With the depth of the
        # macro cell implementing it (named label), terms that do not fit are
        # moved to spare macro cells.
        terms = self._sop_terms(sop)

        internal = []
        for term in terms:
            for bit, _ in term:
                if netlist.get_netname(bit, pins) not in pins and \
                   bit not in internal:
                    internal.append(bit)

        def build(inlined):
            result = []
            for term in terms:
                product = [frozenset()]
                for bit, polarity in term:
                    if bit in inlined:
                        factor = inlined[bit] if polarity \
                            else sop_not(inlined[bit])
                    else:
                        factor = literal(netlist.get_netname(bit, pins),
                                         polarity)
                    product = sop_and(product, factor)
                result = sop_or(result, product)
            return result

        expansions = {bit: self.expand(netlist, bit, pins) for bit in internal}

        if depth is None:
            if None in expansions.values():
                return None
            return build(expansions)

        full = None if None in expansions.values() else build(expansions)
        if full is None:
            self._sizes[label] = None
            raise FitError("{} is too large to flatten into product "
                           "terms".format(label))
        if self.fit(full, depth) is not None:
            return full

        full = minimize(full)
        self._sizes[label] = len(full)
        return self._split(full, depth, label, pins)

    def _split(self, terms, depth, label, pins):
        # Move terms to spare macro cells until the rest, plus one term per
        # spare macro cell, fits in depth
        spares = self._spare_cells(pins)
        chunks = []
        start = 0
        while len(terms) - start + len(chunks) > depth:
            if len(chunks) == len(spares):
                raise FitError(
                    "{} needs {} product terms, more than the {} a macro "
                    "cell holds".format(label, len(terms), depth))
            size = spares[len(chunks)].get_useable_depth()
            chunks.append(terms[start:start + size])
            start += size

        result = terms[start:]
        for k, chunk in enumerate(chunks):
            netname = "{}_part{}".format(label, k)
            cell = self._take_spare(netname, pins)
            cell.fuse_xor = 1
            cell._write_terms(chunk, pins)
            cell.used = True
            result += literal(netname)
        return result

    def _spare_cells(self, pins):
        # Unused macro cells whose output feeds back into the AND-array, from
        # the end of the list, which is usually the last to be assigned by hand
        return [cell for cell in reversed(self.cells)
                if not cell.used and cell.outpad in self.inpads and
                cell.outpad not in pins.values()]

    def _take_spare(self, netname, pins):
        spares = self._spare_cells(pins)
        if not spares:
            raise FitError(
                "No spare macro cell left for internal signal {}".format(
                    netname)
            )
        cell = spares[0]
        _logger.warning(
            "Internal signal %s placed on spare pin %d "
            "(leave this pin unconnected)", netname, cell.outpad
        )
        pins[netname] = cell.outpad
        return cell

    def _fit_error(self, netname, pin, assigned, pins, error):
        # Explain why the macro cell of an output could not be configured
        size = self._sizes.get(netname, 0)
        depth = self.get_cell(pin).get_useable_depth()
        if size is None:
            return FitError(
                "Output {} (pin {}) is too large to flatten into product "
                "terms (more than {})".format(netname, pin, MAX_TERMS))

        if size > depth:
            left = len(self._spare_cells(pins))
            if left:
                why = "the {} spare macro cell{} left {} not enough to " \
                    "split it over".format(left, "s" if left > 1 else "",
                                           "are" if left > 1 else "is")
            else:
                why = "no spare macro cell is left to split it over"
            msg = "Output {} (pin {}) needs {} product terms after " \
                "minimization, more than the {} a macro cell holds, and " \
                "{}".format(netname, pin, size, depth, why)
        else:
            msg = "Output {} (pin {}): {}".format(netname, pin, error.msg)

        spares = sorted((p, n) for n, p in pins.items() if n not in assigned)
        if spares:
            msg += " (spare pins already used: {})".format(", ".join(
                "{} for {}".format(p, n) for p, n in spares))
        else:
            msg += " (every pin with feedback is assigned in the " \
                "configuration)"
        return FitError(msg)

    def pnr(self, netlist, pins):
        # Internal signals get added to pins as they are placed
        assigned = set(pins)
        pins = dict(pins)
        ios = list(netlist.get_ios(pins))

        for netname in netlist.get_used_inputs():
            if netname not in pins:
                raise PnrError("Input {} is used but not assigned to a "
                               "pin".format(netname))

        # Registers that are not outputs need a macro cell of their own:
        # reserve them first so that logic using them can treat them as pins
        registers = []
        for bit in netlist.get_register_bits():
            netname = netlist.get_netname(bit, pins)
            if netname not in pins:
                try:
                    registers.append((self._take_spare(netname, pins), bit))
                except FitError:
                    raise FitError(
                        "Register {} is not an output and no spare macro "
                        "cell is left for it".format(netname))

        for netname, pin, direction in ios:
            if direction == "output":
                cell = self.get_cell(pin)
                if cell.used:
                    raise PnrError("Cell {} is already used".format(pin))

                bit = netlist.get_bit(netname)
                try:
                    cell.configure(netlist, bit, pins)
                except FitError as error:
                    raise self._fit_error(netname, pin, assigned, pins, error)
            else:
                try:
                    cell = self.get_cell(pin)
                except KeyError:
                    pass
                else:
                    cell.configure_as_input()

        for cell, bit in registers:
            cell.configure(netlist, bit, pins)


class GalXXv8(Gal):
    def write_jedec(self, stream):
        offset = 0

        design_specs = """
    Generated by ReGAL
    Device: {}
""".format(type(self).__name__)

        jedec = Jedec(stream, design_specs)
        jedec.fuse_number(self.fuse_number)
        jedec.fuse_default(0)
        jedec.security_fuse(0)

        # AND-array
        for cell in self.cells:
            jedec.comment("Macro cell {} AND-Array".format(cell.outpad))

            for line_idx in range(0, cell.width * cell.depth, cell.width):
                line = cell.fuses_and_array[line_idx:line_idx + cell.width]
                if 0 in line or (cell.has_oe() and line_idx == 0):
                    offset = jedec.fuses(offset, line)
                else:
                    offset += cell.width

        # XOR
        for cell in self.cells:
            jedec.comment("Macro cell {} XOR".format(cell.outpad))
            offset = jedec.fuses(offset, [cell.fuse_xor])

        # Signature
        jedec.comment("Signature")
        offset = jedec.fuses(offset, self.fuses_signature)

        # AC1
        for cell in self.cells:
            jedec.comment("Macro cell {} AC1".format(cell.outpad))
            offset = jedec.fuses(offset, [cell.fuse_ac1])

        # PTD
        for cell in self.cells:
            jedec.comment("Macro cell {} PTD".format(cell.outpad))
            offset = jedec.fuses(offset, cell.fuses_ptd)

        # SYN / AC0
        jedec.comment("SYN")
        offset = jedec.fuses(offset, [self.fuse_syn])
        jedec.comment("AC0")
        offset = jedec.fuses(offset, [self.fuse_ac0])

        jedec.checksum()


class Gal16v8(GalXXv8):
    def __init__(self, mode):
        self.fuse_number = 2194

        inpads = []
        outpads = []
        if mode == "simple":
            inpads = [
                2,  1, 3, 19,
                4, 18, 5, 17,
                6, 14, 7, 13,
                8, 12, 9, 11
            ]
            outpads = [19, 18, 17, 16, 15, 14, 13, 12]
        elif mode == "registered":
            inpads = [
                2, 19, 3, 18,
                4, 17, 5, 16,
                6, 15, 7, 14,
                8, 13, 9, 12
            ]
            outpads = [19, 18, 17, 16, 15, 14, 13, 12]
        elif mode == "complex":
            inpads = [
                2,  1, 3, 18,
                4, 17, 5, 16,
                6, 15, 7, 14,
                8, 13, 9, 11
            ]
            outpads = [19, 18, 17, 16, 15, 14, 13, 12]

        GalXXv8.__init__(self, mode, inpads, outpads)


class Gal20v8(GalXXv8):
    def __init__(self, mode):
        self.fuse_number = 2706

        inpads = []
        outpads = []
        if mode == "simple":
            inpads = [
                 2,  1,  3, 23,
                 4, 22,  5, 21,
                 6, 20,  7, 17,
                 8, 16,  9, 15,
                10, 14, 11, 13
            ]
            outpads = [22, 21, 20, 19, 18, 17, 16, 15]

        GalXXv8.__init__(self, mode, inpads, outpads)
