# SPDX-License-Identifier: GPL-3.0-or-later
"""How a rafter sits on a wall: the bird's mouth (shared code, not a feature).

    cut = birdsmouth(depth, slope, plate=wall_width)     # on a wall
    cut = birdsmouth(depth, slope, seat=asked_for)       # on anything else

depth is the rafter measured square to its slope, slope the rise over the run
of the roof plane at the eaves. All lengths in metres. What comes back:

    seat    the level cut that lies on the plate
    heel    the plumb cut against the outer face of the wall (seat x slope)
    notch   how deep the cut goes into the rafter, square to its edge
    plumb   the rafter measured straight up and down (depth / cos)
    hap     height above plate: from the outer top corner of the plate up to
            the top of the rafter (plumb - heel)
    limited True when the seat had to be shorter than asked for

On a wall the seat is as long as the plate is wide, unless that would notch
the rafter deeper than NOTCH of its depth: then it is as long as that allows.
The roof stands at plate height + hap, measured at the outer face of the wall.
No Qt, no scene: plain numbers.
"""
from __future__ import annotations

import math

NOTCH = 0.25          # a notch at the bearing end: at most this much of the depth
FLAT = 1e-9           # a slope below this is a flat roof: nothing to cut


def plumb(depth: float, slope: float) -> float:
    """The rafter measured straight up and down."""
    return depth * math.hypot(1.0, slope)


def depth_of(plumb_height: float, slope: float) -> float:
    """The other way round: the depth of a rafter this high when plumb."""
    return plumb_height / math.hypot(1.0, slope)


def seat_limit(depth: float, slope: float) -> float:
    """The longest seat that keeps the notch within NOTCH of the depth."""
    if slope < FLAT:
        return math.inf
    return NOTCH * depth * math.hypot(1.0, slope) / slope


def birdsmouth(depth: float, slope: float, plate=None, seat=None) -> dict:
    depth, slope = float(depth), abs(float(slope))
    want = max(0.0, float(plate if plate is not None else (seat or 0.0)))
    cut = min(want, seat_limit(depth, slope))
    if slope < FLAT:
        slope = 0.0
    heel = cut * slope
    high = plumb(depth, slope)
    return {"seat": cut, "heel": heel,
            "notch": heel / math.hypot(1.0, slope),
            "plumb": high, "hap": high - heel,
            "limited": cut < want - 1e-9}
