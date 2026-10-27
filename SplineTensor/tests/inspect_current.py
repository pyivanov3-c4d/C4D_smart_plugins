import c4d,runpy,os,sys,json,traceback
root=os.path.dirname(os.path.dirname(__file__));sys.path.insert(0,root)
ns=runpy.run_path(os.path.join(root,'SplineTensor.pyp'),run_name='inspect_scene')
doc=c4d.documents.LoadDocument(os.path.join(root,'tests','Current-scene-repro.c4d'),c4d.SCENEFILTER_OBJECTS,None)
op=doc.GetFirstObject();child=op.GetDown(); data=[]
while child:
 try:
  loops=ns['sample_loops'](child,op)
  data.append(dict(name=child.GetName(),loops=loops))
  print(child.GetName(),'segments',len(loops),'samples',[len(x) for x in loops],flush=True)
 except Exception:traceback.print_exc()
 child=child.GetNext()
with open(os.path.join(root,'tests','current-scene-input.json'),'w') as stream:json.dump(data,stream)
instance=ns['SplineTensor']();result=instance.GetVirtualObjects(op,None)
print('RESULT',result.GetName(),'TYPE',result.GetType(),flush=True)

assert isinstance(result,c4d.PolygonObject),result.GetName()
with open(os.path.join(root,"CURRENT-SCENE-HOST-TEST.json"),"w") as stream:json.dump(dict(passed=True,points=result.GetPointCount(),polygons=result.GetPolygonCount()),stream,indent=2)
