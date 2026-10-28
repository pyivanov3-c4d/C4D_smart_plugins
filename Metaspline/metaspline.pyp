"""Metaspline - closed planar liquid spline generator for Cinema 4D."""
import math
import os
import sys
import threading
import traceback
import c4d
from c4d import plugins, bitmaps, utils

ROOT = os.path.dirname(__file__)
if ROOT not in sys.path: sys.path.insert(0, ROOT)
import metaspline_geometry as geo
import metaspline_progress as progress_ui

PLUGIN_ID = 1069991  # Local installation ID; register before redistribution.
COLLAPSE, FALLOW, SMOOTH, STATUS, VISCOSITY = 11000, 11001, 11002, 11003, 11004
MAX_CURVES = 100000
VERSION = '2.2.1'


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
    while node:
        if check: check()
        try:
            if len(ancestors)>64 or any(node==v for v in ancestors):
                raise ValueError('Cyclic or deep child hierarchy')
            lineage=ancestors+(node,)
            matrix=parent_matrix*node.GetMl()
            deform=node.GetDeformCache()
            if deform is not None:
                collect(deform,matrix,paths,check,lineage,groups)
            elif node.CheckType(c4d.Ospline) or node.CheckType(c4d.Oline):
                source=read_spline(node,matrix,check)
                paths.extend(source)
                if groups is not None and source: groups.append(source)
            else:
                spline=node.GetRealSpline() if node.GetInfo() & c4d.OBJECT_ISSPLINE else None
                if spline is not None:
                    source=read_spline(spline,matrix,check)
                    paths.extend(source)
                    if groups is not None and source: groups.append(source)
                elif node.GetCache() is not None:
                    collect(node.GetCache(),matrix,paths,check,lineage,groups)
                elif node.GetDown() is not None:
                    collect(node.GetDown(),matrix,paths,check,lineage,groups)
        except geo.EvaluationStopped:
            raise
        except Exception as error:
            print('Metaspline skipped child: '+str(error))
        node=node.GetNext()


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
    result.SetName('Metaspline result')
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


class Metaspline(plugins.ObjectData):
    def Init(self, op, isCloneInit=False):
        for key in (COLLAPSE,FALLOW,SMOOTH,VISCOSITY): self.InitAttr(op,float,[key])
        if not isCloneInit: op[COLLAPSE],op[FALLOW],op[SMOOTH]=20.,40.,.15
        if not isCloneInit or op[VISCOSITY] is None:op[VISCOSITY]=.25
        self.status='Place closed splines below Metaspline.'
        self.signature=None
        self._evaluation=threading.local()
        self._result_lock=threading.RLock()
        self._result_cache=None
        return True

    def CheckDirty(self,op,doc):
        state=[doc.GetTime().Get() if doc else 0.]
        def visit(node,depth=0):
            while node and len(state)<10000 and depth<64:
                state.append((node,depth,node.GetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_MATRIX | c4d.DIRTYFLAGS_CHILDREN)))
                visit(node.GetDown(),depth+1)
                node=node.GetNext()
        visit(op.GetDown())
        state=tuple(state)
        if state!=getattr(self,'signature',None):
            self.signature=state; op.SetDirty(c4d.DIRTYFLAGS_DATA)

    def GetDDescription(self,op,description,flags):
        if not description.LoadDescription(op.GetType()): return False
        # Resource PERCENT literals are display percentages; runtime bounds are
        # normalized. Explicit runtime bounds also protect against stale sliders.
        smooth_bc=description.GetParameterI(c4d.DescID(SMOOTH))
        if smooth_bc is not None:
            smooth_bc[c4d.DESC_MIN]=0.
            smooth_bc[c4d.DESC_MAX]=1.
            smooth_bc[c4d.DESC_MINSLIDER]=0.
            smooth_bc[c4d.DESC_MAXSLIDER]=1.
            smooth_bc[c4d.DESC_STEP]=.01
        viscosity_bc=description.GetParameterI(c4d.DescID(VISCOSITY))
        if viscosity_bc is not None:
            viscosity_bc[c4d.DESC_MIN]=0.
            viscosity_bc[c4d.DESC_MAX]=1.
            viscosity_bc[c4d.DESC_MINSLIDER]=0.
            viscosity_bc[c4d.DESC_MAXSLIDER]=1.
            viscosity_bc[c4d.DESC_STEP]=.01
        bc=description.GetParameterI(c4d.DescID(STATUS))
        if bc is not None: bc[c4d.DESC_NAME]=VERSION+' | '+getattr(self,'status','')
        return True,flags | c4d.DESCFLAGS_DESC_LOADED

    def build(self,op,bt=None):
        groups=[]; skipped=0
        cancel=bt.TestBreak if bt else None
        job=progress_ui.Progress(bt)
        try:
            job.stage('Reading closed child splines')
            # Each top-level child gets an independent read budget.
            node=op.GetDown()
            count=0
            while node and count<256:
                # collect walks siblings, so restrict traversal with a stop callback.
                child_groups=[]
                try:
                    collect_one(node,c4d.Matrix(),child_groups,geo.WorkBudget(.6,cancel),(op,))
                    groups.extend(child_groups)
                except geo.EvaluationStopped:
                    if cancel and cancel():raise progress_ui.Cancelled()
                    skipped+=1
                except Exception as error:
                    skipped+=1; print('Metaspline skipped child: '+str(error))
                node=node.GetNext(); count+=1
            originals=[(c,True) for group in groups for c,closed in group if closed and c]
            if sum(len(c) for c,_ in originals)>MAX_CURVES:
                self.status='Curve limit; closed originals retained'
                return make_spline(originals)
            try:
                if not hasattr(self._evaluation,'geometry_cache'): self._evaluation.geometry_cache={}
                viscosity=.25 if op[VISCOSITY] is None else max(0.,min(1.,float(op[VISCOSITY])))
                result,self.status=geo.process(groups,max(0.,float(op[COLLAPSE])),max(0.,float(op[FALLOW])),max(0.,min(1.,float(op[SMOOTH]))),geo.WorkBudget(6.,cancel),cache=self._evaluation.geometry_cache,progress=job.stage,viscosity=viscosity)
            except geo.EvaluationStopped as error:
                result=originals; self.status=str(error)+'; closed originals retained'
            if skipped: self.status+=' | {} child reads skipped'.format(skipped)
            return make_spline(result)
        except progress_ui.Cancelled:
            self.status='Cancelled; closed originals retained'
            return make_spline(locals().get('originals',[]))
        except Exception as error:
            self.status=str(error); traceback.print_exc()
            return make_spline(locals().get('originals',[]))
        finally:
            job.close()

    def evaluate(self,op,hh=None,bt=None):
        state=getattr(self,'_evaluation',None)
        if state is None: state=self._evaluation=threading.local()
        if getattr(state,'active',False): return make_spline([])
        state.active=True
        try:
            if hh is not None and op.GetDown() is not None:
                hierarchy=op.GetAndCheckHierarchyClone(hh,op.GetDown(),c4d.HIERARCHYCLONEFLAGS_ASSPLINE,True)
                if hierarchy and not hierarchy['dirty']: return hierarchy['clone']
            def source_signature():
                doc=op.GetDocument() if hasattr(op,'GetDocument') else None
                signature=[op[COLLAPSE],op[FALLOW],op[SMOOTH],op[VISCOSITY],doc.GetTime().Get() if doc else 0.]
                def fingerprint(node,depth=0):
                    while node and depth<64 and len(signature)<10000:
                        signature.append((node,node.GetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_MATRIX | c4d.DIRTYFLAGS_CHILDREN)))
                        fingerprint(node.GetDown(),depth+1);node=node.GetNext()
                fingerprint(op.GetDown())
                return tuple(signature)
            signature=source_signature()
            # GetContour and GVO can run on different host threads. Share only
            # cloned output; mutable intermediate geometry stays thread-local.
            with self._result_lock:
                cached=self._result_cache
                if cached is not None and cached[0]==signature:return cached[1].GetClone()
            result=self.build(op,bt)
            if hasattr(result,'GetClone') and not any(word in self.status.lower() for word in ('cancel','limit','retained','skipped')):
                with self._result_lock:self._result_cache=(source_signature(),result.GetClone())
            return result
        finally: state.active=False

    def GetVirtualObjects(self,op,hh): return self.evaluate(op,hh=hh)
    def GetContour(self,op,doc,lod,bt): return self.evaluate(op,bt=bt)


def collect_one(node,parent_matrix,groups,check,ancestors):
    check()
    if len(ancestors)>64 or any(node==v for v in ancestors): raise ValueError('Cyclic/deep hierarchy')
    matrix=parent_matrix*node.GetMl(); lineage=ancestors+(node,)
    deform=node.GetDeformCache()
    if deform is not None:
        collect(deform,matrix,[],check,lineage,groups)
    elif node.CheckType(c4d.Ospline) or node.CheckType(c4d.Oline):
        groups.append(read_spline(node,matrix,check))
    else:
        spline=node.GetRealSpline() if node.GetInfo() & c4d.OBJECT_ISSPLINE else None
        if spline is not None: groups.append(read_spline(spline,matrix,check))
        else:
            child=node.GetCache()
            if child is None: child=node.GetDown()
            if child is not None: collect(child,matrix,[],check,lineage,groups)


if __name__=='__main__':
    if not progress_ui.register_progress():
        raise RuntimeError('Metaspline progress registration failed: plugin ID conflict.')
    icon=bitmaps.BaseBitmap()
    if icon.InitWith(os.path.join(ROOT,'res','icon.png'))[0]!=c4d.IMAGERESULT_OK: icon=None
    if not plugins.RegisterObjectPlugin(PLUGIN_ID,'Metaspline',Metaspline,'Ometaspline',c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT | c4d.OBJECT_ISSPLINE,icon):
        raise RuntimeError('Metaspline registration failed: plugin ID conflict.')


