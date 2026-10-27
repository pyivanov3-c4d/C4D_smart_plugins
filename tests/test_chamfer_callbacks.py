"""Regression checks for callback orchestration; these are not live C4D tests."""
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ChamferPro'))
import chamfer_geometry as geo


class Matrix:
    def __mul__(self, other): return other


class Vector(tuple):
    def __new__(cls,*p): return tuple.__new__(cls,p)
    def __mul__(self,s): return Vector(*(x*s for x in self))
    def __add__(self,b): return Vector(*(x+y for x,y in zip(self,b)))
    x=property(lambda self:self[0])
    y=property(lambda self:self[1])
    z=property(lambda self:self[2])


class ObjectData:
    def InitAttr(self, *args): pass


fake = types.ModuleType('c4d')
fake.plugins = types.SimpleNamespace(ObjectData=ObjectData)
fake.bitmaps = types.SimpleNamespace()
fake.utils = types.SimpleNamespace(SendModelingCommand=Mock(side_effect=AssertionError('Nested modeling command')))
fake.documents = types.SimpleNamespace(BaseDocument=Mock(side_effect=AssertionError('Nested document evaluation')))
fake.Matrix = Matrix
fake.OBJECT_ISSPLINE, fake.Ospline, fake.Oline = 1, 5101, 5137
fake.DIRTYFLAGS_DATA, fake.DIRTYFLAGS_MATRIX, fake.DIRTYFLAGS_CACHE, fake.DIRTYFLAGS_CHILDREN = 1,2,4,8
fake.HIERARCHYCLONEFLAGS_ASSPLINE = 1
with patch.dict(sys.modules, {'c4d':fake}):
    code = runpy.run_path(str(ROOT/'ChamferPro/chamfer_pro.pyp'))
Plugin = code['ChamferPro']
namespace = Plugin.build.__globals__


class Node(dict):
    def __eq__(self, other): return self is other
    def __ne__(self, other): return self is not other
    def __init__(self, child=None, spline=None):
        super().__init__({11000:.5,11001:10.})
        self.child, self.spline = child, spline
        self.changes = 0
        self.dirty = {1:0,2:0,4:0,8:0}
        self.reads = 0
    def GetDown(self): return self.child
    def GetNext(self): return None
    def GetMl(self): return Matrix()
    def GetDeformCache(self): return None
    def GetCache(self): return None
    def CheckType(self, kind): return False
    def GetInfo(self): return fake.OBJECT_ISSPLINE if self.spline is not None else 0
    def GetRealSpline(self):
        self.reads += 1
        return self.spline
    def GetDirty(self, flags): return sum(n for flag,n in self.dirty.items() if flags & flag)
    def SetDirty(self, flags): self.changes += 1


class CallbackTests(unittest.TestCase):
    def setUp(self):
        self.op = Node(Node())
        self.plugin = Plugin()
        self.plugin.Init(self.op)

    def test_multicontour_output_closure(self):
        class Spline(dict):
            def __init__(self,*args): super().__init__(); self.segments=[]; self.tangents={}
            def ResizeObject(self,n,s): self.segments=[None]*s
            def SetAllPoints(self,p): self.points=p
            def SetTangent(self,i,left,right): self.tangents[i]={'vl':left,'vr':right}
            def GetTangent(self,i): return self.tangents[i]
            def GetAllPoints(self): return self.points
            def GetInterpolationType(self): return 4
            def GetSegmentCount(self): return len(self.segments)
            def GetSegment(self,i): return dict(zip(('cnt','closed'),self.segments[i]))
            def IsClosed(self): return self[100]
            def CheckType(self,kind): return False
            def SetSegment(self,i,n,closed): self.segments[i]=(n,closed)
            def SetName(self,*args): pass
            def Message(self,*args): pass
        square=[geo.line(a,b) for a,b in zip([(0,0,0),(10,0,0),(10,10,0),(0,10,0)],
                                            [(10,0,0),(10,10,0),(0,10,0),(0,0,0)])]
        attrs={'SplineObject':Spline,'Vector':Vector,'SPLINETYPE_BEZIER':4,'SPLINETYPE_LINEAR':0,
               'SPLINEOBJECT_CLOSED':100,'SPLINEOBJECT_INTERPOLATION':101,
               'SPLINEOBJECT_INTERPOLATION_ADAPTIVE':3,'SPLINEOBJECT_ANGLE':102,'MSG_UPDATE':0}
        with patch.dict(fake.__dict__,attrs):
            result=code['make_spline']([(square,True),(square,True)])
            self.assertTrue(result[100])
            self.assertEqual(result.segments,[(4,True),(4,True)])
            mixed=code['make_spline']([(square,True),([square[0]],False)])
            self.assertFalse(mixed[100])
            self.assertEqual(mixed.points[0],mixed.points[4])
            self.assertNotEqual(mixed.points[5],mixed.points[6])
            arcs=geo.circle_arcs((0,0,0),(100,0,0),(0,100,0),(0,0,1),100)
            spline=code['make_spline']([(arcs,False)])
            decoded=[]
            for i in range(len(spline.points)-1):
                a,b=spline.points[i:i+2]
                # Model the host's documented 4/3 handle interpretation.
                cubic=(a,a+spline.tangents[i]['vr']*(4/3),
                       b+spline.tangents[i+1]['vl']*(4/3),b)
                decoded.append(cubic)
                for j in range(101):
                    self.assertLess(abs(geo.length(geo.point(cubic,j/100))-100),.0005)
            imported=code['read_spline'](spline,Matrix())[0][0]
            for expected,actual in zip(decoded,imported):
                for p,q in zip(expected,actual): self.assertLess(geo.length(geo.sub(p,q)),1e-10)

    def test_text_uses_native_contour_without_modeling(self):
        spline = object()
        text = Node(spline=spline)
        op = Node(text)
        paths = [([geo.line((0,0,0),(10,0,0))],False)]
        with patch.dict(namespace, {'read_spline':Mock(return_value=paths)}):
            self.assertEqual(code['evaluated_paths'](op),paths)
        self.assertEqual(text.reads,1)
        fake.utils.SendModelingCommand.assert_not_called()
        fake.documents.BaseDocument.assert_not_called()

    def test_cache_dirty_does_not_trigger_rebuild_loop(self):
        doc = types.SimpleNamespace(GetTime=lambda: types.SimpleNamespace(Get=lambda:0))
        self.plugin.CheckDirty(self.op,doc)
        self.assertEqual(self.op.changes,1)
        self.op.child.dirty[4] += 1
        self.plugin.CheckDirty(self.op,doc)
        self.assertEqual(self.op.changes,1)
        self.op.child.dirty[1] += 1
        self.plugin.CheckDirty(self.op,doc)
        self.assertEqual(self.op.changes,2)
        self.op.child = None
        self.plugin.CheckDirty(self.op,doc)
        self.assertEqual(self.op.changes,3)

    def test_reentrant_contour_does_not_recurse(self):
        def hierarchy(*args):
            self.assertEqual(self.plugin.GetContour(self.op,None,1,None),[])
            return {'dirty':True,'clone':None}
        self.op.GetAndCheckHierarchyClone = hierarchy
        with patch.dict(namespace, {'make_spline':lambda paths:paths}), patch.object(self.plugin,'build',return_value='result') as build:
            self.assertEqual(self.plugin.GetVirtualObjects(self.op,object()),'result')
            self.assertEqual(build.call_count,1)

    def test_unchanged_hierarchy_reuses_cache(self):
        self.op.GetAndCheckHierarchyClone = lambda *args:{'dirty':False,'clone':'cached'}
        with patch.object(self.plugin,'build',side_effect=AssertionError('unnecessary rebuild')):
            self.assertEqual(self.plugin.GetVirtualObjects(self.op,object()),'cached')

    def test_budget_fallback_preserves_whole_input(self):
        paths = [([geo.line((i,0,0),(i+1,0,0)) for i in range(1000)],False)]
        expired = geo.WorkBudget(-1.)
        with patch.dict(namespace, {'evaluated_groups':lambda op:[paths],'make_spline':lambda paths:paths}), patch.object(geo,'WorkBudget',return_value=expired):
            self.assertEqual(self.plugin.build(self.op),paths)
            self.assertIn('original contours retained',self.plugin.status)

    def test_small_child_does_not_reduce_requested_radius(self):
        def rectangle(x,w,h):
            points=[(x,0,0),(x+w,0,0),(x+w,h,0),(x,h,0)]
            return ([geo.line(a,b) for a,b in zip(points,points[1:]+points[:1])],True)
        groups=[[rectangle(0,400,400)],
                [rectangle(500,100,20),rectangle(700,100,100)]]
        self.op[11001]=100.
        expected=[]
        radii=[]
        for group in groups:
            result,report=geo.round_paths_fixed(group,100.,self.op[11000],local_limit=True)
            expected.extend(result)
            radii.append(report['effective_radius'])
        with patch.dict(namespace, {'evaluated_groups':lambda op:groups,'make_spline':lambda paths:paths}):
            actual=self.plugin.build(self.op)
        self.assertEqual(actual,expected)
        self.assertEqual(radii[0],100.)
        self.assertEqual(radii[1],100.)
        self.assertIn('12 rounded',self.plugin.status)
        self.assertIn('8 locally limited',self.plugin.status)
        self.assertIn('0 unchanged',self.plugin.status)

    def test_timeout_of_first_child_does_not_cancel_second(self):
        points=[(0,0,0),(100,0,0),(100,100,0),(0,100,0)]
        square=([geo.line(a,b) for a,b in zip(points,points[1:]+points[:1])],True)
        rounded,report=geo.round_paths_fixed([square],10,.5,local_limit=True)
        with patch.dict(namespace, {'evaluated_groups':lambda op:[[square],[square]],'make_spline':lambda p:p}), patch.object(geo,'round_paths_fixed',side_effect=[geo.EvaluationStopped('test'),(rounded,report)]):
            result=self.plugin.build(self.op)
        self.assertEqual(result,[square]+rounded)
        self.assertIn('4 rounded',self.plugin.status)
        self.assertIn('1 child evaluations stopped',self.plugin.status)

    def test_collection_keeps_multicontour_sources_together(self):
        a,b=Node(spline=object()),Node(spline=object())
        a.GetNext=lambda:b
        first=[([geo.line((0,0,0),(10,0,0))],False)]*2
        second=[([geo.line((20,0,0),(30,0,0))],False)]
        with patch.dict(namespace, {'read_spline':Mock(side_effect=[first,second])}):
            self.assertEqual(code['evaluated_groups'](Node(a)),[first,second])

    def test_exception_releases_recursion_guard(self):
        with patch.object(self.plugin,'build',side_effect=ValueError('test')):
            with self.assertRaises(ValueError): self.plugin.evaluate(self.op)
        with patch.object(self.plugin,'build',return_value='recovered'):
            self.assertEqual(self.plugin.evaluate(self.op),'recovered')


if __name__=='__main__': unittest.main()
