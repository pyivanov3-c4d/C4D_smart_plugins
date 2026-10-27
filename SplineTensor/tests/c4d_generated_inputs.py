"""Host regression for generated and multi-segment spline inputs."""
import c4d,os,sys,runpy,json,traceback
root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,root)
ns=runpy.run_path(os.path.join(root,'SplineTensor.pyp'),run_name='generated_test')
report={'passed':False,'checks':[]}
try:
 assert c4d.plugins.FindPlugin(1051122,c4d.PLUGINTYPE_OBJECT),'Outline plugin not loaded'
 doc=c4d.documents.LoadDocument(os.path.join(root,'tests','Outline-repro.c4d'),c4d.SCENEFILTER_OBJECTS,None)
 op=doc.GetFirstObject(); outline=op.GetDown().GetNext()
 loops=ns['sample_loops'](outline,op)
 assert len(loops)==2,len(loops)
 # The output must include the actual offset, not just the original Circle.
 original=ns['sample_loops'](outline.GetDown(),op)[0]
 bounds=lambda points:tuple((round(min(p[k] for p in points),5),round(max(p[k] for p in points),5)) for k in range(3))
 assert any(bounds(loop)!=bounds(original) for loop in loops)
 instance=ns['SplineTensor']()
 result=instance.GetVirtualObjects(op,None)
 assert isinstance(result,c4d.PolygonObject),result.GetName()
 report['checks'].append('Actual Outline output: two closed segments, offset geometry retained')
 initial=ns['geometry_key'](op); previous=result.GetAllPoints()
 circle=outline.GetDown();circle[c4d.PRIM_CIRCLE_RADIUS]*=.9;circle.Message(c4d.MSG_UPDATE)
 assert ns['geometry_key'](op)!=initial
 result=instance.GetVirtualObjects(op,None)
 assert isinstance(result,c4d.PolygonObject),result.GetName()
 assert result.GetAllPoints()!=previous
 report['checks'].append('Nested Circle radius edit invalidates cache and changes relief')
 initial=ns['geometry_key'](op)
 outline[10000]=int(outline[10000])+2
 assert ns['geometry_key'](op)!=initial
 assert isinstance(instance.GetVirtualObjects(op,None),c4d.PolygonObject)
 report['checks'].append('Outline distance edit refreshes output')
 builds=instance._build_count
 for _ in range(50):instance.GetVirtualObjects(op,None)
 assert instance._build_count==builds
 report['checks'].append('50 unchanged generated-input evaluations: no rebuilds')
 # Native document evaluation catches recursion or threading failures.
 doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
 assert isinstance(op.GetCache(),c4d.PolygonObject),op.GetCache()
 report['checks'].append('Native generator evaluation with Outline')
 # Connect several translated splines; each closed segment becomes a contour.
 connect=c4d.BaseObject(c4d.Oconnector); connect.SetName('Connect')
 connect.InsertUnderLast(op);connect.SetRelPos(outline.GetRelPos())
 for x in (-70,70):
  item=c4d.BaseObject(c4d.Osplinecircle);item[c4d.PRIM_CIRCLE_RADIUS]=25
  item[c4d.PRIM_PLANE]=c4d.PRIM_PLANE_XZ
  item.SetRelPos(c4d.Vector(x,0,0));item.InsertUnderLast(connect)
 loops=ns['sample_loops'](connect,op)
 assert len(loops)==2,len(loops)
 centers=[sum(p[0] for p in loop)/len(loop) for loop in loops]
 assert abs(abs(centers[1]-centers[0])-140)<1e-4,centers
 outline.Remove()
 op[1000]=5
 result=instance.GetVirtualObjects(op,None)
 assert isinstance(result,c4d.PolygonObject),result.GetName()
 report['checks'].append('Connect output: both segments and nested transforms preserved')
 initial=ns['geometry_key'](op)
 connect.GetDown().SetRelPos(c4d.Vector(-80,0,0))
 assert ns['geometry_key'](op)!=initial
 doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
 assert isinstance(op.GetCache(),c4d.PolygonObject),op.GetCache()
 report['checks'].append('Nested Connect movement updates native output')
 stable=op.GetCache().GetGUID()
 for _ in range(20):doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
 assert op.GetCache().GetGUID()==stable
 report['checks'].append('20 unchanged native Connect evaluations preserve the same cache')
 report['passed']=True
except Exception:report['error']=traceback.format_exc()
with open(os.path.join(root,'GENERATED-INPUT-HOST-TEST.json'),'w') as stream:json.dump(report,stream,indent=2)
print(json.dumps(report,indent=2),flush=True)

