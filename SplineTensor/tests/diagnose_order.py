import c4d,runpy,os,sys
root=os.path.dirname(os.path.dirname(__file__));sys.path.insert(0,root)
ns=runpy.run_path(os.path.join(root,'SplineTensor.pyp'),run_name='diagnostic')
doc=c4d.documents.LoadDocument(os.path.join(root,'tests','Scene-current-diagnostic.c4d'),c4d.SCENEFILTER_OBJECTS,None)
op=doc.GetFirstObject();first=op.GetDown();second=first.GetNext()
second.Remove();second.InsertUnder(op)
result=ns['SplineTensor']().GetVirtualObjects(op,None)
print('SWAPPED RESULT',result.GetName(),flush=True)
if isinstance(result,c4d.PolygonObject):print('POINTS',result.GetPointCount(),'POLYGONS',result.GetPolygonCount(),flush=True)
