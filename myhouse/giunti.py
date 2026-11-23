# SPDX-License-Identifier: GPL-3.0-or-later
"""Split wall and Wall joint, for MyHouse.

Split wall: click a point on a wall and it becomes two walls that meet
there. Both stay in the same run, so the outer ends keep their corners.

Wall joint: click a wall near a corner to change how the two walls meet.
Each click moves to the next of three joints:
    mitre (as drawn)  ->  the clicked wall runs through, the other butts
    against it  ->  the other wall runs through  ->  mitre again
Only walls of the same run meet in a corner; walls drawn separately already
end square.

Both: Esc / right-click leaves the command, each change is one undo step.
"""
from __future__ import annotations

import copy
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QVector3D

from core import bim
from tools.base import Tool, ToolContext

from . import finestre, muri
from ._i18n import tr
from ._imperial import fmt
from .allunga import MIN_LEN, _pose_key, _same, wall_group

ORDER = 13                       # after Walls, Adopt wall and Stretch wall
JOINTS = {None: tr("mitred"), "through": tr("runs through"),
          "butt": tr("butts")}


def _set_data(group, d: dict) -> None:
    ext = dict(group.ext or {})
    ext[muri.KEY] = d
    group.ext = ext


def _mates(scene, group):
    """The other walls of the same run that sit in the same place."""
    d = muri.wall_data(group)
    chain = d.get("chain")
    if not chain:
        return []
    key = _pose_key(group)
    return [g for g in scene.groups
            if g is not group and (muri.wall_data(g) or {}).get("chain")
            == chain and _pose_key(g) == key]


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------

def split(scene, group, s: float):
    """Cuts the wall in two at the distance s from its start. The group
    keeps the first half; returns the new group, the second half."""
    from core.group import Group
    d = muri.wall_data(group)
    if d is None:
        raise ValueError(tr("this is not a MyHouse wall"))
    (ax, ay), (bx, by) = d["a"], d["b"]
    L = math.hypot(bx - ax, by - ay)
    if s < MIN_LEN or s > L - MIN_LEN:
        raise ValueError(tr("the cut is at the end of the wall"))
    a, b = [ax, ay], [bx, by]
    p = [ax + (bx - ax) * s / L, ay + (by - ay) * s / L]
    mates = _mates(scene, group)
    if not d.get("chain"):                 # the halves must mitre together
        from core.group import new_uid
        d = dict(d, chain=new_uid(), nth=d["th"])
    d1, d2 = copy.deepcopy(d), copy.deepcopy(d)
    d1.update(b=list(p), next=list(b))
    d1.pop("jb", None)
    d2.update(a=list(p), prev=list(a))
    d2.pop("ja", None)
    pose = muri.wall_pose(group)
    part2 = muri.wall_part(d2, pose)       # raises before anything changes
    group.children = [muri.wall_part(d1, pose)]
    _set_data(group, d1)

    used = {g.name for g in scene.groups}
    name, k = f"{group.name}b", 2
    while name in used:
        name, k = f"{group.name}b{k}", k + 1
    g2 = Group(name=name)
    g2.adopt([part2])
    g2.component = False
    g2.layer = getattr(group, "layer", muri.LAYER_NAME)
    g2.material = dict(group.material) if group.material else None
    g2.hidden, g2.locked = group.hidden, group.locked
    g2.xform = group.xform
    bim.tag_group(g2, "IfcWall", name)
    ext = copy.deepcopy(dict(group.ext or {}))
    ext[muri.KEY] = d2
    g2.ext = ext
    scene.groups.insert(scene.groups.index(group) + 1, g2)

    for g in mates:                        # the neighbours now see the cut
        w = muri.wall_data(g)
        new = dict(w)
        if _same(w.get("prev"), a) and _same(w["a"], b):
            new["prev"] = list(p)
        if _same(w.get("next"), b) and _same(w["b"], a):
            new["next"] = list(p)
        if new != w:
            _set_data(g, new)
    muri.update_roof_clips(scene)
    finestre.update_openings(scene)
    return g2


# ---------------------------------------------------------------------------
# Joint
# ---------------------------------------------------------------------------

def joint_partner(scene, group, end: str):
    """(group, end) of the wall that meets this end in a corner, or None."""
    d = muri.wall_data(group)
    if d is None or not d.get("prev" if end == "a" else "next"):
        return None
    P = d[end]
    for g in _mates(scene, group):
        w = muri.wall_data(g)
        for e, far in (("a", "prev"), ("b", "next")):
            if _same(w[e], P) and w.get(far):
                return g, e
    return None


def joint_kind(group, end: str):
    return (muri.wall_data(group) or {}).get("j" + end)


def set_joint(scene, group, end: str, kind) -> None:
    """kind: "through" = this wall runs through and the other butts against
    it; "butt" = the other way round; None = mitre."""
    if kind not in JOINTS:
        raise ValueError(tr("unknown joint"))
    mate = joint_partner(scene, group, end)
    if mate is None:
        raise ValueError(tr("this end does not meet another wall of the "
                            "same run in a corner"))
    other = {"through": "butt", "butt": "through", None: None}[kind]
    for g, e, k in ((group, end, kind), (mate[0], mate[1], other)):
        w = muri.wall_data(g)
        muri.rebuild_wall(g, w["th"], w["h"], {"j" + e: k})
    muri.update_roof_clips(scene)
    finestre.update_openings(scene)


def next_joint(group, end: str):
    return {None: "through", "through": "butt", "butt": None}[
        joint_kind(group, end)]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class _WallClickTool(Tool):
    """A tool that acts on the wall under each click and stays active."""
    shortcut = None
    label = ""                # the tool's name, translated
    prompt = ""

    def __init__(self) -> None:
        self._entering = False
        self._vp = None
        self.marks = []

    def _buffer(self) -> str:
        return getattr(self._vp, "_value_buffer", "") or ""

    def on_activate(self, viewport) -> None:
        if self._entering:
            self._vp = viewport
            self.marks = []
            viewport.flash_status(
                tr("{tool}: {message}", tool=self.label,
                   message=self.prompt), 6000)
            return
        self._entering = True
        try:
            viewport.set_active_tool(self)
        finally:
            self._entering = False

    def on_deactivate(self, viewport) -> None:
        self.marks = []

    def on_cancel(self, viewport) -> None:
        self.marks = []
        viewport.update()

    def claims_key(self, key: int, modifiers) -> bool:
        if modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        return key == Qt.Key_Escape and not self._buffer()

    def _exit(self, viewport) -> None:
        self.marks = []
        viewport.update()
        back = getattr(viewport.window(), "activate_select_tool", None)
        if callable(back):
            back()

    def on_key(self, viewport, key: int, modifiers) -> bool:
        if key == Qt.Key_Escape:
            self._exit(viewport)
            return True
        return False

    def context_menu(self, viewport, pos) -> bool:
        self._exit(viewport)
        return True

    def status_clause(self) -> str:
        return tr("{prompt} · Esc = exit", prompt=self.prompt)

    def rubber_band_lines(self):
        return list(self.marks)

    @staticmethod
    def _axis(group):
        """(A, B) of the wall's drawn line, in world coordinates."""
        d = muri.wall_data(group)
        pose = finestre._full_pose(group)
        return (pose.map(QVector3D(d["a"][0], d["a"][1], d["z0"])),
                pose.map(QVector3D(d["b"][0], d["b"][1], d["z0"])))

    def _run(self, viewport, mutate) -> bool:
        scene = viewport.scene
        if getattr(scene, "edit_group", None) is not None:
            viewport.flash_status(tr("Close the group you are editing"), 4000)
            return False
        hist = viewport.history
        hist.execute(muri.MuriCommand(mutate))
        if getattr(hist, "last_error", None):
            viewport.flash_status(
                tr("{tool}: {message}", tool=self.label,
                   message=str(hist.last_error).split(": ", 1)[-1]), 6000)
            return False
        self.marks = []
        viewport.notify_scene_changed()
        viewport.update()
        return True


class SplitTool(_WallClickTool):
    name = "Split wall"
    description = "Cuts a MyHouse wall in two at the point you click."
    label = tr("Split wall")
    prompt = tr("click the point on a wall where to cut it")

    def _where(self, scene, world):
        hit = wall_group(scene, world)
        if hit is None:
            return None
        g = hit[0]
        A, B = self._axis(g)
        run = B - A
        L = run.length()
        if L < 1e-9:
            return None
        u = run / L
        s = QVector3D.dotProduct(world - A, u)
        return g, s, L, A, u

    def on_hover(self, ctx: ToolContext) -> None:
        self.marks = []
        hit = self._where(ctx.viewport.scene, QVector3D(ctx.world))
        if hit is not None:
            g, s, L, A, u = hit
            if MIN_LEN < s < L - MIN_LEN:
                d = muri.wall_data(g)
                p = A + u * s
                n = QVector3D(-u.y(), u.x(), 0.0)
                dl, dr = muri.side_offsets(d["th"], d["align"])
                self.marks = [(p + n * (dl + 0.05), p - n * (dr + 0.05))]
        ctx.viewport.update()

    def on_click(self, ctx: ToolContext) -> None:
        viewport = ctx.viewport
        hit = self._where(viewport.scene, QVector3D(ctx.world))
        if hit is None:
            viewport.flash_status(
                tr("Click a wall made with the Walls tool (or adopted)"),
                4000)
            return
        g, s, L, _A, _u = hit
        if self._run(viewport, lambda sc: split(sc, g, s)):
            viewport.flash_status(
                tr("Wall cut in two: {a} and {b} · "
                   "click another wall, or Esc", a=fmt(s), b=fmt(L - s)),
                5000)


class JointTool(_WallClickTool):
    name = "Wall joint"
    description = ("Changes a corner between mitre and butt joint: the wall "
                   "you click runs through, click again for the other way.")
    label = tr("Wall joint")
    prompt = tr("click a wall near a corner: it runs through, the other "
                "butts against it (click again: the other way, then mitre)")

    def on_hover(self, ctx: ToolContext) -> None:
        self.marks = []
        hit = wall_group(ctx.viewport.scene, QVector3D(ctx.world))
        if hit is not None and joint_partner(ctx.viewport.scene, *hit):
            g, end = hit
            A, B = self._axis(g)
            P, far = (A, B) if end == "a" else (B, A)
            run = far - P
            if run.length() > 1e-9:
                u = run.normalized()
                n = QVector3D(-u.y(), u.x(), 0.0) * 0.25
                self.marks = [(P, P + u * min(0.6, run.length())),
                              (P - n, P + n)]
        ctx.viewport.update()

    def on_click(self, ctx: ToolContext) -> None:
        viewport = ctx.viewport
        scene = viewport.scene
        hit = wall_group(scene, QVector3D(ctx.world))
        if hit is None:
            viewport.flash_status(
                tr("Click a wall made with the Walls tool, near a corner"),
                4000)
            return
        g, end = hit
        if joint_partner(scene, g, end) is None:
            viewport.flash_status(
                tr("Wall joint: this end does not meet another wall of the "
                   "same run in a corner (walls drawn separately already "
                   "end square)"), 6000)
            return
        kind = next_joint(g, end)
        if self._run(viewport, lambda sc: set_joint(sc, g, end, kind)):
            if kind == "through":
                msg = tr("Butt joint: {name} runs through · "
                         "click again to change", name=g.name)
            elif kind == "butt":
                msg = tr("Butt joint: {name} butts against the other wall · "
                         "click again to change", name=g.name)
            else:
                msg = tr("Mitred corner · click again to change")
            viewport.flash_status(msg, 5000)


def _icon(kind: str):
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(60, 60, 60), 1.5))
    p.setBrush(QColor(200, 170, 130))
    if kind == "split":
        p.drawRect(QRectF(2, 12, 12, 8))
        p.drawRect(QRectF(18, 12, 12, 8))
        p.setPen(QPen(QColor(30, 110, 200), 2.2))
        p.drawLine(QPointF(16, 6), QPointF(16, 26))
    else:                                   # an L corner with a butt joint
        p.drawRect(QRectF(4, 4, 8, 24))
        p.drawRect(QRectF(12, 20, 16, 8))
        p.setPen(QPen(QColor(30, 110, 200), 2.2))
        p.drawLine(QPointF(12, 18), QPointF(12, 30))
    p.end()
    return QIcon(pm)


def register(api) -> None:
    split_start = api.run_tool(SplitTool())
    joint_start = api.run_tool(JointTool())
    api.add_button(tr("Split wall"),
                   tr("Cut a wall in two: click the point on the wall"),
                   _icon("split"), split_start)
    api.add_button(tr("Wall joint"),
                   tr("Butt or mitre a corner: click the wall that runs "
                      "through; click again for the other way, then mitre"),
                   _icon("joint"), joint_start)
    app = api.app
    add_ctx = getattr(app, "add_context_menu", None)
    if add_ctx is not None:
        from PySide6.QtCore import QTimer

        def context(menu, selection) -> None:
            if not muri._selected_walls(app.viewport.scene):
                return
            menu.addAction(tr("Split wall…"),
                           lambda: QTimer.singleShot(0, split_start))
            menu.addAction(tr("Wall joint (butt / mitre)…"),
                           lambda: QTimer.singleShot(0, joint_start))

        add_ctx(context)
