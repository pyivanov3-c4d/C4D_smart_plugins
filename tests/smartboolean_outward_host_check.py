"""Native verification on a copy of Pavel's wrapped Flower intersection."""
import c4d,json,traceback
from pathlib import Path
base=Path(__file__).resolve().parents[1]/'artifacts/smartBoolean'
report={'passed':False};doc=None
try:
    doc=c4d.documents.LoadDocument(str(base/'outward-repro.c4d'),c4d.SCENEFILTER_OBJECTS|c4d.SCENEFILTER_MATERIALS,None)
    assert doc is not None
    op=doc.GetFirstObject();op.SetDirty(c4d.DIRTYFLAGS_DATA)
    doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    mesh=op.GetCache();assert mesh is not None and mesh.CheckType(c4d.Opolygon)
    points=[(v.x,v.y,v.z) for v in mesh.GetAllPoints()]
    faces=[[f.a,f.b,f.c] if f.c==f.d else [f.a,f.b,f.c,f.d] for f in mesh.GetAllPolygons()]
    status=str(mesh[1099001]);assert '1.0.17' in status and 'spatial boundary limits' in status,status
    violations=[i for i,p in enumerate(points) if abs(p[2]-100)<1e-5 and p[0]<-100-1e-6]
    assert not violations,violations
    import smartboolean_cleanup as g
    assert all(len(v)==2 for v in g.edge_map(faces).values())
    import smartboolean_progress as progress
    assert not progress._jobs
    (base/'outward-fixed-native.json').write_text(json.dumps(dict(points=points,polygons=faces,status=status)))
    report.update(passed=True,status=status,points=len(points),polygons=len(faces),outward_front_points=len(violations),closed=True)
except BaseException:
    report['error']=traceback.format_exc();traceback.print_exc()
finally:
    if doc is not None:c4d.documents.KillDocument(doc)
    (base/'outward-host-1.0.17.json').write_text(json.dumps(report,indent=2))
    print('OUTWARD_REPORT',json.dumps(report))
