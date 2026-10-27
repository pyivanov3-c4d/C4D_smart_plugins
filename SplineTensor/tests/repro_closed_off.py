import c4d,runpy,sys,json,os,traceback
root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,root)
ns=runpy.run_path(os.path.join(root,'SplineTensor.pyp'),run_name='repro')
doc=c4d.documents.LoadDocument(os.path.join(root,'tests','Closed-off-repro.c4d'),c4d.SCENEFILTER_OBJECTS|c4d.SCENEFILTER_MATERIALS,None)
op=doc.GetFirstObject(); first=op.GetDown(); second=first.GetNext()
base=ns['sample'](first,op); contours=[]; child=second
while child:
 contours.append(ns['sample'](child,op)); child=child.GetNext()
delta=second.GetMl().off-first.GetMl().off
payload=dict(base=base,contours=contours,delta=[delta.x,delta.y,delta.z],width=op[1000],subdivisions=op[1001])
with open(os.path.join(root,'tests','closed-off-input.json'),'w') as f:json.dump(payload,f)
try:
 united=ns['unite_contours'](base,contours,payload['delta'])
 result=ns['build_many'](base,united,op[1000],op[1001],lambda t:op[1002].GetPoint(t).y,closed=False,quad_bands=True,return_edges=True,quality=True)
 instance=ns['SplineTensor']()
 mesh=instance.GetVirtualObjects(op,None)
 assert isinstance(mesh,c4d.PolygonObject),mesh.GetName()
 assert mesh.GetPolygonCount()>100
 builds=instance._build_count
 for _ in range(20):instance.GetVirtualObjects(op,None)
 assert instance._build_count==builds
 report=dict(passed=True,points=mesh.GetPointCount(),polygons=mesh.GetPolygonCount(),closed=bool(op[1003]),width=op[1000],unchanged_rebuilds=instance._build_count-builds)
 with open(os.path.join(root,'CLOSED-OFF-HOST-TEST.json'),'w') as stream:json.dump(report,stream,indent=2)
 print(report,flush=True)
except Exception:traceback.print_exc()
