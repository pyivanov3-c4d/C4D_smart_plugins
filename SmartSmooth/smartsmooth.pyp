"""SmartSmooth 1.1.0: Phong-driven subdivision and connected crease bevel."""
import math
import os
import sys
import traceback
import c4d
from c4d import plugins, bitmaps, utils

ROOT = os.path.dirname(__file__)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import smartsmooth_progress as progress

PLUGIN_ID = 1070000  # Local development ID; register before redistribution.
ITERATIONS = 1000
WIDTH, BEVEL_SUB, ROUNDNESS = 1001, 1002, 1003
MAX_POLYGONS = 2000000


def walk(root):
    while root is not None:
        yield root
        yield from walk(root.GetDown())
        root = root.GetNext()


def prepare(mesh, job):
    """Derive ALL creases from Phong, never from existing SDS/normal tags.

    Native OpenSubdiv is an implementation detail: transient 100% edge-only
    weights encode the derived crease mask. Zero point weights permit cubic
    crease refinement. Nothing is written to the user's input objects.
    """
    phong = mesh.GetTag(c4d.Tphong)
    angle = math.pi
    use_breaks = False
    if phong:
        if phong[c4d.PHONGTAG_PHONG_ANGLELIMIT]:
            angle = float(phong[c4d.PHONGTAG_PHONG_ANGLE])
        use_breaks = bool(phong[c4d.PHONGTAG_PHONG_USEEDGES])
    breaks = mesh.GetShadingBreak(False, use_breaks, False, math.pi, angle)
    if breaks is None:
        raise RuntimeError('Could not read Phong breaks.')
    # Ignore stored user normals and SDS weights: Phong is the sole input.
    for tag in mesh.GetTags():
        if tag.CheckType(c4d.Tsds) or tag.CheckType(c4d.Tnormal):
            tag.Remove()
    breaks.CopyTo(mesh.GetPhongBreak())
    if phong is None:
        phong = mesh.MakeTag(c4d.Tphong)
    # Bake original angle-based breaks into explicit edges; do not threshold
    # newly generated faces again. 180 degrees leaves only inherited creases.
    phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
    phong[c4d.PHONGTAG_PHONG_ANGLE] = math.pi
    phong[c4d.PHONGTAG_PHONG_USEEDGES] = True
    weights = mesh.MakeTag(c4d.Tsds)
    if not hasattr(weights, 'SetAllPolyWeights'):
        raise RuntimeError('SmartSmooth requires Cinema 4D 2026.2 or newer.')
    weights.InitFromObject()
    values = []
    polygons = mesh.GetAllPolygons()
    for i, poly in enumerate(polygons):
        if i % 1024 == 0:
            job.count(i, len(polygons), 'Reading Phong creases')
        row = {k: float(breaks.IsSelected(4*i+j)) for j, k in enumerate('abcd')}
        if poly.c == poly.d:
            row['c'] = row['d']
        values.append(row)
    weights.SetAllPointWeights([0.0] * mesh.GetPointCount())
    weights.SetAllPolyWeights(values)
    weights.SetDirty(c4d.DIRTYFLAGS_DATA)
    mesh.Message(c4d.MSG_UPDATE)


def subdivide(root, iterations, job):
    meshes = [o for o in walk(root) if o.CheckType(c4d.Opolygon)]
    estimate = sum(o.GetPolygonCount() for o in meshes) * 4**iterations
    if estimate > MAX_POLYGONS:
        raise ValueError('SmartSmooth: reduce iterations (2 million polygon limit).')
    if not iterations or not meshes:
        for node in walk(root):
            node.DelBit(c4d.BIT_CONTROLOBJECT)
        return root
    for mesh in meshes:
        prepare(mesh, job)
    doc = c4d.documents.BaseDocument()
    try:
        sds = c4d.BaseObject(c4d.Osds)
        sds[c4d.SDSOBJECT_TYPE] = c4d.SDSOBJECT_TYPE_OSD_CATMARK
        sds[c4d.SDSOBJECT_SUBEDITOR_CM] = iterations
        sds[c4d.SDSOBJECT_SUBRAY_CM] = iterations
        sds[c4d.SDSOBJECT_OSD_BOUNDARY_METHOD] = c4d.SDSOBJECT_OSD_BOUNDARY_METHOD_EDGEONLY
        sds[c4d.SDSOBJECT_OSD_EDGE_CREASE] = c4d.SDSOBJECT_OSD_EDGE_CREASE_UNIFORM
        doc.InsertObject(sds)
        root.InsertUnder(sds)
        job.stage('Subdividing — {} iteration{}'.format(iterations, '' if iterations == 1 else 's'))
        result = utils.SendModelingCommand(command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
            list=[sds], doc=doc, mode=c4d.MODELINGCOMMANDMODE_ALL)
        job.check()
        if not isinstance(result, list) or not result:
            raise RuntimeError('Native subdivision did not produce a result.')
        output = result[0]
        output.Remove()
        for node in walk(output):
            node.DelBit(c4d.BIT_CONTROLOBJECT)
            for tag in node.GetTags():
                if tag.CheckType(c4d.Tsds):
                    tag.Remove()
        return output
    finally:
        c4d.documents.KillDocument(doc)


def bevel_creases(root, width, subdivisions, roundness, job, prepare_input=False):
    if width <= 0:
        return root
    doc = c4d.documents.BaseDocument()
    try:
        doc.InsertObject(root)
        for mesh in list(walk(root)):
            if not mesh.CheckType(c4d.Opolygon):
                continue
            if prepare_input:
                prepare(mesh, job)
            for tag in mesh.GetTags():
                if tag.CheckType(c4d.Tsds) or tag.CheckType(c4d.Tnormal):
                    tag.Remove()
            # Only inherited Phong creases, never the subdivided face grid.
            selection = mesh.GetPhongBreak()
            if not selection.GetCount():
                continue
            selection.CopyTo(mesh.GetEdgeS())
            bc = c4d.BaseContainer()
            bc[c4d.MDATA_BEVEL_MASTER_MODE] = c4d.MDATA_BEVEL_MASTER_MODE_CHAMFER
            bc[c4d.MDATA_BEVEL_OFFSET_MODE] = c4d.MDATA_BEVEL_OFFSET_MODE_FIXED
            bc[c4d.MDATA_BEVEL_RADIUS] = width
            bc[c4d.MDATA_BEVEL_SUB] = float(subdivisions)
            bc[c4d.MDATA_BEVEL_DEPTH] = roundness
            bc[c4d.MDATA_BEVEL_LIMIT] = True
            bc[c4d.MDATA_BEVEL_EXTRUSION] = 0.0
            bc[c4d.MDATA_BEVEL_SHAPING_MODE] = c4d.MDATA_BEVEL_SHAPING_MODE_ROUND
            bc[c4d.MDATA_BEVEL_SHAPING_TENSION] = 1.0
            bc[c4d.MDATA_BEVEL_MITERING] = c4d.MDATA_BEVEL_MITERING_UNIFORM
            bc[c4d.MDATA_BEVEL_CORNER_ENDING] = c4d.MDATA_BEVEL_CORNER_ENDING_DEFAULT
            bc[c4d.MDATA_BEVEL_PROUNDING_TYPE] = c4d.MDATA_BEVEL_PROUNDING_TYPE_FLAT
            bc[c4d.MDATA_BEVEL_CORNER_NGON] = False
            bc[c4d.MDATA_BEVEL_ROUNDING_NGON] = False
            bc[c4d.MDATA_BEVEL_SELECTION_PHONG_BREAK] = False
            bc[c4d.MDATA_BEVEL_SELECTION_PHONG_BREAK_M] = False
            job.stage('Beveling Phong creases')
            success = utils.SendModelingCommand(command=c4d.ID_XBEVELTOOL,
                list=[mesh], doc=doc, mode=c4d.MODELINGCOMMANDMODE_EDGESELECTION, bc=bc)
            job.check()
            if success is False:
                raise RuntimeError('SmartSmooth: crease bevel failed.')
            # All crease edges were beveled: inherited breaks inside the new
            # rim would create unwanted shading seams between its profile loops.
            mesh.GetPhongBreak().DeselectAll()
            mesh.GetEdgeS().DeselectAll()
            mesh.Message(c4d.MSG_UPDATE)
        root.Remove()
        return root
    finally:
        c4d.documents.KillDocument(doc)


class SmartSmooth(plugins.ObjectData):
    def Init(self, op, isCloneInit=False):
        self.InitAttr(op, int, [ITERATIONS])
        self.InitAttr(op, float, [WIDTH])
        self.InitAttr(op, int, [BEVEL_SUB])
        self.InitAttr(op, float, [ROUNDNESS])
        if not isCloneInit:
            op[ITERATIONS] = 3
            op[WIDTH], op[BEVEL_SUB], op[ROUNDNESS] = 0.0, 3, 1.0
        self.signature = None
        self.retry = False
        return True

    def CheckDirty(self, op, doc):
        state = []
        for node in walk(op.GetDown()):
            state.append((node, node.GetDirty(c4d.DIRTYFLAGS_ALL)))
            for tag in node.GetTags():
                state.append((tag, tag.GetDirty(c4d.DIRTYFLAGS_DATA)))
            if node.CheckType(c4d.Opolygon):
                state.append(node.GetPhongBreak().GetDirty())
        state = tuple(state)
        if self.retry or state != self.signature:
            self.signature = state
            op.SetDirty(c4d.DIRTYFLAGS_DATA)

    def GetVirtualObjects(self, op, hh):
        first = op.GetDown()
        if first is None:
            return c4d.BaseObject(c4d.Onull)
        job = None
        try:
            self.retry = False
            if op.CheckCache(hh) or op.IsDirty(c4d.DIRTYFLAGS_DATA):
                job = progress.Progress(c4d.threading.GeGetCurrentThread())
                job.stage('Evaluating input')
            clone = op.GetAndCheckHierarchyClone(hh, first, c4d.HIERARCHYCLONEFLAGS_ASPOLY, True)
            if not clone or clone['clone'] is None:
                return None
            if not clone['dirty']:
                return clone['clone']
            if job is None:
                job = progress.Progress(c4d.threading.GeGetCurrentThread())
            job.stage('Reading input')
            iterations = max(0, min(6, int(op[ITERATIONS])))
            result = subdivide(clone['clone'], iterations, job)
            result = bevel_creases(result, max(0.0, float(op[WIDTH])),
                max(0, min(64, int(op[BEVEL_SUB]))),
                max(-1.0, min(1.0, float(op[ROUNDNESS]))), job, iterations == 0)
            result.SetName('SmartSmooth')
            return result
        except progress.Cancelled:
            self.retry = True
            return None
        except Exception as error:
            traceback.print_exc()
            result = c4d.BaseObject(c4d.Onull)
            result.SetName(str(error))
            return result
        finally:
            if job:
                job.close()


if __name__ == '__main__':
    icon = bitmaps.BaseBitmap()
    icon.InitWith(os.path.join(ROOT, 'res', 'icon.png'))
    progress.register_progress()
    plugins.RegisterObjectPlugin(PLUGIN_ID, 'SmartSmooth', SmartSmooth,
        'Osmartsmooth', c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT, icon)
