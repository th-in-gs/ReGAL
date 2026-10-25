import os
import pytest
import json
import yaml

import regal

from galsim import assert_equivalent


def _check(tmpdir, rtl, cfg, jedec):
    # The fuse map must behave like the reference one: comparing them byte
    # for byte would tie the tests to one Yosys version
    netlist = tmpdir.join("netlist.json")
    assert regal.synth(str(netlist), os.path.join("tests", "samples", rtl))

    out = tmpdir.join("out.jed")
    cfg = os.path.join("tests", "samples", cfg)
    assert regal.pnr(str(netlist), cfg, str(out))

    with open(cfg, "r") as f:
        pins = yaml.safe_load(f)["pins"]
    with open(str(netlist), "r") as f:
        ports = json.load(f)["modules"]["top"]["ports"]
    assert_equivalent(os.path.join("tests", "samples", jedec), str(out),
                      pins, ports)


_samples_simple = [
    ("and.v", "and.jed"),
    ("nand.v", "nand.jed"),
    ("not.v", "not.jed"),
    ("or.v", "or.jed"),
    ("xor.v", "xor.jed"),
    ("v1.v", "v1.jed"),
    ("v0.v", "v0.jed"),
    ("fb.v", "fb.jed"),
    ("buf.v", "buf.jed"),
]

_samples_registered = [
    ("clk.v", "clk.jed"),
    ("clk_mixed.v", "clk_mixed.jed"),
    ("ff.v", "ff.jed"),
]

_samples_complex = [
    ("and.v", "andc.jed"),
    ("nand.v", "nandc.jed"),
    ("not.v", "notc.jed"),
    ("or.v", "orc.jed"),
    ("xor.v", "xorc.jed"),
    ("v1.v", "v1c.jed"),
    ("v0.v", "v0c.jed"),
    ("buf.v", "bufc.jed"),
]


@pytest.mark.parametrize("rtl,jedec", _samples_simple)
def test_synth_simple(tmpdir, rtl, jedec):
    _check(tmpdir, rtl, "device.yaml", jedec)


@pytest.mark.parametrize("rtl,jedec", _samples_registered)
def test_synth_registered(tmpdir, rtl, jedec):
    _check(tmpdir, rtl, "device_reg.yaml", jedec)


@pytest.mark.parametrize("rtl,jedec", _samples_complex)
def test_synth_complex(tmpdir, rtl, jedec):
    _check(tmpdir, rtl, "device_complex.yaml", jedec)


# Designs that need internal signals placed on spare macro cells
_samples_spare = [
    ("parity.v", "device_spare.yaml", "parity.jed"),
    ("hidden.v", "device_hidden.yaml", "hidden.jed"),
    ("cpu.v", "device_cpu.yaml", "cpu.jed"),
]


@pytest.mark.parametrize("rtl,cfg,jedec", _samples_spare)
def test_synth_spare(tmpdir, rtl, cfg, jedec):
    _check(tmpdir, rtl, cfg, jedec)
