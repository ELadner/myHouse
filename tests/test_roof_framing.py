"""The roof asked for as it is framed (feet and inches): rafter depth, top
plate and bird's mouth put it in place."""
import math

import pytest
from PySide6.QtWidgets import QDialog, QFormLayout

IN, FT = 0.0254, 0.3048
RECT = [(0., 0.), (20 * FT, 0.), (20 * FT, 12 * FT), (0., 12 * FT)]
PLUMB = 7.25 * IN * math.hypot(1, 0.5)          # a 2x8 at 6 in 12, straight up and down


@pytest.fixture
def roof(viewport, monkeypatch):
    """roof(units, points, ...) draws an automatic 6/12 roof and returns its data."""
    from myhouse import _imperial, tetto

    def make(units="imperial", points=RECT, gables=(), depth=7.25 * IN, plate=8 * FT, seat=3.5 * IN, overhang=0.0):
        monkeypatch.setattr(_imperial, "_setting", units)
        for k, v in dict(thickness=depth, z_base=plate, seat=seat, offset=overhang, layers=None, level=None,
                         pitch=math.degrees(math.atan2(6, 12)), travi=dict(tetto._TRAVI_DEFAULT),
                         tipo_id=None, tipo_nome=None).items():
            monkeypatch.setattr(tetto._Settings, k, v)
        tool = tetto.TettoTool()
        tool._reset()
        tool._scene = viewport.scene
        tool.auto = {"pts": [tuple(p) for p in points], "gables": set(gables)}
        assert tool._auto_solve(viewport)
        tool._commit(viewport)
        return tetto.roof_data([g for g in viewport.scene.groups if tetto.roof_data(g)][-1])
    return make


def walls(viewport, width=3.5 * IN, height=8 * FT):
    """A 20' x 12' house; returns the outline on the outer face of its walls."""
    from myhouse import muri, solaio
    muri.build_walls(viewport.scene, RECT, True, width, height, 0.0, "W", align="center")
    return solaio.find_footprint(viewport.scene, 3., 2.)


def test_roof_on_walls_sits_on_the_plate_with_a_birdsmouth(viewport, roof):
    d = roof(points=walls(viewport))
    fr = d["fr"]
    assert fr["wall"] == pytest.approx(3.5 * IN) and fr["seat"] == pytest.approx(3.5 * IN)
    assert fr["heel"] == pytest.approx(1.75 * IN) and fr["slope"] == pytest.approx(0.5)
    assert fr["depth"] == pytest.approx(7.25 * IN) and fr["plate"] == pytest.approx(8 * FT)
    assert d["th"] == pytest.approx(PLUMB)                                   # every other tool reads it plumb
    assert d["base"] == pytest.approx(8 * FT + PLUMB - 1.75 * IN)            # plate + height above plate
    assert min(c[2] for c in d["ctrl"]) == pytest.approx(d["base"])


def test_walls_under_the_plate_are_not_cut_to_the_slope(viewport, roof):
    from myhouse import muri, tetto
    scene = viewport.scene
    outline = walls(viewport)
    muri.build_walls(scene, [(10 * FT, 0.), (10 * FT, 12 * FT)], False, 3.5 * IN, 11 * FT, 0.0, "T", align="center")
    roof(points=outline)
    cut = {round(muri.wall_data(g)["h"] / FT): "clip" in muri.wall_data(g) for g in scene.groups if muri.wall_data(g)}
    assert cut == {8: False, 11: True}          # the rafters overlap the plate; a wall through the roof is still cut
    assert tetto.update_roof_clips(scene) == 0


def test_walls_under_a_metric_roof_are_cut_as_before(viewport, roof):
    from myhouse import muri
    outline = walls(viewport, width=0.30, height=3.0)
    roof(units="metric", points=outline, depth=0.20, plate=3.1)               # its underside dips into the walls
    assert all("clip" in muri.wall_data(g) for g in viewport.scene.groups if muri.wall_data(g))


def test_roof_on_a_wide_wall_gets_a_shorter_seat(viewport, roof):
    d = roof(points=walls(viewport, width=11.25 * IN))
    fr = d["fr"]
    assert fr["wall"] == pytest.approx(11.25 * IN) and fr["limited"]
    assert fr["notch"] == pytest.approx(7.25 * IN / 4) and fr["seat"] < 11.25 * IN


def test_roof_with_no_wall_underneath_uses_the_seat_asked_for(viewport, roof):
    d = roof(seat=2 * IN)
    assert d["fr"]["wall"] is None and d["fr"]["seat"] == pytest.approx(2 * IN)
    assert d["base"] == pytest.approx(8 * FT + PLUMB - 1 * IN)
    bare = roof(seat=0.0)                                                    # on a beam: no bird's mouth
    assert bare["fr"]["heel"] == 0 and bare["base"] == pytest.approx(8 * FT + PLUMB)


def test_overhang_runs_down_from_the_wall_line(viewport, roof):
    d = roof(points=walls(viewport), overhang=2 * FT)
    assert d["base"] == pytest.approx(8 * FT + PLUMB - 1.75 * IN)            # still the top over the wall face
    assert min(c[2] for c in d["ctrl"]) == pytest.approx(d["base"] - 1 * FT) # 2' out at 6 in 12


def test_metric_roof_is_as_it_always_was(viewport, roof):
    d = roof(units="metric", points=walls(viewport), depth=0.20, plate=3.0)
    assert "fr" not in d and d["th"] == pytest.approx(0.20) and d["base"] == pytest.approx(3.0)


def test_eaves_of_a_hand_drawn_shed_roof(myhouse):
    from myhouse import tetto
    sq = [(0., 0.), (4., 0.), (4., 4.), (0., 4.)]
    high = {(0., 4.): 1.0, (4., 4.): 1.0}                                    # the far side 1 m up
    eaves = tetto.eave_slopes(sq, [], lambda p: high.get((p[0], p[1]), 0.0))
    assert [(a, b) for a, b, _s in eaves] == [((0., 0.), (4., 0.))]          # only the low side
    assert eaves[0][2] == pytest.approx(0.25)
    assert all(s == 0 for _a, _b, s in tetto.eave_slopes(sq, [], lambda p: 0.0)) and len(tetto.eave_slopes(sq, [], lambda p: 0.0)) == 4


def test_editing_keeps_the_roof_and_gives_back_what_was_typed(viewport, roof):
    from myhouse import tetto
    d = roof(points=walls(viewport))
    group = [g for g in viewport.scene.groups if tetto.roof_data(g)][-1]
    tool = tetto.TettoTool()
    tool.edit(viewport, group)
    assert not tool.legacy and tetto._Settings.thickness == pytest.approx(7.25 * IN)
    assert tetto._Settings.z_base == pytest.approx(8 * FT)
    tool._commit(viewport)
    again = tetto.roof_data(group)
    assert again["base"] == pytest.approx(d["base"]) and again["th"] == pytest.approx(d["th"])
    assert again["fr"]["plate"] == pytest.approx(8 * FT)


def test_old_roof_keeps_its_place_when_it_is_given_rafters(viewport, roof, monkeypatch):
    from myhouse import _imperial, tetto
    outline = walls(viewport)
    old = roof(units="metric", points=outline, depth=0.20, plate=3.0)
    group = [g for g in viewport.scene.groups if tetto.roof_data(g)][-1]
    monkeypatch.setattr(_imperial, "_setting", "imperial")
    tool = tetto.TettoTool()
    tool.edit(viewport, group)
    assert tool.legacy                                                       # a height edit leaves it alone
    tool._commit(viewport)
    assert "fr" not in tetto.roof_data(group) and tetto.roof_data(group)["base"] == pytest.approx(3.0)
    tool = tetto.TettoTool()
    tool.edit(viewport, group)
    tool._adopt_framing(old)                                                 # what the settings panel does
    assert tetto._Settings.thickness == pytest.approx(0.20 / math.hypot(1, 0.5))
    tool._commit(viewport)
    new = tetto.roof_data(group)
    assert new["base"] == pytest.approx(3.0) and new["th"] == pytest.approx(0.20)
    assert new["fr"]["plate"] == pytest.approx(3.0 - new["fr"]["hap"])


def test_reframe_with_a_deeper_rafter_lifts_the_roof(viewport, roof):
    from myhouse import tetto
    d = roof(points=walls(viewport))
    deep = tetto.reframe(d, 9.25 * IN)                                       # a 2x10
    assert deep["th"] == pytest.approx(9.25 * IN * math.hypot(1, 0.5))
    assert deep["base"] - d["base"] == pytest.approx(2 * IN * math.hypot(1, 0.5))
    assert deep["fr"]["plate"] == d["fr"]["plate"] and d["th"] == pytest.approx(PLUMB)   # d itself untouched
    tetto.roof_mesh(deep)


def test_layers_of_a_framed_roof_are_square_to_the_slope(viewport, roof):
    from myhouse import tetto
    d = roof(points=walls(viewport))
    d = dict(d, layers=[{"t": 0.75 * IN, "name": "sheathing"}, {"t": 6.5 * IN, "name": "rafters"}])
    subs = tetto._layer_subs(d)
    assert sum(s["th"] for s in subs) == pytest.approx(PLUMB)
    assert subs[1]["_dz"] == pytest.approx(0.75 * IN * math.hypot(1, 0.5))
    tetto.roof_mesh(d)


@pytest.mark.parametrize("units,framed", [("imperial", True), ("metric", False)])
def test_dialog_asks_for_rafter_and_plate_in_feet_and_inches(units, framed, window, monkeypatch):
    from myhouse import _imperial, tetto
    from myhouse._lingua import tr
    monkeypatch.setattr(_imperial, "_setting", units)
    for k, v in dict(thickness=7.25 * IN, z_base=8 * FT, seat=3.5 * IN, layers=None, level=None).items():
        monkeypatch.setattr(tetto._Settings, k, v)
    seen = {}

    def fake_exec(dlg):
        dlg.show()
        for form in dlg.findChildren(QFormLayout):
            for r in range(form.rowCount()):
                li, fi = form.itemAt(r, QFormLayout.LabelRole), form.itemAt(r, QFormLayout.FieldRole)
                if li is not None and fi is not None and li.widget() is not None:
                    seen[li.widget().text()] = fi.widget()
        mark = "(ft-in)" if framed else "(m)"
        for label, field in seen.items():
            if label.startswith(tr("Appoggio dove non c'è un muro sotto (a) (m)").replace("(m)", mark)[:12]) and framed:
                field.setValue(2 * IN)
        dlg.close()
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    assert tetto.ask_settings(window)
    labels = " | ".join(seen)
    assert (tr("Altezza del puntone, in squadra con la falda (s) (m)")[:12] in labels) == framed
    assert (tr("Banchina: da terra / sopra la quota del piano (z) (m)")[:10] in labels) == framed
    assert (tr("Gronda: da terra / sopra la quota del piano (z) (m)")[:6] in labels) != framed
    assert tetto._Settings.seat == pytest.approx(2 * IN if framed else 3.5 * IN)
