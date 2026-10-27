import c4d,runpy,os,sys,json
root=os.path.dirname(os.path.dirname(__file__));sys.path.insert(0,root)
ns=runpy.run_path(os.path.join(root,'SplineTensor.pyp'),run_name='diagnostic')
doc=c4d.documents.LoadDocument(os.path.join(root,'tests','Shading-20261022.c4d'),c4d.SCENEFILTER_OBJECTS,None)
op=doc.GetFirstObject();first=op.GetDown();second=first.GetNext()
base=ns['sample'](first,op);loops=ns['sample_loops'](second,op);d=second.GetMl().off-first.GetMl().off
contours=ns['unite_contours'](base,loops,(d.x,d.y,d.z))
curve=op[ns['CURVE']];profile=lambda t:curve.GetPoint(t).y
p,f,e=ns['build_many'](base,contours,op[1000],op[1001],profile,closed=True,quality=True,quad_bands=True,return_edges=True)
with open(os.path.join(root,'tests','shading-input.json'),'w') as s:json.dump(dict(base=base,contours=contours,profile=[profile(i/1000) for i in range(1001)],points=p,faces=f,creases=e),s)
print('EXPORTED',len(p),len(f),flush=True)
