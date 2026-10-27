"""SplineTensor 0.10.0 experimental -- Cinema 4D Python generator."""
import os
import sys
import traceback
import c4d
from c4d import plugins, bitmaps, utils

ROOT = os.path.dirname(__file__)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from st_geometry import GeometryError
from st_clip import build_clipped as build_many
from st_union import unite_contours
from st_inputs import sample_loops, hierarchy_key
from st_uv import planar_uvs
from st_progress import Progress, register_progress

# DEVELOPMENT ONLY. Obtain a unique Maxon plugin ID before distributing scenes.
PLUGIN_ID = 1069998
WIDTH, SUBDIVISION, CURVE = 1000, 1001, 1002
CLOSED = 1003
DENSITY = 1004

def density_value(op):
    return max(1,int(op.GetDataInstance().GetData(DENSITY) or 1))



def curve_key(curve):
    if curve is None:
        return None
    return tuple(tuple((k[name].x,k[name].y,k[name].z) for name in
                       ('vPos','vTangentLeft','vTangentRight')) + (k['interpol'],)
                 for k in curve.GetKnots())


def default_curve(start_handle=.35,end_handle=.25):
    curve = c4d.SplineData()
    curve.MakeLinearSplineBezier(2)
    knots = curve.GetKnots()
    curve.SetKnot(0,c4d.Vector(0,0,0),knots[0]['lFlagsSettings'],
                  vTangentLeft=c4d.Vector(-start_handle,0,0),vTangentRight=c4d.Vector(start_handle,0,0))
    curve.SetKnot(1,c4d.Vector(1,1,0),knots[1]['lFlagsSettings'],
                  vTangentLeft=c4d.Vector(0,-end_handle,0),vTangentRight=c4d.Vector(0,end_handle,0))
    return curve


_legacy = c4d.SplineData()
_legacy.MakeUserSpline('sin(x*pi/2)',17)
LEGACY_CURVE_KEY = curve_key(_legacy)
PREVIOUS_CURVE_KEY = curve_key(default_curve(.5522847498307936,.5522847498307936))


def migrate_curve(op):
    curve = op[CURVE]
    if curve is not None and curve_key(curve) in (LEGACY_CURVE_KEY,PREVIOUS_CURVE_KEY):
        op[CURVE] = default_curve()
        return True
    return False


def geometry_key(op):
    children = []
    child = op.GetDown()
    while child:
        children.append(hierarchy_key(child))
        child = child.GetNext()
    phong=op.GetTag(c4d.Tphong)
    tag_key=tuple((k,repr(value)) for k,value in phong.GetDataInstance()) if phong else None
    return (op[WIDTH],op[SUBDIVISION],op.GetDataInstance().GetData(CLOSED),
            curve_key(op[CURVE]),tuple(children),tag_key,density_value(op))


def sample(child, generator, density=1):
    loops=sample_loops(child,generator,density)
    if len(loops)!=1:
        raise GeometryError('The first child must produce one closed base boundary.')
    return loops[0]


class SplineTensor(plugins.ObjectData):
    def __init__(self):
        # Native optimization bypasses child invalidation on some hosts. Keep
        # the inexpensive fingerprint check active; reuse geometry explicitly.
        self.SetOptimizeCache(False)
        self._signature = None
        self._last_error = None
        self._built_key = None
        self._template = None
        self._build_count = 0

    def Init(self, op, isCloneInit=False):
        if isCloneInit:
            return True
        op[WIDTH] = 0.0
        op[SUBDIVISION] = 3
        op[CLOSED] = True
        op[DENSITY] = 1
        op[CURVE] = default_curve()
        return True

    def Message(self, op, message, data):
        if c4d.threading.GeIsMainThread():
            migrate_curve(op)
            if op.GetDataInstance().GetData(DENSITY) is None:op[DENSITY]=1
            if message == c4d.MSG_MENUPREPARE and op.GetTag(c4d.Tphong) is None:
                op.SetPhong(True,True,1.3962634016)
        return True

    def CheckDirty(self, op, doc):
        # Include identities, order, transforms and data. Avoid cache reuse when
        # a child moves, changes interpolation, is replaced, or is reparented.
        signature = geometry_key(op)
        if signature != self._signature:
            self._signature = signature
            op.SetDirty(c4d.DIRTYFLAGS_DATA)

    def GetVirtualObjects(self, op, hh):
        key = geometry_key(op)
        if key == self._built_key:
            cache = op.GetCache()
            if cache is not None:
                return cache
            if self._template is not None:
                return self._template.GetClone()
        self._build_count += 1
        progress = Progress()
        try:
            progress.stage(2, 'Reading splines')
            first = op.GetDown()
            second = first.GetNext() if first else None
            if first is None or second is None:
                raise GeometryError('Add a closed base spline first, then one or more closed relief splines.')
            curve = op[CURVE]
            profile = (lambda t: curve.GetPoint(t).y) if curve else None
            closed = op.GetDataInstance().GetData(CLOSED)
            density=density_value(op)
            contours = []
            child = second
            while child:
                contours.extend(sample_loops(child,op,density))
                child = child.GetNext()
            base=sample(first,op,density)
            if len(base)+sum(len(loop) for loop in contours)>1200*density:
                raise GeometryError('Use at most 1200 total sampled points across all children.')
            delta=second.GetMl().off-first.GetMl().off
            progress.stage(15, 'Combining projected shapes', busy=True)
            contours=unite_contours(base,contours,(delta.x,delta.y,delta.z),nested_masks=True)
            progress.stage(30, 'Building and welding surface', busy=True)
            if not contours:
                # Even-odd cancellation leaves the original flat base.
                contours=[base]
            points, triangles, creases = build_many(base, contours,
                                      float(op[WIDTH]), int(op[SUBDIVISION]), profile,
                                      closed=True if closed is None else bool(closed), quad_bands=True, return_edges=True, quality=True, density=density)
            progress.stage(85, 'Creating polygons and UVs')
            result = c4d.PolygonObject(len(points), len(triangles))
            result.SetAllPoints([c4d.Vector(*p) for p in points])
            for i, polygon in enumerate(triangles):
                result.SetPolygon(i, c4d.CPolygon(*polygon))
            uv_points=[c4d.Vector(*p) for p in planar_uvs(base,points)]
            uv_tag=c4d.UVWTag(len(triangles))
            for i,polygon in enumerate(triangles):
                ids=tuple(polygon) if len(polygon)==4 else tuple(polygon)+(polygon[2],)
                uv_tag.SetSlow(i,*[uv_points[j] for j in ids])
            result.InsertTag(uv_tag)
            result.SetName('SplineTensor Surface')
            progress.stage(95, 'Finishing shading')
            source_phong=op.GetTag(c4d.Tphong)
            phong=source_phong.GetClone() if source_phong else c4d.BaseTag(c4d.Tphong)
            if source_phong is None:
                phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
                phong[c4d.PHONGTAG_PHONG_ANGLE] = 1.3962634016
            phong[c4d.PHONGTAG_PHONG_USEEDGES] = True
            result.InsertTag(phong)
            crease_set={frozenset(e) for e in creases}
            breaks=result.GetPhongBreak()
            for index,p in enumerate(result.GetAllPolygons()):
                for edge,(a,b) in enumerate(((p.a,p.b),(p.b,p.c),(p.c,p.d),(p.d,p.a))):
                    if a!=b and frozenset((a,b)) in crease_set:
                        breaks.Select(4*index+edge)
            result.Message(c4d.MSG_UPDATE)
            self._last_error = None
            self._template = result.GetClone()
            self._built_key = key
            return result
        except GeometryError as exc:
            message = str(exc)
        except Exception:
            message = 'Unexpected API/geometry error; see Python Console.'
            traceback.print_exc()
        finally:
            progress.close()
        if message != self._last_error:
            print('SplineTensor: ' + message)
            self._last_error = message
        empty = c4d.BaseObject(c4d.Onull)
        empty.SetName('SplineTensor: ' + message)
        self._template = empty.GetClone()
        self._built_key = key
        return empty


if __name__ == '__main__':
    register_progress()
    icon = bitmaps.BaseBitmap()
    status, _ = icon.InitWith(os.path.join(ROOT, 'res', 'icon.png'))
    if status != c4d.IMAGERESULT_OK:
        icon = None
    plugins.RegisterObjectPlugin(id=PLUGIN_ID, str='SplineTensor', g=SplineTensor,
        description='Osplinetensor', info=c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT,
        icon=icon)

