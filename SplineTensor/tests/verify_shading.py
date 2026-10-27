import c4d,runpy,os,sys,json,traceback
root=os.path.dirname(os.path.dirname(__file__));sys.path.insert(0,root)
ns=runpy.run_path(os.path.join(root,'SplineTensor.pyp'),run_name='inspect_scene')
doc=c4d.documents.LoadDocument(os.path.join(root,'tests','Shading-20261022.c4d'),c4d.SCENEFILTER_OBJECTS,None)
op=doc.GetFirstObject();child=op.GetDown(); data=[]
while child:
 try:
  loops=ns['sample_loops'](child,op)
  data.append(dict(name=child.GetName(),loops=loops))
  print(child.GetName(),'segments',len(loops),'samples',[len(x) for x in loops],flush=True)
 except Exception:traceback.print_exc()
 child=child.GetNext()
with open(os.path.join(root,'tests','shading-host-input.json'),'w') as stream:json.dump(data,stream)
instance=ns['SplineTensor']();result=instance.GetVirtualObjects(op,None)
print('RESULT',result.GetName(),'TYPE',result.GetType(),flush=True)

assert isinstance(result,c4d.PolygonObject),result.GetName()
reports=[]
for closed in (True,False):
 op[ns['CLOSED']]=closed
 instance=ns['SplineTensor']()
 result=instance.GetVirtualObjects(op,None)
 assert isinstance(result,c4d.PolygonObject),result.GetName()
 uv=result.GetTag(c4d.Tuvw)
 assert uv is not None and uv.GetDataCount()==result.GetPolygonCount()
 for i in range(result.GetPolygonCount()):
  for p in uv.GetSlow(i).values():assert 0<=p.x<=1 and 0<=p.y<=1 and p.z==0
 from st_uv import planar_uvs
 expected=planar_uvs(data[0]['loops'][0],[(p.x,p.y,p.z) for p in result.GetAllPoints()])
 for i,poly in enumerate(result.GetAllPolygons()):
  actual=uv.GetSlow(i)
  for key,index in zip(('a','b','c','d'),(poly.a,poly.b,poly.c,poly.d)):
   assert (actual[key]-c4d.Vector(*expected[index])).GetLength()<1e-6
 again=instance.GetVirtualObjects(op,None)
 assert instance._build_count==1 and again.GetTag(c4d.Tuvw) is not None
 reports.append(dict(closed=closed,points=result.GetPointCount(),polygons=result.GetPolygonCount(),uv=True,cache=True))
with open(os.path.join(root,"SHADING-SCENE-HOST-TEST.json"),"w") as stream:json.dump(dict(passed=True,points=result.GetPointCount(),polygons=result.GetPolygonCount()),stream,indent=2)
with open(os.path.join(root,"SHADING-UV-HOST-TEST.json"),"w") as stream:json.dump(dict(passed=True,cases=reports),stream,indent=2)
