"""Compare native chamfer shading options without changing geometry."""
import c4d, json, runpy, traceback
from pathlib import Path
root=Path(__file__).resolve().parents[1]
base=root/'artifacts/smartBoolean'
report={'passed':False}
doc=None
try:
    sb=runpy.run_path(str(root/'smartBoolean/smart_boolean.pyp'))
    scope=sb['bevel'].__globals__
    original=scope['command']
    chamfer=scope['chamfer_command']
    results=[]
    for breaks in (True,False):
        counts=[]
        scope['chamfer_command']=(lambda doc,mesh,bc: command(doc,mesh,c4d.ID_XBEVELTOOL,bc,c4d.MODELINGCOMMANDMODE_EDGESELECTION)) if breaks else chamfer
        def command(doc,mesh,cmd,settings=None,mode=None):
            if cmd==c4d.ID_XBEVELTOOL:
                settings[c4d.MDATA_BEVEL_SELECTION_PHONG_BREAK]=breaks
                settings[c4d.MDATA_BEVEL_SELECTION_PHONG_BREAK_M]=breaks
            result=original(doc,mesh,cmd,settings,mode)
            if cmd==c4d.ID_XBEVELTOOL:counts.append(mesh.GetPhongBreak().GetCount())
            return result
        scope['command']=command
        doc=c4d.documents.LoadDocument(str(base/'weld-repro.c4d'),c4d.SCENEFILTER_OBJECTS|c4d.SCENEFILTER_MATERIALS,None)
        op=doc.GetFirstObject()
        # Obtain raw Boolean from the registered generator, then use source bevel.
        op[1001]=0.0
        doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        mesh=op.GetCache().GetClone();doc.InsertObject(mesh)
        mesh=sb['bevel'](doc,mesh,5.0,3,1.0,False)
        points=[(p.x,p.y,p.z) for p in mesh.GetAllPoints()]
        faces=[(p.a,p.b,p.c,p.d) for p in mesh.GetAllPolygons()]
        results.append((points,faces,mesh.GetPhongBreak().GetCount(),counts))
        c4d.documents.KillDocument(doc);doc=None
    report.update(before=results[0][2],after=results[1][2],native_before=results[0][3],native_after=results[1][3])
    assert results[0][:2]==results[1][:2], 'Geometry changed'
    assert results[1][2]<results[0][2], 'No Phong breaks removed'
    report.update(passed=True,before=results[0][2],after=results[1][2],native_before=results[0][3],native_after=results[1][3],geometry_unchanged=True)
except BaseException:
    report['error']=traceback.format_exc()
finally:
    if doc is not None:c4d.documents.KillDocument(doc)
    (base/'phong-host.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))

