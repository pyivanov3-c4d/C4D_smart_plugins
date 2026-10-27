"""Verify actual native point welding on the saved user scene."""
import c4d,json,traceback
from pathlib import Path
base=Path(__file__).resolve().parents[1]/'artifacts/smartBoolean'
report={'passed':False};doc=None
try:
    doc=c4d.documents.LoadDocument(str(base/'weld-repro.c4d'),c4d.SCENEFILTER_OBJECTS|c4d.SCENEFILTER_MATERIALS,None)
    assert doc is not None
    op=doc.GetFirstObject();op.SetDirty(c4d.DIRTYFLAGS_DATA)
    doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    mesh=op.GetCache();assert mesh is not None and mesh.CheckType(c4d.Opolygon)
    status=str(mesh[1099001]);assert '1.0.18' in status and 'welded' in status,status
    points=[(p.x,p.y,p.z) for p in mesh.GetAllPoints()]
    faces=[[f.a,f.b,f.c] if f.c==f.d else [f.a,f.b,f.c,f.d] for f in mesh.GetAllPolygons()]
    import smartboolean_cleanup as g
    import smartboolean_weld as w
    read=lambda name:json.loads((base/(name+'.json')).read_text())
    before,ref,setup=read('weld-current'),read('weld-reference'),read('weld-source')
    setup['seam']={tuple(e) for e in setup['seam']}
    expected,mapping,rebuilt=w.resolve(before['points'],ref['first'],ref['second'],before['polygons'],setup)
    assert len(points)==len(before['points'])-len(mapping),(len(points),len(before['points']),len(mapping))
    # Optimize may retriangulate planar n-gons, so polygon counts can differ.
    assert len(faces)<=len(rebuilt),(len(faces),len(rebuilt))
    quantize=lambda p:tuple(round(v,6) for v in p)
    used={v for f in rebuilt for v in f}
    assert {quantize(p) for p in points}=={quantize(expected[v]) for v in used}
    def volume(p,polys):
        return sum(g.dot(p[f[0]],g.cross(p[f[i]],p[f[i+1]]))/6
                   for f in polys for i in range(1,len(f)-1))
    expected_volume=volume(expected,rebuilt)
    actual_volume=volume(points,faces)
    assert abs(expected_volume-actual_volume)<max(1e-6,abs(expected_volume)*1e-9),(expected_volume,actual_volume)
    for representative in set(mapping.values()):
        assert sum(g.length(g.sub(p,expected[representative]))<1e-6 for p in points)==1
    assert all(len(s)==2 for s in g.edge_map(faces).values())
    import smartboolean_progress as progress
    assert not progress._jobs
    report.update(passed=True,status=status,points=len(points),polygons=len(faces),merged=len(mapping),closed=True)
    (base/'weld-fixed-native.json').write_text(json.dumps(dict(points=points,polygons=faces,status=status)))
except BaseException:
    report['error']=traceback.format_exc();traceback.print_exc()
finally:
    if doc is not None:c4d.documents.KillDocument(doc)
    (base/'weld-host-1.0.18.json').write_text(json.dumps(report,indent=2))
    print('WELD_REPORT',json.dumps(report))
