import io

from regal.pnr.jedec import Jedec


def test_transmission_checksum():
    # JESD3: the 16-bit sum of every character from STX to ETX included,
    # written as four hex digits after ETX
    stream = io.StringIO()
    jedec = Jedec(stream, "test")
    jedec.fuse_number(16)
    jedec.fuse_default(0)
    jedec.fuses(0, [1, 0, 1, 1])
    jedec.checksum()
    text = stream.getvalue()
    start, end = text.index("\x02"), text.index("\x03")
    expected = sum(ord(c) for c in text[start:end + 1]) & 0xFFFF
    assert text[end + 1:] == "{:04X}".format(expected)
