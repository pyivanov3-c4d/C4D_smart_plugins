"""Run in c4dpy against the installed plugin; isolated document only."""
import c4d,json,traceback,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'artifacts/smartBoolean/progress-host-1.0.16.json'
report={'passed':False,'checks':[]}
doc=None
try:
    import smartboolean_progress as progress
    calls=[];original=progress.Progress.stage
    def stage(self,*args,**kwargs):
        calls.append(args[0]);return original(self,*args,**kwargs)
    progress.Progress.stage=stage
    doc=c4d.documents.BaseDocument()
    op=c4d.BaseObject(1069992);assert op is not None
    doc.InsertObject(op);op[1000]=1;op[1001]=3.;op[1002]=3
    for offset in (0.,25.):
        cube=c4d.BaseObject(c4d.Ocube);cube[c4d.PRIM_CUBE_LEN]=c4d.Vector(50)
        cube.SetRelPos(c4d.Vector(offset,offset,offset));cube.InsertUnderLast(op)
    doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    mesh=op.GetCache()
    assert mesh is not None and mesh.CheckType(c4d.Opolygon) and mesh.GetPolygonCount()>0
    assert '1.0.16' in str(mesh[1099001]),str(mesh[1099001])
    assert calls and not progress._jobs
    report['checks'].append('native Boolean/bevel callback completed; progress closed')
    report['polygons']=mesh.GetPolygonCount();report['status']=str(mesh[1099001])
    before=len(calls)
    doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    assert len(calls)==before,'Cached result reported calculation progress'
    report['checks'].append('cached native evaluation did not start progress')
    assert c4d.plugins.FindPlugin(progress.PROGRESS_ID,c4d.PLUGINTYPE_ANY) is not None
    report['checks'].append('main-thread progress message plugin registered')
    report['passed']=True
except BaseException:
    report['error']=traceback.format_exc();traceback.print_exc()
finally:
    if doc is not None:c4d.documents.KillDocument(doc)
    out.write_text(json.dumps(report,indent=2))
    print('SMARTBOOLEAN_PROGRESS_REPORT',json.dumps(report))
