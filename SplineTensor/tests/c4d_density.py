import c4d,runpy,os,sys,json,math,traceback
root=os.path.dirname(os.path.dirname(__file__));sys.path.insert(0,root)
from st_inputs import sample_loops
ns=runpy.run_path(os.path.join(root,'SplineTensor.pyp'),run_name='density_test')
report={'passed':False,'cases':[]}
try:
 doc=c4d.documents.BaseDocument();op=c4d.BaseObject(ns['PLUGIN_ID']);doc.InsertObject(op)
 instance=ns['SplineTensor']();instance.Init(op);assert op[1004]==1
 base=c4d.SplineObject(4,c4d.SPLINETYPE_LINEAR);base[c4d.SPLINEOBJECT_CLOSED]=True
 base.SetAllPoints([c4d.Vector(-50,-50,0),c4d.Vector(50,-50,0),c4d.Vector(50,50,0),c4d.Vector(-50,50,0)]);base.InsertUnderLast(op);base.Message(c4d.MSG_UPDATE)
 circle=c4d.BaseObject(c4d.Osplinecircle);circle[c4d.PRIM_CIRCLE_RADIUS]=15;circle.SetRelPos(c4d.Vector(0,0,5));circle.InsertUnderLast(op)
 doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
 one=sample_loops(circle,op,1)[0];two=sample_loops(circle,op,2)[0]
 assert len(two)==2*len(one)
 assert two[::2]==one
 deviations=[]
 for i in range(len(one)):
  midpoint=tuple((one[i][k]+one[(i+1)%len(one)][k])*.5 for k in range(3))
  deviations.append(math.dist(two[2*i+1],midpoint))
 assert min(deviations)>1e-4, deviations
 report['curved_rim_samples']=[len(one),len(two)];report['min_curve_vs_chord_distance']=min(deviations)
 op[1000]=2
 for mode in (True,False):
  op[1003]=mode
  counts=[]
  for density in (1,2,3):
   op[1004]=density
   mesh=instance.GetVirtualObjects(op,None)
   if not isinstance(mesh,c4d.PolygonObject):
    b=ns['sample'](base,op,density);c=ns['unite_contours'](b,sample_loops(circle,op,density),(0,0,5),nested_masks=True)
    with open(os.path.join(root,'tests/density-failure.json'),'w') as stream:json.dump(dict(base=b,contours=c,density=density,closed=mode),stream)
    ns['build_many'](b,c,2,3,lambda t:op[1002].GetPoint(t).y,closed=mode,quad_bands=True,quality=True,density=density)
    raise AssertionError(mesh.GetName())
   quads=sum(p.c!=p.d for p in mesh.GetAllPolygons())
   assert quads==len(one)*density*4*density*(1 if mode else 2),(quads,density)
   assert mesh.GetTag(c4d.Tuvw) is not None
   count=instance._build_count;instance.GetVirtualObjects(op,None);assert instance._build_count==count
   counts.append(mesh.GetPointCount())
   report['cases'].append(dict(closed=mode,density=density,points=mesh.GetPointCount(),polygons=mesh.GetPolygonCount(),quads=quads))
  assert counts[0]<counts[1]<counts[2]
 # Multi-segment imported spline: all segments retain their original samples.
 saved=c4d.documents.LoadDocument(os.path.join(root,'tests','Mask-experiment.c4d'),c4d.SCENEFILTER_OBJECTS,None)
 saved_op=saved.GetFirstObject();saved_child=saved_op.GetDown().GetNext()
 coarse=sample_loops(saved_child,saved_op,1);fine=sample_loops(saved_child,saved_op,2)
 assert len(coarse)==len(fine)==3
 for a,b in zip(coarse,fine):assert len(b)==2*len(a) and b[::2]==a
 # Exact native parameter correspondence, including later spline segments.
 helper=c4d.utils.SplineHelp();helper.InitSplineWith(saved_child,c4d.SPLINEHELPFLAGS_RETAINLINEOBJECT)
 line=helper.GetLineObject();metadata=line.GetTag(c4d.Tline).GetAllHighlevelData();start=0
 spline=saved_child.GetRealSpline()
 for segment in range(helper.GetSegmentCount()):
  count=helper.GetVertexCount(segment)
  for i in range(start,start+count):
   assert (spline.GetSplinePoint(metadata[i]['t'],segment)-line.GetPoint(i)).GetLength()<1e-5
  start+=count
 report['multisegment_samples']=[[len(a) for a in coarse],[len(b) for b in fine]]
 # Evaluate the saved XOR scene at higher density, including clipping/welding.
 saved=c4d.documents.LoadDocument(os.path.join(root,'tests','Xor-scene.c4d'),c4d.SCENEFILTER_OBJECTS,None)
 saved_op=saved.GetFirstObject();saved_op[1004]=2
 result=ns['SplineTensor']().GetVirtualObjects(saved_op,None)
 assert isinstance(result,c4d.PolygonObject),result.GetName()
 report['xor_density_2']={'points':result.GetPointCount(),'polygons':result.GetPolygonCount()}
 report['passed']=True
except Exception:report['error']=traceback.format_exc()
with open(os.path.join(root,'DENSITY-HOST-TEST.json'),'w') as stream:json.dump(report,stream,indent=2)
print(json.dumps(report,indent=2),flush=True)
