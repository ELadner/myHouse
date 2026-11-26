import math

import pytest

IN, FT = 0.0254, 0.3048


def test_birdsmouth_of_a_2x8_at_6_in_12_on_a_2x4_wall():
    from myhouse import _tetto_calc as calc
    cut = calc.birdsmouth(7.25 * IN, 6 / 12, plate=3.5 * IN)
    assert cut["seat"] == pytest.approx(3.5 * IN) and not cut["limited"]
    assert cut["heel"] == pytest.approx(1.75 * IN)
    assert cut["notch"] == pytest.approx(3.5 * IN * math.sin(math.atan2(6, 12)))
    assert cut["plumb"] == pytest.approx(7.25 * IN / math.cos(math.atan2(6, 12)))
    assert cut["hap"] == pytest.approx(cut["plumb"] - 1.75 * IN)            # about 6 3/8"
    assert calc.depth_of(cut["plumb"], 6 / 12) == pytest.approx(7.25 * IN)


def test_birdsmouth_seat_stops_at_a_quarter_of_the_depth():
    from myhouse import _tetto_calc as calc
    cut = calc.birdsmouth(5.5 * IN, 1.0, plate=3.5 * IN)                    # a 2x6 at 12/12
    assert cut["limited"] and cut["notch"] == pytest.approx(5.5 * IN / 4)
    assert cut["seat"] == pytest.approx(5.5 * IN / 4 * math.sqrt(2))
    assert cut["heel"] == pytest.approx(cut["seat"])
    wide = calc.birdsmouth(7.25 * IN, 6 / 12, plate=5.5 * IN)               # a 2x8 on a 2x6 wall
    assert wide["limited"] and wide["seat"] < 5.5 * IN
    assert wide["notch"] == pytest.approx(7.25 * IN / 4)


def test_birdsmouth_off_a_wall_and_on_a_flat_roof():
    from myhouse import _tetto_calc as calc
    none = calc.birdsmouth(7.25 * IN, 6 / 12)                               # no wall, no seat asked for
    assert none["seat"] == 0 and none["heel"] == 0 and none["hap"] == pytest.approx(none["plumb"])
    asked = calc.birdsmouth(7.25 * IN, 6 / 12, seat=2 * IN)
    assert asked["seat"] == pytest.approx(2 * IN) and asked["heel"] == pytest.approx(1 * IN)
    flat = calc.birdsmouth(7.25 * IN, 0.0, plate=3.5 * IN)
    assert flat["seat"] == pytest.approx(3.5 * IN) and flat["heel"] == 0 and not flat["limited"]
    assert flat["hap"] == pytest.approx(7.25 * IN) and flat["notch"] == 0
