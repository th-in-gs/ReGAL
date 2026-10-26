import logging
import os

import pytest

import regal


_samples = [
    ("cpu_full.v", "device_cpu_full.yaml",
     "Output RR (pin 19) needs 12 product terms after minimization, more "
     "than the 8 a macro cell holds, and no spare macro cell is left to "
     "split it over (every pin with feedback is assigned in the "
     "configuration)"),
    ("parity3.v", "device_parity3.yaml",
     "Output O1 (pin 18) needs 16 product terms after minimization, more "
     "than the 8 a macro cell holds, and the 1 spare macro cell left is "
     "not enough to split it over (spare pins already used: "
     "12 for O0_part0, 13 for O0_part1)"),
    ("hidden_full.v", "device_hidden_full.yaml",
     "Register Clk2 is not an output and no spare macro cell is left for it"),
    ("parity8.v", "device_parity8.yaml",
     "Output O (pin 19) is too large to flatten into product terms "
     "(more than 64)"),
    ("parity.v", "device_missing.yaml",
     "Input I4 is used but not assigned to a pin"),
]


@pytest.mark.parametrize("rtl,cfg,message", _samples)
def test_fit_error(tmpdir, caplog, rtl, cfg, message):
    netlist = tmpdir.join("netlist.json")
    assert regal.synth(str(netlist), os.path.join("tests", "samples", rtl))

    with caplog.at_level(logging.ERROR, logger="regal_pnr"):
        assert not regal.pnr(str(netlist),
                             os.path.join("tests", "samples", cfg),
                             str(tmpdir.join("out.jed")))
    assert message in caplog.text
