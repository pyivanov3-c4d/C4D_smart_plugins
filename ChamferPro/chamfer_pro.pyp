"""chamferPro - non-destructive, constant-radius spline fillets for C4D."""
import math
import os
import sys
import threading
import traceback
import c4d
from c4d import plugins, bitmaps, utils

ROOT = os.path.dirname(__file__)
if ROOT not in sys.path: sys.path.insert(0, ROOT)
import chamfer_geometry as geo

PLUGIN_ID = 1069990  # Local installation ID; register before redistribution.
ANGLE, RADIUS, STATUS = 11000, 11001, 11002
MAX_CURVES = 100000
VERSION = '1.1.3'


def xyz(v): return (v.x, v.y, v.z)
def vector(p): return c4d.Vector(*p)


def read_spline(spline, matrix, check=None):
    """Preserve cubic handles; other interpolation types use evaluated lines."""
    if spline.CheckType(c4d.Oline):
        tag = spline.GetTag(c4d.Tsegment)
        segments = tag.GetAllHighlevelData() if tag else []
        bezier = False
        global_closed = None
    else:
        if spline.GetInterpolationType() not in (c4d.SPLINETYPE_LINEAR, c4d.SPLINETYPE_BEZIER):
            helper = utils.SplineHelp()
            if not helper.InitSplineWith(spline, c4d.SPLINEHELPFLAGS_RETAINLINEOBJECT):
                raise ValueError('Could not evaluate spline interpolation.')
            return read_spline(helper.GetLineObject(), matrix, check)
        segments = [spline.GetSegment(i) for i in range(spline.GetSegmentCount())]
        bezier = spline.GetInterpolationType() == c4d.SPLINETYPE_BEZIER
        global_closed = spline.IsClosed()
    points = spline.GetAllPoints()
    if not segments:
        segments = [{'cnt': len(points), 'closed': bool(spline[c4d.SPLINEOBJECT_CLOSED])}]
    paths, start = [], 0
    for segment in segments:
        count = segment['cnt']
        closed = bool(segment['closed']) if global_closed is None else bool(global_closed)
        curves = []
        for k in range(count if closed else count-1):
            if check: check()
            i, j = start+k, start+(k+1) % count
            a, b = xyz(matrix*points[i]), xyz(matrix*points[j])
            if bezier:
                ti, tj = spline.GetTangent(i), spline.GetTangent(j)
                # C4D stores 3/4 of the conventional cubic Bezier handle.
                curve = (a, xyz(matrix*(points[i]+ti['vr']*(4./3.))),
                         xyz(matrix*(points[j]+tj['vl']*(4./3.))), b)
            else: curve = geo.line(a, b)
            if any(geo.length(geo.sub(p, a)) > 1e-10 for p in curve[1:]):
                curves.append(curve)
        if curves: paths.append((curves, closed))
        start += count
    return paths


def collect(node, parent_matrix, paths, check=None, ancestors=(), groups=None):
    """Read evaluated contours; never run modeling commands in a generator.

GetRealSpline is only queried on spline generators (Text, Rectangle, etc.),
not on generic cache containers. A cache must not lead back to its owner.
"""
    while node:
        if check: check()
        if any(node == ancestor for ancestor in ancestors):
            raise ValueError('Cyclic child/cache dependency')
        lineage = ancestors+(node,)
        matrix = parent_matrix*node.GetMl()
        deform = node.GetDeformCache()
        if deform is not None:
            collect(deform, matrix, paths, check, lineage, groups)
        elif node.CheckType(c4d.Ospline) or node.CheckType(c4d.Oline):
            source = read_spline(node, matrix, check)
            paths.extend(source)
            if groups is not None and source: groups.append(source)
        else:
            spline = node.GetRealSpline() if node.GetInfo() & c4d.OBJECT_ISSPLINE else None
            if spline is not None:
                source = read_spline(spline, matrix, check)
                paths.extend(source)
                if groups is not None and source: groups.append(source)
            elif node.GetCache() is not None:
                collect(node.GetCache(), matrix, paths, check, lineage, groups)
            elif node.GetDown() is not None:
                collect(node.GetDown(), matrix, paths, check, lineage, groups)
        node = node.GetNext()


def make_spline(paths):
    points, tangents, segments = [], [], []
    zero = (0., 0., 0.)
    # C4D applies its Closed switch to the entire SplineObject, regardless
    # of the per-segment flags. Mixed inputs use explicit endpoint closure.
    all_closed = bool(paths) and all(closed for curves, closed in paths if curves)
    for curves, closed in paths:
        if not curves: continue
        start = len(points)
        for i, curve in enumerate(curves):
            points.append(vector(curve[0]))
            incoming = geo.sub(curves[i-1][2], curve[0]) if i or closed else zero
            tangents.append((vector(incoming), vector(geo.sub(curve[1], curve[0]))))
        if not closed or not all_closed:
            points.append(vector(curves[-1][3]))
            tangents.append((vector(geo.sub(curves[-1][2], curves[-1][3])), vector(zero)))
        segments.append((len(points)-start, all_closed))
    result = c4d.SplineObject(len(points), c4d.SPLINETYPE_BEZIER)
    if points:
        result.ResizeObject(len(points), len(segments))
        result.SetAllPoints(points)
        for i, (left, right) in enumerate(tangents):
            result.SetTangent(i, left*.75, right*.75)
        for i, (count, closed) in enumerate(segments): result.SetSegment(i, count, closed)
    result[c4d.SPLINEOBJECT_CLOSED] = all_closed
    result[c4d.SPLINEOBJECT_INTERPOLATION] = c4d.SPLINEOBJECT_INTERPOLATION_ADAPTIVE
    result[c4d.SPLINEOBJECT_ANGLE] = math.radians(2)
    result.SetName('chamferPro result')
    result.Message(c4d.MSG_UPDATE)
    return result


def evaluated_paths(op):
    paths = []
    collect(op.GetDown(), c4d.Matrix(), paths, ancestors=(op,))
    return paths


def evaluated_groups(op):
    groups = []
    collect(op.GetDown(), c4d.Matrix(), [], ancestors=(op,), groups=groups)
    return groups


class ChamferPro(plugins.ObjectData):
    def Init(self, op, isCloneInit=False):
        self.InitAttr(op, float, [ANGLE])
        self.InitAttr(op, float, [RADIUS])
        if not isCloneInit:
            op[ANGLE] = math.radians(30)
            op[RADIUS] = 10.
        self.status = 'Place splines below chamferPro.'
        self.signature = None
        self._evaluation = threading.local()
        return True

    def CheckDirty(self, op, doc):
        state = [doc.GetTime().Get() if doc else 0.]
        def visit(node, depth=0):
            while node:
                # CACHE changes as a consequence of our own evaluation. Watching
                # it here can continuously invalidate the generator's result.
                state.append((node, depth, node.GetDirty(c4d.DIRTYFLAGS_DATA |
                              c4d.DIRTYFLAGS_MATRIX | c4d.DIRTYFLAGS_CHILDREN)))
                visit(node.GetDown(), depth+1)
                node = node.GetNext()
        visit(op.GetDown())
        state = tuple(state)
        if state != getattr(self, 'signature', None):
            self.signature = state
            op.SetDirty(c4d.DIRTYFLAGS_DATA)

    def GetDDescription(self, op, description, flags):
        if not description.LoadDescription(op.GetType()): return False
        bc = description.GetParameterI(c4d.DescID(STATUS))
        if bc is not None: bc[c4d.DESC_NAME] = VERSION+' | '+getattr(self, 'status', '')
        return True, flags | c4d.DESCFLAGS_DESC_LOADED

    def build(self, op, bt=None):
        if op.GetDown() is None:
            self.status = 'Place splines below chamferPro.'
            return make_spline([])
        try:
            groups = evaluated_groups(op)
            paths = [path for group in groups for path in group]
            if sum(len(c) for c, _ in paths) > MAX_CURVES:
                self.status = 'Over 100,000 spans; original contours retained'
                return make_spline(paths)
            output, reports, stopped = [], [], 0
            for group in groups:
                # A slow child must not discard results from other children.
                budget = geo.WorkBudget(2., bt.TestBreak if bt is not None else None)
                try:
                    connected = geo.connect_paths(group, check=budget)
                    result, report = geo.round_paths_fixed(connected,
                        max(0., float(op[RADIUS])), max(0., min(math.pi, float(op[ANGLE]))),
                        check=budget, local_limit=True)
                    output.extend(result)
                    reports.append(report)
                except geo.EvaluationStopped:
                    output.extend(group)
                    stopped += 1
            # Connection timeout must not discard successfully rounded geometry.
            try:
                output = geo.connect_paths(output, check=geo.WorkBudget(2.))
            except geo.EvaluationStopped:
                pass
            self.status = '{} rounded | Radius {:.6g} | {} cleaned | {} locally limited | {} unchanged'.format(
                sum(r['rounded'] for r in reports),
                max(0., float(op[RADIUS])),
                sum(r['cleaned'] for r in reports),
                sum(r['limited'] for r in reports),
                sum(r['skipped']+r['conflicts'] for r in reports))
            self.status += ' | {} redundant points removed'.format(sum(r['redundant'] for r in reports))
            if stopped: self.status += ' | {} child evaluations stopped; original contours retained'.format(stopped)
            if not paths: self.status = 'No usable child splines found.'
            return make_spline(output)
        except Exception as error:
            self.status = str(error)
            traceback.print_exc()
            return make_spline([])

    def evaluate(self, op, hh=None, bt=None):
        # The host can request a contour while preparing a hierarchy cache.
        # Re-entering the same generator must never start another build.
        state = getattr(self, '_evaluation', None)
        if state is None:
            state = self._evaluation = threading.local()
        if getattr(state, 'active', False):
            self.status = 'Recursive evaluation blocked'
            return make_spline([])
        state.active = True
        try:
            if hh is not None and op.GetDown() is not None:
                hierarchy = op.GetAndCheckHierarchyClone(hh, op.GetDown(),
                            c4d.HIERARCHYCLONEFLAGS_ASSPLINE, True)
                if hierarchy and not hierarchy['dirty']:
                    return hierarchy['clone']
            return self.build(op, bt)
        finally:
            state.active = False

    def GetVirtualObjects(self, op, hh):
        return self.evaluate(op, hh=hh)

    def GetContour(self, op, doc, lod, bt):
        return self.evaluate(op, bt=bt)


if __name__ == '__main__':
    icon = bitmaps.BaseBitmap()
    if icon.InitWith(os.path.join(ROOT, 'res', 'icon.png'))[0] != c4d.IMAGERESULT_OK:
        icon = None
    if not plugins.RegisterObjectPlugin(PLUGIN_ID, 'chamferPro', ChamferPro,
            'Ochamferpro', c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT | c4d.OBJECT_ISSPLINE, icon):
        raise RuntimeError('chamferPro registration failed: plugin ID conflict.')
