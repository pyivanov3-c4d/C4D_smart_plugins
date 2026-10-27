"""Offline topology/selection regression checks. Does not emulate C4D's engine."""
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

class Selection:
    def __init__(self, selected=()): self.selected=set(selected)
    def DeselectAll(self): self.selected.clear()
    def Merge(self, other): self.selected.update(other.selected)
    def IsSelected(self, i): return i in self.selected
    def Select(self, i): self.selected.add(i)

class Mesh:
    def __init__(self, points, polys):
        self.points=[types.SimpleNamespace(x=x,y=y,z=z) for x,y,z in points]
        self.polys=[types.SimpleNamespace(a=p[0],b=p[1],c=p[2],d=p[-1]) for p in polys]
        self.selection=Selection()
        self.tags=[]
    def GetAllPoints(self): return self.points
    def GetAllPolygons(self): return self.polys
    def GetPolygonCount(self): return len(self.polys)
    def GetEdgeS(self): return self.selection
    def GetTags(self): return self.tags

fake=types.ModuleType('c4d')
fake.plugins=types.SimpleNamespace(ObjectData=object)
fake.bitmaps=fake.documents=fake.utils=types.SimpleNamespace()
fake.Tedgeselection=5701
fake.Tpoint,fake.Tpolygon,fake.Tphong=5600,5604,5612
fake.Tnormal,fake.Ttexture,fake.Tuvw=5711,5616,5671
fake.TEXTURETAG_RESTRICTION=1001
fake.HIERARCHYCLONEFLAGS_ASPOLY=1
with patch.dict(sys.modules, {'c4d':fake}):
    sb=runpy.run_path(str(Path(__file__).resolve().parents[1]/'smartBoolean/smart_boolean.pyp'))

def tetra():
    return Mesh([(0,0,0),(1,0,0),(0,1,0),(0,0,1)],
                [(0,2,1),(0,1,3),(1,2,3),(2,0,3)])

class TopologyTests(unittest.TestCase):
    def test_cached_generator_does_not_start_progress(self):
        op=MagicMock();cached=object()
        op.GetAndCheckHierarchyClone.return_value={'dirty':False,'clone':cached}
        with patch.object(sb['progress_ui'],'Progress') as progress:
            result=sb['SmartBoolean'].GetVirtualObjects(object(),op,MagicMock())
        self.assertIs(result,cached);progress.assert_not_called()

    def test_conversion_progress_closes_on_error(self):
        job=Mock()
        fn=sb['convert_and_hide']
        with patch.object(sb['progress_ui'],'Progress',return_value=job),patch.dict(fn.__globals__,_convert_and_hide=Mock(side_effect=RuntimeError('failed'))):
            with self.assertRaises(RuntimeError):fn(Mock())
        job.stage.assert_called_once();job.close.assert_called_once()

    def test_generator_cancellation_always_closes_progress(self):
        op=MagicMock();op.GetAndCheckHierarchyClone.return_value={'dirty':True,'clone':Mock()}
        job=Mock();job.stage.side_effect=sb['progress_ui'].Cancelled()
        empty=object()
        with patch.object(sb['progress_ui'],'Progress',return_value=job),patch.object(fake,'threading',types.SimpleNamespace(GeGetCurrentThread=lambda:None),create=True):
            result=sb['SmartBoolean'].GetVirtualObjects(object(),op,MagicMock())
        self.assertIsNone(result);job.close.assert_called_once()

    def test_convert_and_hide_preserves_source_and_orders_copy(self):
        fn=sb['_convert_and_hide'];op=MagicMock();child=MagicMock();grandchild=MagicMock();copy=MagicMock()
        op.GetDown.return_value=child;child.GetDown.return_value=grandchild
        child.GetNext.return_value=None;grandchild.GetDown.return_value=None;grandchild.GetNext.return_value=None
        copy.GetDown.return_value=None;copy.CheckType.return_value=True;copy.GetPolygonCount.return_value=4
        op.GetName.return_value='Boolean';doc=op.GetDocument.return_value
        constants=dict(threading=types.SimpleNamespace(GeIsMainThread=lambda:True),StopAllThreads=Mock(),
            MCOMMAND_CURRENTSTATETOOBJECT=245,Opolygon=5100,MODE_UNDEF=2,MODE_OFF=1,
            UNDOTYPE_NEWOBJ=1,UNDOTYPE_CHANGE=2,SELECTION_NEW=0,EventAdd=Mock())
        def evaluate(*args):
            for node in (op,child,grandchild):node.SetDeformMode.assert_not_called()
            return [copy]
        with patch.multiple(fake,create=True,**constants),patch.dict(fn.__globals__,command=Mock(side_effect=evaluate)):
            self.assertIs(fn(op),copy)
        doc.InsertObject.assert_called_once_with(copy,parent=op.GetUp(),pred=op)
        copy.SetMl.assert_called_once_with(op.GetMl())
        copy.SetName.assert_called_once_with('Boolean (converted)')
        for node in (op,child,grandchild):
            node.SetDeformMode.assert_called_once_with(False)
            node.SetEditorMode.assert_called_once_with(1)
            node.SetRenderMode.assert_called_once_with(1)
        self.assertEqual(doc.AddUndo.call_count,4)
        doc.StartUndo.assert_called_once();doc.EndUndo.assert_called_once()

    def test_failed_conversion_does_not_hide_source(self):
        fn=sb['_convert_and_hide'];op=MagicMock()
        with patch.multiple(fake,create=True,threading=types.SimpleNamespace(GeIsMainThread=lambda:True),
                StopAllThreads=Mock(),MCOMMAND_CURRENTSTATETOOBJECT=245),patch.dict(fn.__globals__,command=Mock(return_value=False)):
            with self.assertRaises(RuntimeError):fn(op)
        op.SetDeformMode.assert_not_called();op.SetEditorMode.assert_not_called()
        op.GetDocument().StartUndo.assert_not_called()

    def test_points_remove_default_is_off(self):
        op={}
        self.assertTrue(sb['SmartBoolean'].Init(types.SimpleNamespace(InitAttr=lambda *a:None),op))
        self.assertIs(op[sb['POINTS_REMOVE']],False)
    def test_points_remove_controls_both_heavy_passes(self):
        import re
        source=(Path(__file__).resolve().parents[1]/'smartBoolean/smart_boolean.pyp').read_text(encoding='utf-8-sig')
        constants={name:name for name in re.findall(r'c4d\.((?:MDATA_|MODELINGCOMMANDMODE_|ID_XBEVEL)[A-Z_0-9]*)',source)}
        constants['BaseContainer']=dict
        fn=sb['bevel']; context=fn.__globals__
        for enabled in (False,True):
            mesh=MagicMock(); candidate=MagicMock(); mesh.GetClone.return_value=candidate
            mesh.GetRad.return_value.GetLength.return_value=100.
            candidate.GetTags.return_value=[]
            prepare=Mock(return_value=mesh); finish=Mock(return_value=candidate)
            with patch.multiple(fake,create=True,**constants),patch.dict(context,
                seam_selection=Mock(return_value=1),sound_mesh=Mock(return_value=True),
                mesh_arrays=Mock(return_value=([],[])),
                command=Mock(return_value=True),prepare_bevel=prepare,finish_bevel=finish):
                fn(MagicMock(),mesh,10,3,1,enabled)
            self.assertEqual(prepare.call_count,int(enabled))
            self.assertEqual(finish.call_count,int(enabled))
    def test_native_geometry_storage_does_not_disable_retopology(self):
        mesh=tetra()
        def tag(kind,name=''):
            return types.SimpleNamespace(GetType=lambda:kind,
                CheckType=lambda t:t==kind,GetName=lambda:name)
        # Exact tag inventory observed on the user's evaluated mesh.
        mesh.tags=[tag(fake.Tphong),tag(fake.Tedgeselection,sb['SEAM']),
                   tag(fake.Tuvw),tag(fake.Tpolygon),tag(fake.Tpoint)]
        self.assertTrue(sb['topology_tags_supported'](mesh))
        mesh.tags.append(tag(999999))
        self.assertFalse(sb['topology_tags_supported'](mesh))
    def test_closed_tetrahedron(self):
        self.assertTrue(sb['sound_mesh'](tetra(),True))
    def test_hole_rejected_for_closed_input(self):
        mesh=tetra(); mesh.polys.pop()
        self.assertFalse(sb['sound_mesh'](mesh,True))
        self.assertTrue(sb['sound_mesh'](mesh,False))
    def test_nonmanifold_rejected(self):
        mesh=tetra(); mesh.polys.append(mesh.polys[0])
        self.assertFalse(sb['sound_mesh'](mesh))
    def test_nan_rejected(self):
        mesh=tetra(); mesh.points[0].x=float('nan')
        self.assertFalse(sb['sound_mesh'](mesh))
    def test_empty_bevel_result_rejected(self):
        self.assertFalse(sb['sound_mesh'](Mesh([],[]),True))
    def test_out_of_range_face_rejected(self):
        mesh=tetra(); mesh.polys[0].a=8
        self.assertFalse(sb['sound_mesh'](mesh))
    def test_seam_selects_both_sides_only(self):
        mesh=tetra()
        tag=types.SimpleNamespace(CheckType=lambda t:t==5701,
            GetName=lambda:sb['SEAM'],GetBaseSelect=lambda:Selection([3]))
        mesh.tags=[tag]
        self.assertEqual(sb['seam_selection'](mesh),1)
        self.assertEqual(mesh.selection.selected,{3,4})
    def test_no_intersection_does_not_bevel_all_edges(self):
        mesh=tetra(); mesh.selection.Select(0)
        self.assertIs(sb['bevel'](None,mesh,10,3,1),mesh)
        self.assertEqual(mesh.selection.selected,set())
    def test_zero_width_bypasses_modeling(self):
        mesh=tetra()
        self.assertIs(sb['bevel'](None,mesh,0,3,1),mesh)

if __name__=='__main__': unittest.main()
