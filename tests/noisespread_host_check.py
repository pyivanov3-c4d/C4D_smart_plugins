"""Run with Cinema 4D 2026 c4dpy, with NoiseSpread installed. Uses isolated docs."""
import c4d
import json
import math
from pathlib import Path
import traceback

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/noisespread'
report={'version':c4d.GetC4DVersion(),'checks':[]}

def children(obj):
    result=[]; obj=obj.GetDown() if obj else None
    while obj:
        if obj.CheckType(c4d.Oinstance): result.append(obj)
        obj=obj.GetNext()
    return result

def run():
    op=c4d.BaseObject(1069993)
    assert op is not None,'Plugin failed to register'
    report['checks'].append('plugin registration')
    assert op[11000]==1. and op[11001]==0.
    assert op[11002] and op[11002][c4d.SLA_NOISE_SPACE]==c4d.SLA_NOISE_SPACE_WORLD
    desc=op.GetDescription(c4d.DESCFLAGS_DESC_0)
    assert desc.GetParameter(c4d.DescID(11000)) is not None
    report['checks'].append('resources, defaults and native World Noise')
    doc=c4d.documents.BaseDocument(); doc.InsertObject(op)
    surface=c4d.PolygonObject(4,1)
    surface.SetAllPoints([c4d.Vector(-80,0,-80),c4d.Vector(-80,0,80),c4d.Vector(80,0,80),c4d.Vector(80,0,-80)])
    surface.SetPolygon(0,c4d.CPolygon(0,1,2,3)); surface.SetName('Surface'); surface.InsertUnderLast(op)
    tag=c4d.SelectionTag(c4d.Tpolygonselection); tag.SetName('Allowed'); tag.GetBaseSelect().Select(0); surface.InsertTag(tag)
    sphere=c4d.BaseObject(c4d.Osphere); sphere[c4d.PRIM_SPHERE_RAD]=8.; sphere.SetName('Source'); sphere.InsertUnderLast(op)
    def evaluate():
        op.SetDirty(c4d.DIRTYFLAGS_DATA)
        doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        result=children(op.GetCache())
        assert result,'Empty generator cache'
        return result
    a=evaluate()
    visible_surface=op.GetCache().GetDown()
    assert visible_surface.CheckType(c4d.Opolygon)
    assert visible_surface.GetEditorMode()!=c4d.MODE_OFF and visible_surface.GetRenderMode()!=c4d.MODE_OFF
    assert not visible_surface.GetBit(c4d.BIT_CONTROLOBJECT)
    assert op.GetRad().y>=8.,'Bounds must include the instance extent above the plane'
    report['checks'].append('visible first surface and complete instance bounds')
    report['uniform_count']=len(a)
    assert len(a)>80
    assert all(o.CheckType(c4d.Oinstance) and o[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE]==c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE_SINGLEINSTANCE for o in a)
    assert all(o[c4d.INSTANCEOBJECT_LINK] is not None and o[c4d.INSTANCEOBJECT_LINK].GetName()=='Source [prototype]' for o in a)
    assert all(abs(o.GetMl().v2.y-1)<1e-6 for o in a)
    report['checks'].append('evaluated primitive source, render-instance links, normal alignment')
    op[11001]=.5; b=evaluate()
    values=[o.GetMl().v2.GetLength() for o in b]
    report['noise_count']=len(b); report['scale_range']=[min(values),max(values)]
    assert max(values)-min(values)>.05
    for i,o in enumerate(b):
        for q in b[i+1:]:
            assert (o.GetMl().off-q.GetMl().off).GetLength()+1e-5 >= 8*(o.GetMl().v2.GetLength()+q.GetMl().v2.GetLength())
    report['checks'].append('native Noise variation and radius clearance')
    def positions(objects): return [(o.GetMl().off.x,o.GetMl().off.y,o.GetMl().off.z) for o in objects]
    before=positions(b)
    op[11002][c4d.SLA_NOISE_GLOBAL_SCALE]=2.
    c=evaluate(); assert positions(c)!=before
    report['checks'].append('native Noise global scale changes placement')
    op[11003]='Allowed'; assert evaluate()
    op[11003]='Missing'; op.SetDirty(c4d.DIRTYFLAGS_DATA)
    doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    assert not children(op.GetCache())
    assert op.GetCache().GetDown().CheckType(c4d.Opolygon),'Invalid selection must keep the surface visible'
    op[11003]=''; op[11001]=.5; evaluate()
    report['checks'].append('named polygon selection and missing-selection rejection')
    mat=c4d.BaseMaterial(c4d.Mmaterial); mat.SetName('Mesher blue'); mat[c4d.MATERIAL_COLOR_COLOR]=c4d.Vector(1/255,152/255,252/255); doc.InsertMaterial(mat)
    texture=c4d.TextureTag(); texture.SetMaterial(mat); sphere.InsertTag(texture)
    camera=c4d.BaseObject(c4d.Ocamera); camera.SetName('Top view')
    camera.SetMg(c4d.Matrix(c4d.Vector(0,340,0),c4d.Vector(1,0,0),c4d.Vector(0,0,1),c4d.Vector(0,-1,0)))
    doc.InsertObject(camera); doc.GetActiveBaseDraw().SetSceneCamera(camera)
    doc.GetRenderBaseDraw().SetSceneCamera(camera)
    light=c4d.BaseObject(c4d.Olight); light.SetAbsPos(c4d.Vector(0,200,0)); doc.InsertObject(light)
    rd=doc.GetActiveRenderData(); rd[c4d.RDATA_XRES]=700; rd[c4d.RDATA_YRES]=700
    rd[c4d.RDATA_RENDERENGINE]=c4d.RDATA_RENDERENGINE_STANDARD
    path=str(OUT/'NoiseSpread-demo.c4d')
    assert c4d.documents.SaveDocument(doc,path,c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,c4d.FORMAT_C4DEXPORT)
    report['checks'].append('demo scene saved')
    bitmap=c4d.bitmaps.BaseBitmap(); bitmap.Init(700,700)
    rendered=c4d.documents.RenderDocument(doc,rd.GetDataInstance(),bitmap,c4d.RENDERFLAGS_EXTERNAL)
    report['render_result']=int(rendered)
    if rendered==c4d.RENDERRESULT_OK:
        bitmap.Save(str(OUT/'host-preview.png'),c4d.FILTER_PNG)
        report['nonblack_pixels']=sum(max(bitmap.GetPixel(x,y))>2 for x in range(0,700,4) for y in range(0,700,4))
        assert report['nonblack_pixels']>100,'Render contains no visible instances'
        report['checks'].append('standard render')
    # Additional host regressions, performed after saving the simple demo.
    op[11001]=0.
    sphere.SetAbsScale(c4d.Vector(2.)); scaled=evaluate()
    assert all(abs(o.GetMl().v2.GetLength()-2.)<1e-6 for o in scaled)
    assert len(scaled)<report['uniform_count']//2
    sphere.SetAbsScale(c4d.Vector(1.))
    other=c4d.BaseObject(c4d.Ocube); other[c4d.PRIM_CUBE_LEN]=c4d.Vector(8.)
    other.SetName('Second source'); other.InsertUnderLast(op)
    mixed=evaluate()
    assert len(set(o[c4d.INSTANCEOBJECT_LINK].GetName() for o in mixed))==2
    other.Remove()
    surface.SetAbsPos(c4d.Vector(100,20,0)); transformed=evaluate()
    assert all(19.999<o.GetMl().off.y<20.001 and 19.99<=o.GetMl().off.x<=180.01 for o in transformed)
    surface.Remove()
    curved=c4d.BaseObject(c4d.Osphere); curved[c4d.PRIM_SPHERE_RAD]=60.; curved[c4d.PRIM_SPHERE_SUB]=12
    curved.InsertUnder(op); op[11005]=180
    round_result=evaluate()
    assert len(round_result)>50
    assert all(o.GetMl().v2.Dot(o.GetMl().off)>0 for o in round_result)
    report['curved_count']=len(round_result)
    report['checks'].append('source scale, mixed sources, translated surface, native curved surface')
    sphere.Remove(); op.SetDirty(c4d.DIRTYFLAGS_DATA)
    doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    assert op.GetCache() is not None
    assert not children(op.GetCache())
    assert op.GetRad().GetLength()>50.,'Surface must stay visible without sources'
    repro=c4d.documents.LoadDocument(str(OUT/'user-repro.c4d'),c4d.SCENEFILTER_OBJECTS|c4d.SCENEFILTER_MATERIALS,None)
    if repro:
        repro.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        generator=repro.GetFirstObject(); cached=generator.GetCache()
        assert cached.GetDown().CheckType(c4d.Opolygon)
        assert not cached.GetDown().GetBit(c4d.BIT_CONTROLOBJECT)
        assert len(children(cached))==95
        assert generator.GetRad().x>110.
        report['checks'].append('user scene: visible surface, 95 instances, bounds include their radii')
    report['passed']=True

try: run()
except BaseException:
    report['passed']=False; report['error']=traceback.format_exc(); traceback.print_exc()
finally:
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'host-check.json').write_text(json.dumps(report,indent=2))
    print('NOISESPREAD_REPORT',json.dumps(report))
