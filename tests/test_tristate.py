import itertools
import logging
import os

import regal

from galsim import Gal16v8Sim


def test_tristate(tmpdir):
    netlist = str(tmpdir.join("netlist.json"))
    out = str(tmpdir.join("out.jed"))
    assert regal.synth(netlist, os.path.join("tests", "samples", "tri.v"))
    assert regal.pnr(netlist, os.path.join("tests", "samples",
                                           "device_tri.yaml"), out)

    sim = Gal16v8Sim(out)
    for a, b, e1, e2 in itertools.product([0, 1], repeat=4):
        y = sim.outputs({2: a, 3: b, 4: e1, 5: e2})[19]
        assert y == (a ^ b if e1 and not e2 else None)


def test_tristate_enable_too_wide(tmpdir, caplog):
    netlist = str(tmpdir.join("netlist.json"))
    assert regal.synth(netlist, os.path.join("tests", "samples",
                                             "tri_wide.v"))
    with caplog.at_level(logging.ERROR):
        assert not regal.pnr(netlist, os.path.join(
            "tests", "samples", "device_tri_wide.yaml"),
            str(tmpdir.join("out.jed")))
    assert "Output enable of pin 19 needs 2 product terms, but a macro " \
        "cell has only one for it" in caplog.text
