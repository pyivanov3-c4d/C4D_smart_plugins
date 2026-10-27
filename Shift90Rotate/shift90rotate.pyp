"""Drag an axis ring to rotate the selected object exactly 90 degrees.

Cinema 4D 2026 Python ToolData plugin. The ID below is for local use; obtain a
registered ID from Maxon PluginCafe before distributing this plugin publicly.
"""

import math
import os
import traceback

import c4d
from c4d import bitmaps, plugins, utils


PLUGIN_ID = 1069987
RING_PIXELS = 86.0
HIT_PIXELS = 11.0
DRAG_PIXELS = 12.0
SEGMENTS = 96

AXES = (
    ("X", c4d.Vector(1, 0, 0), c4d.Vector(0, 1, 0), c4d.Vector(0, 0, 1), c4d.Vector(1.0, 0.25, 0.25)),
    ("Y", c4d.Vector(0, 1, 0), c4d.Vector(0, 0, 1), c4d.Vector(1, 0, 0), c4d.Vector(0.25, 0.9, 0.35)),
    ("Z", c4d.Vector(0, 0, 1), c4d.Vector(1, 0, 0), c4d.Vector(0, 1, 0), c4d.Vector(0.3, 0.55, 1.0)),
)


def _unit(v):
    length = v.GetLength()
    return v / length if length > 1e-10 else None


def _axis_frame(doc, op):
    mg = op.GetMg()
    # Follow Cinema 4D's native World/Object coordinate toggle.
    if doc[c4d.DOCUMENT_STATEW]:
        return mg.off, tuple(entry[1] for entry in AXES)
    basis = (mg.v1, mg.v2, mg.v3)
    return mg.off, tuple(_unit(v) for v in basis)


def _rings(doc, bd, op):
    center, basis = _axis_frame(doc, op)
    if any(v is None for v in basis):
        return []
    depth = bd.WS(center).z
    radius = abs(bd.PW_S(depth, True)) * RING_PIXELS
    if radius <= 1e-7:
        return []
    rings = []
    for name, _axis, _u, _v, color in AXES:
        index = {"X": (0, 1, 2), "Y": (1, 2, 0), "Z": (2, 0, 1)}[name]
        axis, u, v = (basis[i] for i in index)
        world = []
        screen = []
        for step in range(SEGMENTS + 1):
            angle = 2.0 * math.pi * step / SEGMENTS
            point = center + (u * math.cos(angle) + v * math.sin(angle)) * radius
            pixel = bd.WS(point)
            world.append(point)
            screen.append((pixel.x, pixel.y))
        rings.append((name, axis, color, world, screen))
    return rings


def _nearest_segment(px, py, rings):
    winner = None
    for name, axis, _color, _world, screen in rings:
        for i in range(SEGMENTS):
            ax, ay = screen[i]
            bx, by = screen[i + 1]
            vx, vy = bx - ax, by - ay
            length_sq = vx * vx + vy * vy
            if length_sq < 1e-6:
                continue
            t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / length_sq))
            distance_sq = (px - ax - t * vx) ** 2 + (py - ay - t * vy) ** 2
            if winner is None or distance_sq < winner[0]:
                winner = (distance_sq, name, axis, (vx, vy))
    return winner if winner is not None and winner[0] <= HIT_PIXELS ** 2 else None


def _selected_roots(doc):
    selected = doc.GetActiveObjects(0)
    roots = []
    for op in selected:
        parent = op.GetUp()
        while parent is not None and parent not in selected:
            parent = parent.GetUp()
        if parent is None:
            roots.append(op)
    return roots


class Rotate90(plugins.ToolData):
    _drag_axis = None
    _hover_axis = None
    _hover_view = None
    _hover_object = None

    def _redraw(self):
        c4d.DrawViews(c4d.DRAWFLAGS_ONLY_ACTIVE_VIEW
                      | c4d.DRAWFLAGS_NO_THREAD
                      | c4d.DRAWFLAGS_NO_ANIMATION)

    def Draw(self, doc, data, bd, bh, bt, flags):
        op = doc.GetActiveObject()
        if op is None:
            return c4d.TOOLDRAW_NONE
        rings = _rings(doc, bd, op)
        bd.SetMatrix_Matrix(None, c4d.Matrix())
        highlight = self._drag_axis
        if highlight is None and self._hover_view == bd and self._hover_object == op:
            highlight = self._hover_axis
        for _name, _axis, color, points, _screen in rings:
            bd.SetPen(c4d.Vector(1.0, 1.0, 0.0)
                      if _name == highlight else color)
            for i in range(SEGMENTS):
                bd.DrawLine(points[i], points[i + 1], 0)
        return c4d.TOOLDRAW_NONE

    def MouseInput(self, doc, data, bd, win, msg):
        if msg[c4d.BFM_INPUT_CHANNEL] != c4d.BFM_INPUT_MOUSELEFT:
            return False
        op = doc.GetActiveObject()
        if op is None:
            return False
        start_x = float(msg[c4d.BFM_INPUT_X])
        start_y = float(msg[c4d.BFM_INPUT_Y])
        hit = _nearest_segment(start_x, start_y, _rings(doc, bd, op))
        if hit is None:
            return False

        _distance_sq, _name, axis, tangent = hit
        win.MouseDragStart(c4d.KEY_MLEFT, start_x, start_y,
                           c4d.MOUSEDRAGFLAGS_DONTHIDEMOUSE)
        dx_total = 0.0
        dy_total = 0.0
        self._drag_axis = _name
        try:
            self._redraw()
            while True:
                result, dx, dy, _channels = win.MouseDrag()
                if result != c4d.MOUSEDRAGRESULT_CONTINUE:
                    break
                dx_total += dx
                dy_total += dy
                self._redraw()
        finally:
            try:
                end_result = win.MouseDragEnd()
            finally:
                self._drag_axis = None
                self._hover_axis = None
                self._hover_view = None
                self._hover_object = None
                self._redraw()
        if end_result == c4d.MOUSEDRAGRESULT_ESCAPE:
            return True
        if math.hypot(dx_total, dy_total) < DRAG_PIXELS:
            return True

        along = dx_total * tangent[0] + dy_total * tangent[1]
        if abs(along) < 1e-5:
            return True
        angle = -math.pi / 2.0 if along > 0 else math.pi / 2.0
        rotation = utils.RotAxisToMatrix(axis, angle)
        roots = _selected_roots(doc)
        if not roots:
            return True

        doc.StartUndo()
        try:
            for target in roots:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, target)
                original = target.GetMg()
                pivot = original.off
                # Matrix multiplication applies the world-space quarter turn.
                turned = rotation * original
                turned.off = pivot
                target.SetMg(turned)
                target.Message(c4d.MSG_UPDATE)
        finally:
            doc.EndUndo()
        c4d.EventAdd()
        return True

    def GetCursorInfo(self, doc, data, bd, x, y, bc):
        # Lock the highlight to the captured ring throughout a mouse drag.
        if self._drag_axis is not None:
            return True
        op = doc.GetActiveObject()
        hit = None
        if (bc.GetId() != c4d.BFM_CURSORINFO_REMOVE
                and op is not None and x >= 0 and y >= 0):
            hit = _nearest_segment(x, y, _rings(doc, bd, op))
        axis = hit[1] if hit is not None else None
        view = bd if axis is not None else None
        target = op if axis is not None else None
        changed = (axis != self._hover_axis or view != self._hover_view
                   or target != self._hover_object)
        self._hover_axis = axis
        self._hover_view = view
        self._hover_object = target
        if hit is not None:
            bc[c4d.RESULT_BUBBLEHELP_TITLE] = "90° Rotate"
            bc[c4d.RESULT_BUBBLEHELP] = "Drag the %s ring: exactly 90°" % axis
        if changed:
            self._redraw()
        return True


if __name__ == "__main__":
    try:
        icon = bitmaps.BaseBitmap()
        icon_path = os.path.join(os.path.dirname(__file__), "res", "icon.png")
        if icon.InitWith(icon_path)[0] != c4d.IMAGERESULT_OK:
            print("Rotate90: could not load icon: " + icon_path)
            icon = None
        registered = plugins.RegisterToolPlugin(
            PLUGIN_ID,
            "90° Rotate",
            0,
            icon,
            "Drag an X, Y or Z ring to turn selected objects 90 degrees.",
            Rotate90(),
        )
        if not registered:
            raise RuntimeError("Rotate90: tool registration failed (plugin ID conflict?).")
    except BaseException:
        log_path = os.path.join(os.path.dirname(__file__), "registration_error.log")
        with open(log_path, "w", encoding="utf-8") as log:
            log.write(traceback.format_exc())
        raise
