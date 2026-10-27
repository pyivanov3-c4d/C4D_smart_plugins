"""Regression for editor cancellations being committed as valid empty caches."""
import c4d
import json
import sys
import time
import traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'NoiseSpread'))
import noisespread_geometry as geometry
OUT=ROOT/'artifacts/noisespread'
report={'passed':False,'checks':[]}
real_pack=geometry.pack
real_thread=c4d.threading.GeGetCurrentThread

def count(op):
    cache=op.GetCache()
    node=cache.GetDown() if cache else None
    total=0
    while node:
        total+=int(node.CheckType(c4d.Oinstance)); node=node.GetNext()
    return total

def make_doc():
    doc=c4d.documents.BaseDocument(); op=c4d.BaseObject(1069993); doc.InsertObject(op)
    surface=c4d.BaseObject(c4d.Oplane); surface[c4d.PRIM_PLANE_WIDTH]=160; surface[c4d.PRIM_PLANE_HEIGHT]=160
    surface.InsertUnderLast(op)
    source=c4d.BaseObject(c4d.Osphere); source[c4d.PRIM_SPHERE_RAD]=8; source.InsertUnderLast(op)
    return doc,op

def passes(doc): doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)

try:
    # Cancel during packing, then resume without touching a user parameter.
    doc,op=make_doc()
    geometry.pack=lambda *a,**k:([],'Cancelled; partial packing')
    passes(doc)
    assert op.GetCache() is None,'Cancellation was committed as a valid cache'
    geometry.pack=real_pack
    passes(doc)
    assert count(op)>80,'Next pass did not retry the cancelled build'
    report['checks'].append('packing cancellation leaves cache invalid; next pass recovers automatically')
    # Cancel after packing but before the first instance is created (reported bug).
    doc,op=make_doc()
    geometry.pack=lambda *a,**k:([((0,0,0),8,(0,1,0),0,1,0,(1,0,0))],'Packing complete')
    class CancelledThread:
        def TestBreak(self): return True
    c4d.threading.GeGetCurrentThread=lambda:CancelledThread()
    passes(doc)
    assert op.GetCache() is None,'Instance-construction cancellation committed an empty cache'
    c4d.threading.GeGetCurrentThread=real_thread
    geometry.pack=real_pack
    passes(doc)
    assert count(op)>80
    report['checks'].append('instance-build cancellation leaves cache invalid; next pass recovers automatically')
    # Real scene from the latest user report, with primitive surface/source.
    repro=c4d.documents.LoadDocument(str(OUT/'user-repro-101.c4d'),c4d.SCENEFILTER_OBJECTS|c4d.SCENEFILTER_MATERIALS,None)
    started=time.perf_counter(); passes(repro)
    op=repro.GetFirstObject()
    report['scene_instances']=count(op); report['evaluation_seconds']=round(time.perf_counter()-started,3)
    assert count(op)>100
    assert op.GetCache().GetDown().CheckType(c4d.Opolygon)
    before=count(op); passes(repro); assert count(op)==before
    report['checks'].append('latest user scene generates stable instances with the first surface visible')
    report['passed']=True
except BaseException: report['error']=traceback.format_exc(); traceback.print_exc()
finally:
    geometry.pack=real_pack
    c4d.threading.GeGetCurrentThread=real_thread
    (OUT/'cancel-host-check.json').write_text(json.dumps(report,indent=2))
    print('NOISESPREAD_CANCEL_REPORT',json.dumps(report))
