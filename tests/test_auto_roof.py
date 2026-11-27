import math

import pytest

L_SHAPE = [(0., 0.), (8., 0.), (8., 4.), (4., 4.), (4., 7.), (0., 7.)]


def test_solver_hip_roof_on_a_rectangle():
    from myhouse import _tetto_auto
    pts, lines, hs = _tetto_auto.solve([(0., 0.), (8., 0.), (8., 4.), (0., 4.)], (), 0.5)
    assert len(pts) == 4 and len(lines) == 5                 # four hips and the ridge
    assert max(h[2] for h in hs) == pytest.approx(1.0)        # half the 4 m span, at 1 in 2


def test_solver_gable_and_inside_corner():
    from myhouse import _tetto_auto
    pts, lines, hs = _tetto_auto.solve([(0., 0.), (8., 0.), (8., 4.), (0., 4.)], {1, 3}, 0.5)
    assert len(pts) == 6 and len(lines) == 1                  # the ridge runs gable to gable
    pts, lines, hs = _tetto_auto.solve(L_SHAPE, (), 1.0)       # a valley at the inside corner
    assert any(a == pytest.approx((4., 4.)) or b == pytest.approx((4., 4.)) for a, b in lines)
    with pytest.raises(_tetto_auto.RoofError):
        _tetto_auto.solve(L_SHAPE, set(range(6)), 1.0)         # nothing slopes


def test_solver_gable_ends_that_share_a_corner():
    from myhouse import _tetto_auto
    square = [(0., 0.), (6., 0.), (6., 6.), (0., 6.)]
    pts, lines, hs = _tetto_auto.solve(square, {0, 1}, 1.0)   # a cross gable
    assert max(h[2] for h in hs) == pytest.approx(3.0)        # not a peak at the shared corner
    assert {(round(x, 6), round(y, 6)) for x, y in pts} == {(0., 0.), (3., 0.), (6., 0.), (6., 3.), (6., 6.), (0., 6.)}
    got = {frozenset(((round(a[0], 6), round(a[1], 6)), (round(b[0], 6), round(b[1], 6)))) for a, b in lines}
    assert got == {frozenset((p, (3., 3.))) for p in ((3., 0.), (6., 3.), (6., 0.), (0., 6.))}   # two ridges, valley, hip
    z = {(round(x, 6), round(y, 6)): h for x, y, h in hs}
    assert z[(3., 0.)] == pytest.approx(3.) and z[(6., 3.)] == pytest.approx(3.) and z[(6., 0.)] == pytest.approx(0.)
    for o in (square[::-1], [(x + 10.15, y * 1.5 - 3.3) for x, y in square]):   # either direction, any place
        for g in ({0, 1}, {1, 2}, {3, 0}, {0, 1, 2}):
            _tetto_auto.solve(o, g, 0.5)
    pts, lines, hs = _tetto_auto.solve(square, {0, 1, 2}, 1.0)  # one slope left: a shed roof
    assert lines == [] and max(h[2] for h in hs) == pytest.approx(6.0)


def test_pitch_text_and_parse(myhouse):
    from myhouse import tetto
    assert tetto.parse_pitch("30°") == pytest.approx(30.)
    assert tetto.parse_pitch("6/12") == pytest.approx(math.degrees(math.atan2(6, 12)))
    assert tetto.parse_pitch("100%") == pytest.approx(45.)
    assert tetto.parse_pitch("nonsense") is None and tetto.parse_pitch("89°") is None and tetto.parse_pitch("1/0") is None
    assert tetto.parse_pitch(tetto.pitch_text(22.5)) == pytest.approx(22.5)


def test_footprint_is_the_outer_face_of_the_walls(viewport):
    from myhouse import muri, solaio
    scene = viewport.scene
    muri.build_walls(scene, [(0., 0.), (6., 0.), (6., 4.), (0., 4.)], True, 0.30, 2.7, 0.0, "W", align="center")
    poly = solaio.find_footprint(scene, 3., 2.)
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    assert (min(xs), max(xs), min(ys), max(ys)) == pytest.approx((-.15, 6.15, -.15, 4.15), abs=2e-3)
    assert solaio.find_footprint(type(scene)()) is None


def test_footprint_of_a_level_takes_the_walls_given_no_level(viewport):
    # an L-shaped house drawn before the model had levels; the one wall drawn after, on
    # the ground floor, is the wing's west wall carried on down through the house: outside
    # above y = 6, a partition below it, the house's north wall meeting it half way
    from shapely.geometry import Polygon
    from myhouse import muri, solaio
    scene = viewport.scene
    ground = {"id": "L0", "name": "Ground"}

    def walls(pts, level=None, z=0.0):
        muri.build_walls(scene, pts, False, 0.30, 2.7, z, "W", align="center", level=level)
    walls([(0., 0.), (10., 0.), (10., 10.), (6., 10.)])
    walls([(6., 6.), (0., 6.), (0., 0.)])
    walls([(6., 10.), (6., 0.)], ground)
    whole = Polygon(solaio.find_footprint(scene, 3., 2.))
    assert whole.area == pytest.approx(82., abs=0.2)           # the L, out to the wall faces
    foot = Polygon(solaio.find_footprint(scene, 3., 2., "L0"))
    assert foot.area == pytest.approx(whole.area, abs=1e-6)   # not a ring round that one wall
    assert foot.bounds == pytest.approx((-.15, -.15, 10.15, 10.15), abs=2e-3)
    assert solaio.find_room(scene, 3., 3., "L0") is not None   # nor is the room it closes lost
    # walls given no level on the storey above are not this level's
    walls([(20., 0.), (24., 0.), (24., 4.), (20., 4.), (20., 0.)], None, 2.7)
    assert Polygon(solaio.find_footprint(scene, 3., 2., "L0")).area == pytest.approx(whole.area, abs=1e-6)
    # a level whose walls all carry it is read as before
    walls([(30., 0.), (34., 0.), (34., 4.), (30., 4.), (30., 0.)], {"id": "L1", "name": "First"}, 2.7)
    assert Polygon(solaio.find_footprint(scene, 32., 2., "L1")).area == pytest.approx(4.3 * 4.3, abs=0.05)


def test_tool_computes_and_creates_the_roof(viewport, monkeypatch):
    from myhouse import tetto
    tool = tetto.TettoTool()
    tool._scene = viewport.scene
    tool.points = list(L_SHAPE)
    tool.phase = "lines"
    monkeypatch.setattr(tetto.QInputDialog, "getText", staticmethod(lambda *a, **k: ("45°", True)))
    tool._auto_start(viewport)
    assert tool.phase == "auto" and tool.auto["gables"] == set()
    before = dict(tool.heights)
    tool.auto["gables"] ^= {0}                                  # the 8 m side becomes a gable end
    assert tool._auto_solve(viewport) and tool.heights != before
    n = len(viewport.scene.groups)
    tool._commit(viewport)
    roofs = [g for g in viewport.scene.groups if tetto.roof_data(g)]
    assert len(viewport.scene.groups) == n + 1 and len(roofs) == 1
    assert tetto.roof_data(roofs[0])["rise"] > 1.0
