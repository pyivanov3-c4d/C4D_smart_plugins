"""Regression checks for callback orchestration; these are not live C4D tests."""
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'Metaspline'))
import metaspline_geometry as geo


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
    code = runpy.run_path(str(ROOT/'Metaspline/metaspline.pyp'))
Plugin = code['Metaspline']
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
    def test_percent_description_allows_full_rounding(self):
        bc={'max':.01,'slidermax':.01}
        desc=types.SimpleNamespace(LoadDescription=lambda kind:True,GetParameterI=lambda ident:bc if ident==11002 else None)
        attrs={'DescID':lambda v:v,'DESC_MIN':'min','DESC_MAX':'max','DESC_MINSLIDER':'slidermin','DESC_MAXSLIDER':'slidermax','DESC_STEP':'step','DESCFLAGS_DESC_LOADED':1}
        with patch.dict(fake.__dict__,attrs):
            self.plugin.GetDDescription(types.SimpleNamespace(GetType=lambda:1069991),desc,0)
        self.assertEqual(bc['max'],1.)
        self.assertEqual(bc['slidermax'],1.)
        self.assertEqual(bc['step'],.01)
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
            from test_metaspline import circle
            arcs=circle(r=100)[0]
            spline=code['make_spline']([(arcs,True)])
            decoded=[]
            for i in range(len(spline.points)):
                j=(i+1)%len(spline.points)
                a,b=spline.points[i],spline.points[j]
                cubic=(a,a+spline.tangents[i]['vr']*(4/3),b+spline.tangents[j]['vl']*(4/3),b)
                decoded.append(cubic)
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

    def test_failed_child_does_not_cancel_second(self):
        from test_metaspline import circle
        first,second=Node(spline=object()),Node(spline=object())
        first.GetNext=lambda:second
        self.op.child=first
        path=circle()
        with patch.dict(namespace, {'read_spline':Mock(side_effect=[ValueError('bad child'),[path]]),'make_spline':lambda p:p}):
            self.op[11002]=0
            result=self.plugin.build(self.op)
        self.assertEqual(result,[path])
        self.assertIn('1 child reads skipped',self.plugin.status)

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
