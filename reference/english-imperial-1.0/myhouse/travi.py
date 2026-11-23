# SPDX-License-Identifier: GPL-3.0-or-later
"""Plugin Trave per IngeTrazo / MyHouse — crea travi BIM (IfcBeam).

Uso: MyHouse > Trave, scegli larghezza, altezza della sezione e altezza da
terra, poi:
  - clic sul punto iniziale e clic sul punto finale: la trave nasce
    orizzontale (gli estremi si agganciano al centro dei pilastri)
  - Esc o tasto destro esce dal comando

Per INCLINARE una trave: doppio clic su di lei (strumento Seleziona) o
"Edit beam elevations…" nel menu del tasto destro. Compaiono due quadratini
rossi, uno su ciascun lato corto: clic su uno, inserisci l'altezza da terra
di quel lato (si alza tutto il lato, non punto per punto). Invio applica,
Esc annulla. "Edit beam section…" cambia larghezza, altezza e nome.

"Altezza da terra" = quota della faccia INFERIORE della trave.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QVector3D
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout,
)

from core import bim
from tools.base import Tool, ToolContext

from . import muri, piani
from ._i18n import tr
from ._imperial import FT, IN, ask_length, dflt, fmt, spin as _spin

ORDER = 60
BEAM_COLOR = (0.70, 0.55, 0.38)
LAYER_NAME = "Beams"
KEY = "myhouse_trave"           # parametri in group.ext
SNAP = 0.40                     # aggancio al centro dei pilastri (m)


class _Settings:
    w = dflt(6 * IN, 0.20)      # larghezza della sezione
    h = dflt(12 * IN, 0.20)     # altezza della sezione
    z0 = dflt(8 * FT, 3.00)     # altezza da terra (faccia inferiore)
    name = tr("Beam")
    level = None                # id del piano (None = nessuno)


# ---------------------------------------------------------------------------
# Geometria pura
# ---------------------------------------------------------------------------

def beam_corners(d):
    """Gli 8 vertici: dict con A1,A2,B1,B2 (bassi) e le versioni alte."""
    ax, ay = d["a"]
    bx, by = d["b"]
    L = math.hypot(bx - ax, by - ay) or 1.0
    nx, ny = -(by - ay) / L * d["w"] / 2, (bx - ax) / L * d["w"] / 2
    P = QVector3D
    zab, zbb = d["za"], d["zb"]
    h = d["h"]
    return {
        "A1b": P(ax + nx, ay + ny, zab), "A2b": P(ax - nx, ay - ny, zab),
        "B1b": P(bx + nx, by + ny, zbb), "B2b": P(bx - nx, by - ny, zbb),
        "A1t": P(ax + nx, ay + ny, zab + h), "A2t": P(ax - nx, ay - ny, zab + h),
        "B1t": P(bx + nx, by + ny, zbb + h), "B2t": P(bx - nx, by - ny, zbb + h),
    }


def beam_mesh(d):
    from core.mesh import Mesh
    c = beam_corners(d)
    mesh = Mesh()

    def face(keys):
        f = mesh.add_face([c[k] for k in keys])
        # nessun colore predefinito: si applicano i materiali di IngeTrazo
        f.attrs["layer"] = LAYER_NAME

    face(["A2t", "B2t", "B1t", "A1t"])          # sopra
    face(["A1b", "B1b", "B2b", "A2b"])          # sotto
    face(["A2b", "B2b", "B2t", "A2t"])          # lato destro
    face(["B1b", "A1b", "A1t", "B1t"])          # lato sinistro
    face(["B2b", "B1b", "B1t", "B2t"])          # testa B
    face(["A1b", "A2b", "A2t", "A1t"])          # testa A
    return mesh


def beam_edges(d):
    """Spigoli del parallelepipedo (per l'anteprima)."""
    c = beam_corners(d)
    pairs = [("A1b", "B1b"), ("A2b", "B2b"), ("A1t", "B1t"), ("A2t", "B2t"),
             ("A1b", "A2b"), ("B1b", "B2b"), ("A1t", "A2t"), ("B1t", "B2t"),
             ("A1b", "A1t"), ("A2b", "A2t"), ("B1b", "B1t"), ("B2b", "B2t")]
    return [(c[a], c[b]) for a, b in pairs]


def beam_data(group):
    data = (getattr(group, "ext", None) or {}).get(KEY)
    return data if isinstance(data, dict) and "a" in data else None


def build_beam(scene, d, name) -> None:
    from core.group import Group
    if not any(ly.name == LAYER_NAME for ly in scene.layers):
        from core.layers import Layer
        scene.layers.append(Layer(LAYER_NAME))
    part = Group(beam_mesh(d), name="Beam")
    part.component = False
    g = Group(name=name)
    g.adopt([part])
    g.component = False
    g.layer = LAYER_NAME
    bim.tag_group(g, "IfcBeam", name)
    g.ext = {KEY: d}
    scene.groups.append(g)


def rebuild_beam(group, p: dict) -> None:
    d = dict(beam_data(group))
    d.update(p)
    from core.group import Group
    part = Group(beam_mesh(d), name="Beam")
    part.component = False
    group.children = [part]
    group.name = d.get("name", group.name)
    ext = dict(group.ext or {})
    ext[KEY] = d
    group.ext = ext


def _pillar_centres(scene):
    try:
        from . import pilastri
    except ImportError:
        return []
    out = []
    for g in scene.groups:
        d = pilastri.pillar_data(g)
        if d is not None:
            out.append((d["c"][0], d["c"][1]))
    return out


def snap_point(scene, x, y):
    best, hit = SNAP, None
    for cx, cy in _pillar_centres(scene):
        dist = math.hypot(cx - x, cy - y)
        if dist < best:
            best, hit = dist, (cx, cy)
    return hit if hit else (x, y)


# ---------------------------------------------------------------------------
# Dialoghi
# ---------------------------------------------------------------------------

def ask_section(parent, cur: dict, title: str, with_z: bool,
                scene=None):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    form = QFormLayout()
    w = _spin(cur["w"], 0.02, 5.0)
    h = _spin(cur["h"], 0.02, 5.0)
    z0 = _spin(cur.get("z0", 0.0), -100.0, 1000.0)
    name = QLineEdit(cur["name"])
    form.addRow(tr("Section width"), w)
    form.addRow(tr("Section height"), h)
    lvl = None
    if with_z:
        if scene is not None and piani.levels(scene):
            lvl = piani.level_combo(scene, cur.get("lv"))
            form.addRow(tr("Level"), lvl)
        form.addRow(tr("Height above floor / above level - bottom face"), z0)
    form.addRow(tr("Name"), name)
    lay.addLayout(form)
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    if dlg.exec() != QDialog.Accepted:
        return None
    return {"w": w.value(), "h": h.value(), "z0": z0.value(),
            "name": name.text().strip() or tr("Beam"),
            "lv": (lvl.currentData() or None) if lvl is not None else None}


# ---------------------------------------------------------------------------
# Strumento
# ---------------------------------------------------------------------------

class TraveTool(Tool):
    name = "Beam"
    shortcut = None
    description = "Creates a beam (start and end click); double-click to slope it."

    def __init__(self) -> None:
        self._entering = False
        self._reset()

    def _reset(self) -> None:
        self.mode = "create"             # "create" | "edit"
        self.start = None                # (x, y, z) primo punto
        self.hover: QVector3D | None = None
        self.group = None                # trave in modifica
        self.d: dict | None = None       # parametri provvisori in modifica

    # -- ciclo di vita ------------------------------------------------------
    def on_activate(self, viewport) -> None:
        self._vp = viewport
        if self._entering:
            if self.mode != "edit":
                self._reset()
                viewport.flash_status(
                    tr("Beam: click the start point and then the end point · "
                       "Esc = exit"), 6000)
            return
        p = ask_section(viewport.window(),
                        {"w": _Settings.w, "h": _Settings.h,
                         "z0": _Settings.z0, "name": _Settings.name,
                         "lv": piani.active_id(viewport.scene)},
                        tr("Beam"), True, viewport.scene)
        if p is None:
            return
        _Settings.w, _Settings.h = p["w"], p["h"]
        _Settings.z0, _Settings.name = p["z0"], p["name"]
        _Settings.level = p.get("lv")
        piani.set_active(_Settings.level)
        self._activate(viewport)

    def _activate(self, viewport) -> None:
        self._entering = True
        try:
            viewport.set_active_tool(self)
        finally:
            self._entering = False

    def edit(self, viewport, group) -> None:
        """Inclina una trave esistente: clic su un lato corto."""
        d = beam_data(group)
        if d is None:
            return
        if getattr(viewport.scene, "edit_group", None) is not None:
            viewport.flash_status(tr("Close the group you are editing"), 4000)
            return
        self._reset()
        self.mode = "edit"
        self._activate(viewport)
        self.mode = "edit"
        self.group = group
        self.d = dict(d)
        viewport.flash_status(
            tr("Click a red square (short side) to change its height above "
               "floor · Enter = apply · Esc = cancel"), 8000)
        viewport.update()

    def on_deactivate(self, viewport) -> None:
        self._reset()

    def on_cancel(self, viewport) -> None:
        self._reset()
        viewport.update()

    def _exit(self, viewport) -> None:
        self._reset()
        viewport.update()
        back = getattr(viewport.window(), "activate_select_tool", None)
        if callable(back):
            back()

    def context_menu(self, viewport, pos) -> bool:
        self._exit(viewport)
        return True

    def claims_key(self, key: int, modifiers) -> bool:
        if modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        return key == Qt.Key_Escape

    def on_key(self, viewport, key: int, modifiers) -> bool:
        if key == Qt.Key_Escape:
            self._exit(viewport)
            return True
        if self.mode == "edit" and key in (Qt.Key_Return, Qt.Key_Enter):
            self._apply(viewport)
            return True
        if self.mode == "create" and key == Qt.Key_Backspace and self.start:
            self.start = None
            viewport.update()
            return True
        return False

    # -- eventi ---------------------------------------------------------------
    def on_hover(self, ctx: ToolContext) -> None:
        self.hover = QVector3D(ctx.world)
        ctx.viewport.update()

    def _ends(self):
        """[(x, y, z_centro, chiave 'za'/'zb')] dei due lati corti."""
        d = self.d
        return [(d["a"][0], d["a"][1], d["za"] + d["h"] / 2, "za"),
                (d["b"][0], d["b"][1], d["zb"] + d["h"] / 2, "zb")]

    def _pick_end(self, vp, world, radius=22.0):
        px = vp._world_to_pixel(QVector3D(world))
        best, bk = None, None
        for x, y, z, k in self._ends():
            pc = vp._world_to_pixel(QVector3D(x, y, z))
            if px is None or pc is None:
                dist = math.hypot(x - world.x(), y - world.y()) * 100
            else:
                dist = math.hypot(pc[0] - px[0], pc[1] - px[1])
            if dist < radius and (best is None or dist < best):
                best, bk = dist, k
        return bk

    def on_click(self, ctx: ToolContext) -> None:
        vp = ctx.viewport
        if self.mode == "edit":
            k = self._pick_end(vp, ctx.world)
            if k is None:
                vp.flash_status(tr("Click a red square"), 3000)
                return
            val, ok = ask_length(
                vp.window(), tr("End elevation"),
                tr("Height above floor of this end"),
                self.d[k], -100.0, 1000.0)
            if ok:
                self.d[k] = val
            vp.update()
            return
        if getattr(vp.scene, "edit_group", None) is not None:
            vp.flash_status(tr("Close the group you are editing"), 4000)
            return
        x, y = snap_point(vp.scene, ctx.world.x(), ctx.world.y())
        if self.start is None:
            self.start = (x, y, ctx.world.z())
            vp.update()
            return
        sx, sy, sz = self.start
        if math.hypot(x - sx, y - sy) < 1e-3:
            vp.flash_status(tr("The two points coincide"), 3000)
            return
        z, extra = piani.place(vp.scene, _Settings.level, _Settings.z0)
        d = {"a": [sx, sy], "b": [x, y], "za": z, "zb": z,
             "w": _Settings.w, "h": _Settings.h, "name": _Settings.name}
        d.update(extra)
        name = _Settings.name

        def mutate(scene):
            build_beam(scene, d, name)

        vp.history.execute(muri.MuriCommand(mutate))
        vp.notify_scene_changed()
        vp.flash_status(tr("Beam created · double-click to slope it"), 3500)
        self.start = None
        vp.update()

    def _apply(self, viewport) -> None:
        group, d = self.group, self.d

        def mutate(scene):
            q = dict(d)
            lv = piani.get(scene, q.get("lv"))
            if lv:                          # le quote dei lati sono cambiate
                q["off"] = min(q["za"], q["zb"]) - lv["z"]
            rebuild_beam(group, q)

        viewport.history.execute(muri.MuriCommand(mutate))
        viewport.notify_scene_changed()
        viewport.flash_status(tr("Beam edited"), 3000)
        self._exit(viewport)

    # -- disegno -------------------------------------------------------------
    def rubber_band_lines(self):
        if self.mode == "edit" and self.d is not None:
            return beam_edges(self.d)
        if self.start is None or self.hover is None:
            return []
        x, y = snap_point_cache(self.hover)
        sx, sy, sz = self.start
        vp = getattr(self, "_vp", None)
        z = (piani.place(vp.scene, _Settings.level, _Settings.z0)[0]
             if vp is not None else _Settings.z0)
        d = {"a": [sx, sy], "b": [x, y], "za": z, "zb": z,
             "w": _Settings.w, "h": _Settings.h}
        if math.hypot(x - sx, y - sy) < 1e-3:
            return []
        return beam_edges(d)

    def draw_overlay(self, viewport, painter) -> None:
        try:
            if self.mode == "edit" and self.d is not None:
                self._draw_ends(viewport, painter)
        except Exception:
            pass

    def _draw_ends(self, viewport, painter) -> None:
        from PySide6.QtCore import QPointF, QRectF
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        hot = None
        if self.hover is not None:
            hot = self._pick_end(viewport, self.hover)
        for x, y, z, k in self._ends():
            pc = viewport._world_to_pixel(QVector3D(x, y, z))
            if pc is None:
                continue
            r = 9 if k == hot else 7
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.setBrush(QColor(255, 210, 0) if k == hot
                             else QColor(220, 30, 30))
            painter.drawRect(QRectF(pc[0] - r, pc[1] - r, 2 * r, 2 * r))
            painter.setPen(QPen(QColor(20, 20, 20)))
            painter.drawText(QPointF(pc[0] + r + 4, pc[1] - r),
                             fmt(self.d[k]))
        painter.restore()


_snap_scene = {"scene": None}


def snap_point_cache(p: QVector3D):
    """Aggancio per l'anteprima (usa la scena dell'ultimo clic/hover)."""
    sc = _snap_scene["scene"]
    return snap_point(sc, p.x(), p.y()) if sc is not None else (p.x(), p.y())


# ---------------------------------------------------------------------------
# Modifica sezione e registrazione
# ---------------------------------------------------------------------------

def _selected_beams(scene):
    out = []
    for e in scene.selection:
        g = getattr(e, "owner", None) or e
        if g in scene.groups and beam_data(g) is not None and g not in out:
            out.append(g)
    return out


def edit_section(viewport, groups=None) -> None:
    scene = viewport.scene
    if getattr(scene, "edit_group", None) is not None:
        viewport.flash_status(tr("Close the group you are editing"), 4000)
        return
    groups = groups or _selected_beams(scene)
    if not groups:
        viewport.flash_status(tr("Select a beam"), 3000)
        return
    d0 = beam_data(groups[0])
    p = ask_section(viewport.window(), d0, tr("Edit beam section"), False)
    if p is None:
        return
    p.pop("z0")
    p.pop("lv", None)

    def mutate(sc):
        for g in groups:
            q = dict(p)
            if len(groups) > 1:
                q.pop("name")
            rebuild_beam(g, q)

    viewport.history.execute(muri.MuriCommand(mutate))
    viewport.notify_scene_changed()
    viewport.update()
    viewport.flash_status(tr("{n} beams updated", n=len(groups)), 3000)


def _hook_double_click(vp, tool) -> None:
    """Doppio clic su una trave = modifica le quote dei lati corti."""
    if getattr(vp, "_myhouse_travi_dbl", False):
        return
    original = vp.begin_group_edit

    def begin_group_edit(group, *args, **kwargs):
        g = getattr(group, "owner", None) or group
        if beam_data(g) is None:
            return original(group, *args, **kwargs)
        from PySide6.QtCore import QTimer
        _snap_scene["scene"] = vp.scene
        QTimer.singleShot(0, lambda: tool.edit(vp, g))

    vp.begin_group_edit = begin_group_edit
    vp._myhouse_travi_dbl = True


def _icon():
    from PySide6.QtGui import QIcon, QPainter, QPixmap
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(60, 60, 60), 2))
    p.setBrush(QColor(200, 198, 190))
    p.drawRect(6, 14, 8, 26)
    p.drawRect(34, 14, 8, 26)
    p.setBrush(QColor(176, 140, 96))
    p.drawRect(4, 8, 40, 8)
    p.end()
    return QIcon(pm)


def _outliner_kind(group):
    d = beam_data(group)
    if d is None:
        return None
    L = math.hypot(d["b"][0] - d["a"][0], d["b"][1] - d["a"][1])
    return {"type": tr("Beam"),
            "props": [(tr("Section"), f"{fmt(d['w'])} × {fmt(d['h'])}"),
                      (tr("Length"), fmt(L)),
                      (tr("Elevation end A"), fmt(d["za"])),
                      (tr("Elevation end B"), fmt(d["zb"]))]
            + piani.level_props(d)}


def _register_level_kind() -> None:
    def zget(d):
        return min(d["za"], d["zb"])

    def zset(d, z):
        delta = z - zget(d)
        d["za"] += delta
        d["zb"] += delta

    piani.register_kind("trave", KEY, beam_data, zget, zset, rebuild_beam)


def register(api) -> None:
    _register_level_kind()
    tool = TraveTool()
    base_activate = tool.on_activate

    def activate(viewport):
        _snap_scene["scene"] = viewport.scene
        base_activate(viewport)

    tool.on_activate = activate
    api.add_button(tr("Beam"), tr("Creates a beam (horizontal or sloped)"),
                   _icon(), api.run_tool(tool))
    app = api.app
    _hook_double_click(api.window.viewport, tool)
    add_ctx = getattr(app, "add_context_menu", None)
    if add_ctx is not None:
        from PySide6.QtCore import QTimer

        def context(menu, selection) -> None:
            beams = _selected_beams(app.viewport.scene)
            if not beams:
                return
            menu.addSeparator()
            menu.addAction(
                tr("Edit beam elevations…"),
                lambda: QTimer.singleShot(
                    0, lambda: tool.edit(app.viewport, beams[0])))
            menu.addAction(
                tr("Edit beam section…"),
                lambda: QTimer.singleShot(
                    0, lambda: edit_section(app.viewport)))

        add_ctx(context)
    add_kind = getattr(app, "add_outliner_kind", None)
    if add_kind is not None:
        add_kind(_outliner_kind)
