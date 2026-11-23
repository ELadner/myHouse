# SPDX-License-Identifier: GPL-3.0-or-later
"""Plugin Porte per IngeTrazo — inserisce porte parametriche.

File della cartella myhouse/ (vedi myhouse/__init__.py). Stessa logica
delle finestre (finestre.py): la porta si posa sul muro, lo buca da sola e
il foro la segue quando la sposti.

Uso: MyHouse > Porta, imposta le misure, poi:
  - clic              posa la porta con lo spigolo sul punto cliccato
  - Spazio            ribalta la porta: lo spigolo passa dall'altro lato
  - Esc / tasto destro  esce dal comando
Doppio clic su una porta (strumento Seleziona): modifica le misure.
Ogni porta è un gruppo (IfcDoor) con le parti Telaio e Anta.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QMatrix4x4, QPen, QVector3D
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout,
)

from core import bim
from tools.base import Tool, ToolContext

from . import finestre, piani
from ._i18n import tr
from ._imperial import FT, IN, dflt, fmt, spin
from .finestre import FinestraCommand

KEY = "myhouse_porta"            # chiave dei parametri in group.ext
LAYER_NAME = "Doors"
FRAME_COLOR = (0.93, 0.93, 0.90)
LEAF_COLOR = (0.66, 0.49, 0.33)
MODELS = [("porta", tr("Door")),
          ("varco", tr("Opening (hole only, no door)")),
          ("porta1", tr("Door 1 (long glass)")),
          ("porta2", tr("Door 2 (5 horizontal glass panes)")),
          ("porta3", tr("Door 3 (metal strips)")),
          ("porta4", tr("Door 4 (glass split in two)")),
          ("bifold", tr("Bi-fold (closet), single or dual")),
          ("garage1", tr("Garage 1 (ribbed up-and-over)")),
          ("garage2", tr("Garage 2 (sectional panels)"))]
# misure proposte passando a un garage
GARAGE_SIZE = (dflt(9 * FT, 2.50), dflt(7 * FT, 2.20))
GLASS_COLOR = (0.75, 0.85, 0.90)
METAL_COLOR = (0.75, 0.75, 0.78)
# (margine laterale, [(alto, basso) in frazione dall'alto dell'anta])
GLASS = {
    "porta1": (0.15, [(0.07, 0.92)]),
    "porta4": (0.15, [(0.07, 0.48), (0.558, 0.92)]),
    "porta2": (0.17, [(0.071, 0.132), (0.268, 0.329), (0.464, 0.525),
                      (0.663, 0.724), (0.863, 0.924)]),
}
STRIPS = [0.071, 0.186, 0.292, 0.397, 0.502, 0.607, 0.712, 0.818, 0.923]
ORDER = 30                       # posizione del pulsante nella barra


GAP = 0.003                      # gioco tra anta e telaio, per lato


def _around(model: str, leaves, fw: float):
    """What the frame adds around the door itself: (in width, in height).
    A plain opening has no frame: its size is the size of the hole."""
    if model == "varco":
        return 0.0, 0.0
    return 2 * fw + 2 * GAP * _panels(model, leaves), fw + 2 * GAP


def _panels(model: str, leaves) -> int:
    """How many panels stand side by side in the frame. A bi-fold is two
    hinged panels for each leaf: 2 single, 4 dual (a closet front)."""
    if model == "bifold":
        return 2 * int(leaves)
    return int(leaves) if model == "porta" else 1


def door_size(d: dict):
    """(width, height) of the door itself, the slab, without the frame: a
    30" door is 30" wide here, and its frame sits outside that. The stored
    W and H are the whole unit, frame included (that is the hole in the wall)."""
    aw, ah = _around(d.get("model", "porta"), d["leaves"], d["fw"])
    return d["W"] - aw, d["H"] - ah


class _Settings:
    fw = dflt(0.75 * IN, 0.06)   # telaio: larghezza del profilo (3/4" jamb)
    # W e H sono totali, telaio compreso: qui una 3068 (anta 3'0" x 6'8")
    W = dflt(36 * IN, 0.90) + 2 * fw + 2 * GAP
    H = dflt(80 * IN, 2.10) + fw + 2 * GAP
    sill = 0.0          # altezza da terra (soglia)
    leaves = 1          # numero di ante (1 o 2)
    fd = dflt(4.5625 * IN, 0.12)  # telaio: profondità (4 9/16")
    sw = dflt(1.75 * IN, 0.04)   # spessore dell'anta
    model = "porta"     # porta | garage1 | garage2
    flip = False        # True = reversed: handle on the other side
    anchor = "left"     # what the cursor holds: left | middle | right
    level = None        # piano dei muri su cui posare (None = tutti)


def _params() -> dict:
    return {"W": _Settings.W, "H": _Settings.H, "sill": _Settings.sill,
            "leaves": _Settings.leaves, "fw": _Settings.fw,
            "fd": _Settings.fd, "sw": _Settings.sw,
            "model": _Settings.model}


def _store(p: dict) -> None:
    _Settings.W, _Settings.H, _Settings.sill = p["W"], p["H"], p["sill"]
    _Settings.leaves, _Settings.fw = p["leaves"], p["fw"]
    _Settings.fd, _Settings.sw = p["fd"], p["sw"]
    _Settings.model = p.get("model", "porta")


def validate(p: dict) -> str | None:
    if p["W"] <= 2 * p["fw"] + 0.2 * p["leaves"]:
        return tr("Width too small for frame and leaves")
    if p["H"] <= p["fw"] + 0.3:
        return tr("Height too small for frame and leaf")
    if p["sw"] >= p["fd"]:
        return tr("The leaf must be thinner than the frame")
    return None


# ---------------------------------------------------------------------------
# Geometria
# ---------------------------------------------------------------------------

def _box(mesh, T, a0, a1, b0, b1, c0, c1, color):
    """Prisma chiuso con le normali verso l'esterno."""
    quads = [
        [(a0, b0, c0), (a0, b0, c1), (a0, b1, c1), (a0, b1, c0)],
        [(a1, b0, c0), (a1, b1, c0), (a1, b1, c1), (a1, b0, c1)],
        [(a0, b0, c0), (a1, b0, c0), (a1, b0, c1), (a0, b0, c1)],
        [(a0, b1, c0), (a0, b1, c1), (a1, b1, c1), (a1, b1, c0)],
        [(a0, b0, c0), (a0, b1, c0), (a1, b1, c0), (a1, b0, c0)],
        [(a0, b0, c1), (a1, b0, c1), (a1, b1, c1), (a0, b1, c1)],
    ]
    for q in quads:
        f = mesh.add_face([T(*v) for v in q])
        # nessun colore predefinito: si applicano i materiali di IngeTrazo
        f.attrs["layer"] = LAYER_NAME


def _garage1(leaf, T, d) -> None:
    """Basculante: coste verticali, feritoie in alto e in basso, maniglie."""
    W, H, fw, sw = d["W"], d["H"], d["fw"], d["sw"]
    x0, x1 = fw + 0.003, W - fw - 0.003
    z0, z1 = 0.003, H - fw - 0.003
    b0, b1 = sw / 2, sw / 2 + 0.008
    pitch = 0.10
    n = max(1, int(round((x1 - x0) / pitch)))
    step = (x1 - x0) / n
    for i in range(1, n):                        # coste (rilievi)
        x = x0 + i * step
        _box(leaf, T, x - 0.006, x + 0.006, b0, b1, z0, z1, LEAF_COLOR)
    zh = 0.12                                    # fasce con feritoie
    for zc in (z1 - 0.12, z0 + 0.12):
        for i in range(n):
            xc = x0 + (i + 0.5) * step
            for k in range(3):
                zz = zc - zh / 2 + k * zh / 3
                _box(leaf, T, xc - 0.025, xc + 0.025, b0, b1 + 0.006,
                     zz, zz + 0.02, LEAF_COLOR)
    xm, zm = (x0 + x1) / 2, (z0 + z1) / 2        # maniglia centrale
    _box(leaf, T, xm - 0.04, xm + 0.04, b1, b1 + 0.03,
         zm - 0.01, zm + 0.01, LEAF_COLOR)
    _box(leaf, T, xm - 0.01, xm + 0.01, b1, b1 + 0.03,
         zm - 0.06, zm + 0.06, LEAF_COLOR)
    _box(leaf, T, xm - 0.04, xm + 0.04, b1, b1 + 0.03,
         z0 + 0.20, z0 + 0.22, LEAF_COLOR)       # maniglia bassa


def _garage2(leaf, T, d) -> None:
    """Sezionale: pannelli orizzontali separati da scanalature."""
    W, H, fw, sw = d["W"], d["H"], d["fw"], d["sw"]
    x0, x1 = fw + 0.003, W - fw - 0.003
    z0, z1 = 0.003, H - fw - 0.003
    b0 = sw / 2
    n = max(2, int(round((z1 - z0) / 0.20)))
    step = (z1 - z0) / n
    for i in range(n):                           # ogni pannello in rilievo
        za = z0 + i * step + 0.006
        zb = z0 + (i + 1) * step - 0.006
        _box(leaf, T, x0, x1, b0, b0 + 0.008, za, zb, LEAF_COLOR)


def _handle(hw, T, x, zc, sw) -> None:
    """Maniglia a leva con rosetta e serratura, su entrambe le facce."""
    for s in (1, -1):
        inn, out = s * sw / 2, s * (sw / 2 + 0.05)   # faccia anta / esterno
        rs = s * (sw / 2 + 0.01)                     # spessore rosetta

        def box(a0, a1, c0, c1, p, q):
            _box(hw, T, a0, a1, min(p, q), max(p, q), c0, c1, METAL_COLOR)

        box(x - 0.03, x + 0.03, zc - 0.03, zc + 0.03, inn, rs)       # rosetta
        box(x - 0.015, x + 0.015, zc - 0.012, zc + 0.012, inn, out)  # perno
        box(x - 0.14, x + 0.015, zc - 0.012, zc + 0.012,
            out - s * 0.02, out)                                     # leva
        box(x - 0.012, x + 0.012, zc - 0.085, zc - 0.06, inn, rs)    # serratura


def _knob(hw, T, x, zc, sw) -> None:
    """Pomolo di un'anta a libro, sulla sola faccia anteriore."""
    _box(hw, T, x - 0.008, x + 0.008, sw / 2, sw / 2 + 0.02,
         zc - 0.008, zc + 0.008, METAL_COLOR)
    _box(hw, T, x - 0.018, x + 0.018, sw / 2 + 0.02, sw / 2 + 0.035,
         zc - 0.018, zc + 0.018, METAL_COLOR)


def _glass_leaf(model, leaf, glass, T, a0, a1, z0, z1, sw) -> None:
    """Anta piena con aperture vetrate (porta1, porta2)."""
    mg, bands = GLASS[model]
    wl, hl = a1 - a0, z1 - z0
    gx0, gx1 = a0 + mg * wl, a1 - mg * wl
    b0, b1 = -sw / 2, sw / 2
    _box(leaf, T, a0, gx0, b0, b1, z0, z1, LEAF_COLOR)
    _box(leaf, T, gx1, a1, b0, b1, z0, z1, LEAF_COLOR)
    cur = z0                                   # dal basso verso l'alto
    for top, bot in sorted(bands, key=lambda t: -t[1]):
        zb, zt = z1 - bot * hl, z1 - top * hl
        if zb > cur:
            _box(leaf, T, gx0, gx1, b0, b1, cur, zb, LEAF_COLOR)
        _box(glass, T, gx0, gx1, -sw * 0.15, sw * 0.15, zb, zt,
             GLASS_COLOR)
        cur = zt
    if cur < z1:
        _box(leaf, T, gx0, gx1, b0, b1, cur, z1, LEAF_COLOR)


def door_meshes(d: dict):
    """(mesh del telaio, mesh delle ante) dai parametri."""
    return door_meshes_all(d)[:2]


def door_meshes_all(d: dict):
    """(telaio, ante, vetri, ferramenta) dai parametri."""
    from core.mesh import Mesh
    err = validate(d)
    if err:
        raise ValueError(err)
    T = finestre._mapper(d)
    W, H, fw, fd, sw = d["W"], d["H"], d["fw"], d["fd"], d["sw"]
    n = int(d["leaves"])
    frame, leaf, glass, hw = Mesh(), Mesh(), Mesh(), Mesh()
    model = d.get("model", "porta")
    n = _panels(model, n)
    if model == "varco":
        # solo il foro: resta un bordo sottilissimo (1 cm) che tiene il gruppo
        # selezionabile e fa seguire il foro quando lo sposti
        fw = 0.01
        fb0, fb1 = -fd / 2, fd / 2
        _box(frame, T, 0, fw, fb0, fb1, 0, H, FRAME_COLOR)
        _box(frame, T, W - fw, W, fb0, fb1, 0, H, FRAME_COLOR)
        _box(frame, T, fw, W - fw, fb0, fb1, H - fw, H, FRAME_COLOR)
        return frame, leaf, glass, hw

    fb0, fb1 = -fd / 2, fd / 2
    _box(frame, T, 0, fw, fb0, fb1, 0, H, FRAME_COLOR)            # montante
    _box(frame, T, W - fw, W, fb0, fb1, 0, H, FRAME_COLOR)        # montante
    _box(frame, T, fw, W - fw, fb0, fb1, H - fw, H, FRAME_COLOR)  # traverso

    wl = (W - 2 * fw) / n
    gap = 0.003
    for i in range(n):
        a0 = fw + i * wl
        if model in GLASS:
            _glass_leaf(model, leaf, glass, T, a0 + gap, a0 + wl - gap,
                        gap, H - fw - gap, sw)
        else:
            _box(leaf, T, a0 + gap, a0 + wl - gap, -sw / 2, sw / 2,
                 gap, H - fw - gap, LEAF_COLOR)
    if model == "porta3":
        x0, x1 = fw + 0.18 * wl, W - fw - 0.18 * wl
        hl = H - fw - 2 * gap
        for fr in STRIPS:
            zz = H - fw - gap - fr * hl
            for s in (1, -1):
                lo = sw / 2 if s > 0 else -sw / 2 - 0.004
                _box(hw, T, x0, x1, lo, lo + 0.004, zz - 0.006, zz + 0.006,
                     METAL_COLOR)
    if model == "bifold":
        # one knob for each pair, in the middle of its leading panel: the
        # panel away from the jamb the pair pivots on
        lead = [1] if n == 2 else [1, 2]
        for i in lead:
            _knob(hw, T, fw + (i + 0.5) * wl, min(36 * IN, H * 0.47), sw)
        return frame, leaf, glass, hw
    if model == "garage1":
        _garage1(leaf, T, d)
        return frame, leaf, glass, hw
    if model == "garage2":
        _garage2(leaf, T, d)
        _handle(hw, T, W / 2, H * 0.47, sw)
    elif n == 2:
        _handle(hw, T, fw + wl - 0.05, min(1.0, H * 0.47), sw)
        _handle(hw, T, fw + wl + 0.05 + 0.0, min(1.0, H * 0.47), sw)
    else:
        _handle(hw, T, W - fw - 0.06, min(1.0, H * 0.47), sw)
    return frame, leaf, glass, hw


def _parts(d: dict, pose=None):
    frame, leaf, glass, hw = door_meshes_all(d)
    parts = [finestre._part(tr("Frame"), frame, pose)]
    if d.get("model", "porta") != "varco":
        parts.append(finestre._part(tr("Leaf"), leaf, pose))
    if d.get("model", "porta") in GLASS:
        parts.append(finestre._part(tr("Glass"), glass, pose))
    if d.get("model", "porta") not in ("garage1", "varco"):
        parts.append(finestre._part(tr("Handle"), hw, pose))
    return parts


def door_data(group):
    data = (getattr(group, "ext", None) or {}).get(KEY)
    return data if isinstance(data, dict) and "o" in data else None


def _next_name(scene) -> str:
    used = {g.name for g in scene.groups}
    n = 1
    while tr("Door {n}", n=n) in used:
        n += 1
    return tr("Door {n}", n=n)


def make_door(scene, p: dict, place: dict):
    from core.group import Group
    d = dict(p)
    d.update(o=list(place["o"]), u=list(place["u"]),
             flip=bool(place["flip"]))
    for k in ("lv", "lvn", "off"):
        if k in place:
            d[k] = place[k]
    parts = _parts(d)
    if not any(ly.name == LAYER_NAME for ly in scene.layers):
        from core.layers import Layer
        scene.layers.append(Layer(LAYER_NAME))
    name = _next_name(scene)
    g = Group(name=name)
    g.adopt(parts)
    g.component = False
    g.layer = LAYER_NAME
    bim.tag_group(g, "IfcDoor", name)
    g.ext = {KEY: d}
    scene.groups.append(g)
    return g


def rebuild_door(group, p: dict) -> None:
    """Nuove misure, stesso posto."""
    d = dict(door_data(group))
    d.update(p)
    pose = finestre._pose(group)
    group.children = _parts(d, pose)
    ext = dict(group.ext or {})
    ext[KEY] = d
    group.ext = ext


# ---------------------------------------------------------------------------
# Dialogo
# ---------------------------------------------------------------------------

def ask_params(parent, current: dict, title: str, ok_text: str,
               scene=None):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    form = QFormLayout()
    # the dialog works on the door itself; the frame is added around it
    dw, dh = door_size({"model": "porta", **current})
    W = spin(max(dw, 0.3), 0.3, 20.0)
    H = spin(max(dh, 0.5), 0.5, 20.0)
    for s in (W, H):
        s.setToolTip(tr(
            "Size of the door itself (the slab). The frame goes "
            "around it, outside this size, so the hole in the wall "
            "is wider by two frame widths and taller by one."))
    sill = spin(current["sill"], -10.0, 100.0)
    model = QComboBox()
    for key, label in MODELS:
        model.addItem(label, key)
    model.setCurrentIndex(
        max(0, model.findData(current.get("model", "porta"))))
    leaves = QComboBox()
    leaves.addItem(tr("1 leaf"), 1)
    leaves.addItem(tr("2 leaves"), 2)
    leaves.setCurrentIndex(leaves.findData(int(current["leaves"])))
    fw = spin(current["fw"], 0.01, 0.5)
    fd = spin(current["fd"], 0.02, 1.0)
    sw = spin(current["sw"], 0.01, 0.5)
    lvl = None
    if scene is not None and piani.levels(scene):
        lvl = piani.level_combo(scene, piani.active_id(scene))
        form.addRow(tr("Level (walls to place on)"), lvl)
    form.addRow(tr("Model"), model)
    form.addRow(tr("Door width (without frame)"), W)
    form.addRow(tr("Door height (without frame)"), H)
    form.addRow(tr("Height above floor"), sill)
    form.addRow(tr("Leaves"), leaves)
    form.addRow(tr("Frame: profile width"), fw)
    form.addRow(tr("Frame: depth"), fd)
    form.addRow(tr("Leaf thickness"), sw)
    total = QLabel()
    form.addRow(tr("With frame (hole in the wall)"), total)
    lay.addLayout(form)

    def whole():
        aw, ah = _around(model.currentData(), leaves.currentData(),
                         fw.value())
        return W.value() + aw, H.value() + ah

    def show_total(*_a) -> None:
        w, h = whole()
        total.setText(f"{fmt(w)} × {fmt(h)}")
    for s in (W, H, fw):
        s.valueChanged.connect(show_total)
    for c in (model, leaves):
        c.currentIndexChanged.connect(show_total)
    show_total()

    def on_model() -> None:
        key = model.currentData()
        garage = key.startswith("garage")
        bifold = key == "bifold"
        leaves.setItemText(0, tr("Single bi-fold (2 panels)") if bifold
                           else tr("1 leaf"))
        leaves.setItemText(1, tr("Dual bi-fold (4 panels)") if bifold
                           else tr("2 leaves"))
        if bifold:
            if started:                  # just chosen: a closet front
                leaves.setCurrentIndex(leaves.findData(2))
                sw.setValue(dflt(1.375 * IN, 0.035))
        elif key != "porta":
            leaves.setCurrentIndex(leaves.findData(1))
        if garage:
            if W.value() < 1.5:
                W.setValue(GARAGE_SIZE[0])
                H.setValue(GARAGE_SIZE[1])
        leaves.setEnabled(key in ("porta", "bifold"))
        sw.setEnabled(key != "varco")

    started = False
    model.currentIndexChanged.connect(on_model)
    on_model()
    started = True
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.button(QDialogButtonBox.Ok).setText(ok_text)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    if dlg.exec() != QDialog.Accepted:
        return None
    if lvl is not None:
        _Settings.level = lvl.currentData() or None
        piani.set_active(_Settings.level)
    tw, th = whole()
    return {"W": tw, "H": th, "sill": sill.value(),
            "leaves": leaves.currentData(), "fw": fw.value(),
            "fd": fd.value(), "sw": sw.value(),
            "model": model.currentData()}


# ---------------------------------------------------------------------------
# Strumento interattivo
# ---------------------------------------------------------------------------

class PortaTool(Tool):
    name = "Door"
    shortcut = None
    description = "Inserts parametric doors (1 or 2 leaves)."

    def __init__(self) -> None:
        self._entering = False
        self._vp = None
        self.hover: QVector3D | None = None

    def on_activate(self, viewport) -> None:
        if self._entering:
            self._vp = viewport
            self.hover = None
            viewport.flash_status(
                tr("Door: click to place it · "
                   "Space = anchor left / middle / right · "
                   "R = reverse (handle side) · "
                   "Esc / right-click = exit"), 6000)
            return
        p = ask_params(viewport.window(), _params(), tr("Door"), tr("Place"),
                       viewport.scene)
        if p is None:
            return
        err = validate(p)
        if err:
            viewport.flash_status(tr("Door: {error}", error=err), 5000)
            return
        _store(p)
        self._entering = True
        try:
            viewport.set_active_tool(self)
        finally:
            self._entering = False

    def on_deactivate(self, viewport) -> None:
        self.hover = None

    def _exit(self, viewport) -> None:
        self.hover = None
        viewport.update()
        back = getattr(viewport.window(), "activate_select_tool", None)
        if callable(back):
            back()

    def on_hover(self, ctx: ToolContext) -> None:
        self.hover = QVector3D(ctx.world)
        ctx.viewport.update()

    def on_cancel(self, viewport) -> None:
        self.hover = None
        viewport.update()

    def on_click(self, ctx: ToolContext) -> None:
        viewport = ctx.viewport
        scene = viewport.scene
        if getattr(scene, "edit_group", None) is not None:
            viewport.flash_status(
                tr("Close the group you are editing, then place the door"),
                4000)
            return
        world = QVector3D(ctx.world)
        self.hover = world
        p = _params()
        place = finestre.anchored(
            finestre.placement(scene, world, _Settings.flip, _Settings.level),
            p["W"], _Settings.anchor)

        def mutate(sc):
            make_door(sc, p, place)
            finestre.update_openings(sc)

        hist = viewport.history
        hist.execute(FinestraCommand(mutate))
        if getattr(hist, "last_error", None):
            viewport.flash_status(
                tr("Door: {error}",
                   error=str(hist.last_error).split(": ", 1)[-1]), 6000)
            return
        viewport.notify_scene_changed()
        viewport.flash_status(tr("Door created"), 2500)
        viewport.update()

    def context_menu(self, viewport, pos) -> bool:
        self._exit(viewport)
        return True

    def _buffer(self) -> str:
        return getattr(self._vp, "_value_buffer", "") or ""

    def claims_key(self, key: int, modifiers) -> bool:
        if modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        if self._buffer():
            return False
        return key in (Qt.Key_Space, Qt.Key_Escape, Qt.Key_R)

    def on_key(self, viewport, key: int, modifiers) -> bool:
        if key == Qt.Key_Escape:
            self._exit(viewport)
            return True
        if key == Qt.Key_Space:
            _Settings.anchor = finestre.next_anchor(_Settings.anchor)
            viewport.flash_status(
                finestre.anchor_text(_Settings.anchor), 2000)
            viewport.update()
            return True
        if key == Qt.Key_R:
            _Settings.flip = not _Settings.flip
            viewport.flash_status(
                tr("Door reversed: handle on the other side"), 2000)
            viewport.update()
            return True
        return False

    def status_clause(self) -> str:
        return tr("{anchor} (Space) · R = reverse · "
                  "Esc / right-click = exit",
                  anchor=finestre.anchor_text(_Settings.anchor))

    def rubber_band_lines(self):
        if self.hover is None:
            return []
        scene = self._vp.scene if self._vp is not None else None
        if scene is None:
            return []
        d = _params()
        d.update(finestre.anchored(
            finestre.placement(scene, self.hover, _Settings.flip,
                               _Settings.level), d["W"], _Settings.anchor))
        return finestre.outline_lines(d)

    def draw_overlay(self, viewport, painter) -> None:
        try:
            self._draw(viewport, painter)
        except Exception:
            pass

    def _draw(self, viewport, painter) -> None:
        painter.save()
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        fm = painter.fontMetrics()
        p = _params()
        w, h = (fmt(v) for v in door_size(p))
        anchor = finestre.anchor_caps(_Settings.anchor)
        lines = [
            tr("Door {w} × {h} · 1 leaf", w=w, h=h) if p["leaves"] == 1
            else tr("Door {w} × {h} · {n} leaves", w=w, h=h,
                    n=int(p["leaves"])),
            tr("Above floor: {sill} · frame {fw} × {fd}",
               sill=fmt(p["sill"]), fw=fmt(p["fw"]), fd=fmt(p["fd"])),
            tr("{anchor} (Space changes)  ·  REVERSED (R)", anchor=anchor)
            if _Settings.flip
            else tr("{anchor} (Space changes)  ·  not reversed (R)",
                    anchor=anchor),
            tr("Esc / right-click = exit"),
        ]
        w = max(fm.horizontalAdvance(t) for t in lines) + 16
        h = fm.height() * len(lines) + 12
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 30, 30, 200))
        painter.drawRoundedRect(QRectF(12, 44, w, h), 6, 6)
        painter.setPen(QPen(QColor(255, 255, 255)))
        for i, t in enumerate(lines):
            painter.drawText(QPointF(20, 44 + 6 + fm.ascent() + i * fm.height()), t)
        painter.restore()


# ---------------------------------------------------------------------------
# Modifica di una porta già posata
# ---------------------------------------------------------------------------

def _selected_doors(scene):
    out = []
    for e in scene.selection:
        g = getattr(e, "owner", None) or e
        if g in scene.groups and door_data(g) is not None and g not in out:
            out.append(g)
    return out


def edit_doors(viewport, doors=None) -> None:
    scene = viewport.scene
    if getattr(scene, "edit_group", None) is not None:
        viewport.flash_status(tr("Close the group you are editing"), 4000)
        return
    doors = doors or _selected_doors(scene)
    if not doors:
        viewport.flash_status(
            tr("Select a door created with the Door tool"), 4000)
        return
    d = door_data(doors[0])
    current = {k: d[k] for k in ("W", "H", "sill", "leaves", "fw", "fd", "sw")}
    current["model"] = d.get("model", "porta")
    title = tr("Edit door") if len(doors) == 1 \
        else tr("Edit {n} doors", n=len(doors))
    p = ask_params(viewport.window(), current, title, tr("Apply"))
    if p is None:
        return
    err = validate(p)
    if err:
        viewport.flash_status(tr("Door: {error}", error=err), 5000)
        return

    def mutate(sc):
        for g in doors:
            rebuild_door(g, p)
        finestre.update_openings(sc)

    hist = viewport.history
    hist.execute(FinestraCommand(mutate))
    if getattr(hist, "last_error", None):
        viewport.flash_status(
            tr("Door: {error}",
               error=str(hist.last_error).split(": ", 1)[-1]), 6000)
        return
    viewport.notify_scene_changed()
    viewport.update()
    viewport.flash_status(tr("{n} doors updated", n=len(doors)), 3000)


def reversed_place(d: dict) -> dict:
    """The same door in the same hole, turned end for end: the handle (and
    the hinge) change side. Flipping turns the door about its corner, so the
    corner moves to the other end of the unit."""
    (ux, uy), _n = finestre._axes(d)
    ox, oy, oz = d["o"]
    return {"o": [ox + ux * d["W"], oy + uy * d["W"], oz],
            "flip": not d.get("flip")}


def reverse_doors(viewport, doors=None) -> None:
    scene = viewport.scene
    if getattr(scene, "edit_group", None) is not None:
        viewport.flash_status(tr("Close the group you are editing"), 4000)
        return
    doors = doors or _selected_doors(scene)
    if not doors:
        viewport.flash_status(
            tr("Select a door created with the Door tool"), 4000)
        return

    def mutate(sc):
        for g in doors:
            rebuild_door(g, reversed_place(door_data(g)))
        finestre.update_openings(sc)

    hist = viewport.history
    hist.execute(FinestraCommand(mutate))
    if getattr(hist, "last_error", None):
        viewport.flash_status(
            tr("Door: {error}",
               error=str(hist.last_error).split(": ", 1)[-1]), 6000)
        return
    viewport.notify_scene_changed()
    viewport.update()
    viewport.flash_status(
        tr("Door reversed: handle on the other side"), 3000)


def _hook_double_click(vp) -> None:
    """Doppio clic su una porta = modifica le misure."""
    if getattr(vp, "_myhouse_porte_dbl", False):
        return
    original = vp.begin_group_edit

    def begin_group_edit(group, *args, **kwargs):
        g = getattr(group, "owner", None) or group
        if door_data(g) is None:
            return original(group, *args, **kwargs)
        from PySide6.QtCore import QTimer
        scene = vp.scene
        try:
            scene.select([g])
        except Exception:
            scene.selection.clear()
            scene.selection.add(g)
        vp.update()
        QTimer.singleShot(0, lambda: edit_doors(vp, [g]))

    vp.begin_group_edit = begin_group_edit
    vp._myhouse_porte_dbl = True


def _outliner_kind(group):
    d = door_data(group)
    if d is None:
        return None
    names = dict(MODELS)
    return {"type": tr("Door"),
            "props": [(tr("Model"),
                       names.get(d.get("model", "porta"), tr("Door"))),
                      (tr("Door width"), fmt(door_size(d)[0])),
                      (tr("Door height"), fmt(door_size(d)[1])),
                      (tr("With frame"), f"{fmt(d['W'])} × {fmt(d['H'])}"),
                      (tr("Above floor"), fmt(d["sill"])),
                      (tr("Leaves"), tr("{n} bi-fold panels", n=_panels(
                          d.get("model", "porta"), d["leaves"]))
                       if d.get("model") == "bifold"
                       else str(int(d["leaves"])))]
            + piani.level_props(d)}


# ---------------------------------------------------------------------------
# Registrazione sulla barra MyHouse
# ---------------------------------------------------------------------------

def _icon():
    from PySide6.QtGui import QIcon, QPainter, QPixmap
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(60, 60, 60), 2))
    p.setBrush(QColor(170, 125, 85))
    p.drawRect(13, 6, 22, 36)
    p.setBrush(QColor(240, 220, 120))
    p.drawEllipse(28, 23, 4, 4)
    p.end()
    return QIcon(pm)


def _register_level_kind() -> None:
    def zset(d, z):
        o = list(d["o"])
        o[2] = z
        d["o"] = o

    piani.register_kind("porta", KEY, door_data, lambda d: d["o"][2],
                        zset, rebuild_door)


def register(api) -> None:
    _register_level_kind()
    api.add_button(tr("Door"), tr("Inserts a door (1 or 2 leaves)"),
                   _icon(), api.run_tool(PortaTool()))

    app = api.app
    _hook_double_click(api.window.viewport)
    add_ctx = getattr(app, "add_context_menu", None)
    if add_ctx is not None:
        from PySide6.QtCore import QTimer

        def context(menu, selection) -> None:
            if not _selected_doors(app.viewport.scene):
                return
            menu.addSeparator()
            menu.addAction(
                tr("Edit door…"),
                lambda: QTimer.singleShot(
                    0, lambda: edit_doors(app.viewport)))
            menu.addAction(
                tr("Reverse door (handle on the other side)"),
                lambda: QTimer.singleShot(
                    0, lambda: reverse_doors(app.viewport)))

        add_ctx(context)
    add_kind = getattr(app, "add_outliner_kind", None)
    if add_kind is not None:
        add_kind(_outliner_kind)
