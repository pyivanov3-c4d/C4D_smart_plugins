"""Run with c4dpy.exe, outside generator callbacks and outside the MCP bridge."""
import c4d
import json
import sys
import traceback
from pathlib import Path

root=Path(__file__).resolve().parents[1]
report={'passed':False,'checks':[],'cases':{}}
doc=None
try:
    import metaspline_progress as progress
    calls=[];original=progress.Progress.stage
    def record(self,*args,**kwargs):
        calls.append(args[0]);return original(self,*args,**kwargs)
    progress.Progress.stage=record
    doc=c4d.documents.BaseDocument()
    op=c4d.BaseObject(1069991)
    assert op is not None,'Metaspline registration missing'
    doc.InsertObject(op)
    children=[]
    for x in (0.,115.):
        child=c4d.BaseObject(c4d.Osplinecircle)
        child[c4d.PRIM_CIRCLE_RADIUS]=50.
        child.SetRelPos(c4d.Vector(x,0,0));child.InsertUnderLast(op);children.append(child)
    op[11000]=20.;op[11001]=40.;op[11002]=0.
    def evaluate():
        doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        spline=op.GetRealSpline()
        assert spline is not None and spline.IsClosed()
        assert spline.GetPointCount()>0
        return spline
    bridge=evaluate()
    assert bridge.GetSegmentCount()==1,bridge.GetSegmentCount()
    report['cases']['bridge_points']=bridge.GetPointCount()
    assert calls and not progress._jobs
    report['checks'].append('Registered generator: closed native spline bridge; progress cleared')
    before=len(calls);evaluate()
    assert len(calls)==before,'Cached result recalculated/reported progress'
    report['checks'].append('Cached evaluation leaves status untouched')
    assert op[11004]==.25,'Viscosity default missing'
    op[11004]=0.;low=list(evaluate().GetAllPoints())
    op[11004]=1.;high=list(evaluate().GetAllPoints())
    assert low!=high,'Viscosity did not invalidate native result'
    op[11004]=.25
    report['checks'].append('Viscosity default and native parameter edits rebuild geometry')
    children[1].SetRelPos(c4d.Vector(155,0,0));op[11001]=100.
    fallow=evaluate();assert fallow.GetSegmentCount()==2
    report['cases']['fallow_points']=fallow.GetPointCount()
    children[1].SetRelPos(c4d.Vector(80,0,0));op[11000]=0.;op[11001]=0.
    united=evaluate();assert united.GetSegmentCount()==1
    report['checks'].append('Native Circle children: overlap union and non-welded Fallow')
    op[11002]=1.;rounded=evaluate()
    report['cases']['round_points']=rounded.GetPointCount()
    children[0][c4d.PRIM_CIRCLE_RADIUS]=45.
    children[1][c4d.PRIM_CIRCLE_RADIUS]=20.
    op[11000]=20.;op[11001]=60.;op[11002]=0.
    for gap in (20.1,19.9,8.,-5.):
        children[1].SetRelPos(c4d.Vector(65+gap,0,0))
        transition=evaluate()
        assert transition.GetSegmentCount()==(2 if gap>20 else 1)
    report['checks'].append('Fixed-control native progression: separate bulges, thin neck, thick neck, overlap')
    # Native Text exercises original font Beziers and multiple closed contours.
    for child in children:child.Remove()
    text=c4d.BaseObject(c4d.Osplinetext);text[c4d.PRIM_TEXT_TEXT]='B8';text.InsertUnder(op)
    op[11002]=0.
    letters=evaluate();assert letters.GetSegmentCount()>=4
    report['checks'].append('Native Text with counters: closed multi-contour output')
    extrude=c4d.BaseObject(c4d.Oextrude);doc.InsertObject(extrude);op.Remove();op.InsertUnder(extrude)
    doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    assert extrude.GetCache() is not None,'Extrude did not consume the output spline'
    assert not progress._jobs
    report['checks'].append('Native Extrude consumes output')
    assert c4d.plugins.FindPlugin(progress.PROGRESS_ID,c4d.PLUGINTYPE_ANY) is not None
    report['checks'].append('Main-thread progress message plugin registered')
    report['passed']=True
except BaseException:
    report['error']=traceback.format_exc();traceback.print_exc()
finally:
    if doc is not None:c4d.documents.KillDocument(doc)
    path=root/'artifacts/metaspline/host-check-2.2.1.json'
    path.write_text(json.dumps(report,indent=2))
    print('METASPLINE_HOST_REPORT',json.dumps(report))
sys.exit(0 if report['passed'] else 1)
