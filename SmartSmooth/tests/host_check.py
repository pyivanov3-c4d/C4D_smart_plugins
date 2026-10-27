"""Run with c4dpy against the installed plugin. Only detached test docs."""
import c4d
import math
import json
import traceback
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / 'artifacts/smartsmooth/host-report.json'
report = {'passed': False, 'checks': [], 'version': c4d.GetC4DVersion()}
docs = []

def mesh_of(root):
    while root:
        if root.CheckType(c4d.Opolygon): return root
        found = mesh_of(root.GetDown())
        if found: return found
        root = root.GetNext()

def ring():
    # A bent band: the middle ring is a curved 90-degree crease.
    m = c4d.PolygonObject(24,16)
    m.SetAllPoints([c4d.Vector(radius*math.cos(i*math.pi/4),y,radius*math.sin(i*math.pi/4))
                   for radius,y in ((1,-1),(1,0),(2,0)) for i in range(8)])
    for j in range(2):
        for i in range(8):
            m.SetPolygon(j*8+i,c4d.CPolygon(j*8+i,j*8+(i+1)%8,(j+1)*8+(i+1)%8,(j+1)*8+i))
    m.Message(c4d.MSG_UPDATE)
    p=m.MakeTag(c4d.Tphong)
    p[c4d.PHONGTAG_PHONG_ANGLELIMIT]=True
    p[c4d.PHONGTAG_PHONG_ANGLE]=math.pi
    p[c4d.PHONGTAG_PHONG_USEEDGES]=True
    for i in range(8):
        m.GetPhongBreak().Select(4*i+2)
        m.GetPhongBreak().Select(4*(i+8))
    return m,p

def scene(mesh):
    d=c4d.documents.BaseDocument();docs.append(d)
    o=c4d.BaseObject(1070000);assert o is not None,'Plugin registration'
    d.InsertObject(o);mesh.InsertUnder(o)
    return d,o

def evaluate(d,o,build=c4d.BUILDFLAGS_NONE):
    d.ExecutePasses(None,True,True,True,build)
    m=mesh_of(o.GetCache())
    assert m is not None,'Missing polygon cache: '+str(o.GetCache())
    return m

def signature(m):
    return [(p.x,p.y,p.z) for p in m.GetAllPoints()]

try:
    import smartsmooth_progress as progress
    stages=[];original=progress.Progress.stage
    def stage(self,*args,**kwargs):
        stages.append(args);return original(self,*args,**kwargs)
    progress.Progress.stage=stage
    mesh,phong=ring();source=signature(mesh);d,o=scene(mesh)
    assert o[1000]==3 and o[1001]==0 and o[1002]==3 and o[1003]==1
    o[1000]=1
    assert o.GetDescription(c4d.DESCFLAGS_DESC_0).GetParameter(c4d.DescID(1000)) is not None
    out=evaluate(d,o);assert out.GetPolygonCount()==64
    expected=.75+.25*math.cos(math.pi/4)
    assert any((p-c4d.Vector(expected,0,0)).GetLength()<1e-6 for p in out.GetAllPoints()),'Crease cubic mask'
    assert out.GetPhongBreak().GetCount()==32,'Refined explicit Phong edges'
    assert signature(mesh)==source and mesh.GetTag(c4d.Tsds) is None
    assert out.GetTag(c4d.Tsds) is None
    report['checks'].append('registration, default 3, resources, cubic crease motion, sharp refined edges, input untouched')
    sig=signature(out);before=len(stages)
    out=evaluate(d,o);assert signature(out)==sig and len(stages)==before
    assert not progress._jobs
    report['checks'].append('cache reuse does not report calculation; progress closes')
    phong[c4d.PHONGTAG_PHONG_USEEDGES]=False
    out=evaluate(d,o);assert signature(out)!=sig,'Phong tag edit did not invalidate cache'
    assert out.GetPhongBreak().GetCount()==0
    report['checks'].append('Use Edge Breaks toggle and Phong-tag cache invalidation')
    phong[c4d.PHONGTAG_PHONG_ANGLE]=math.radians(89)
    out=evaluate(d,o);assert signature(out)==sig,'89 degree threshold must identify the 90 degree ring'
    phong[c4d.PHONGTAG_PHONG_ANGLE]=math.radians(91)
    assert signature(evaluate(d,o))!=sig
    phong[c4d.PHONGTAG_PHONG_ANGLELIMIT]=False
    phong[c4d.PHONGTAG_PHONG_ANGLE]=.01
    assert signature(evaluate(d,o))!=sig
    report['checks'].append('angle thresholds 89/91 degrees and disabled Angle Limit')
    phong[c4d.PHONGTAG_PHONG_USEEDGES]=True
    assert signature(evaluate(d,o))==sig
    saved=mesh.GetPhongBreak().GetClone()
    mesh.GetPhongBreak().DeselectAll()
    mesh.Message(c4d.MSG_UPDATE)
    mesh.SetDirty(c4d.DIRTYFLAGS_DATA)
    assert signature(evaluate(d,o))!=sig,'Break selection edit did not invalidate cache'
    saved.CopyTo(mesh.GetPhongBreak())
    mesh.Message(c4d.MSG_UPDATE)
    mesh.SetDirty(c4d.DIRTYFLAGS_DATA)
    assert signature(evaluate(d,o))==sig
    report['checks'].append('direct Phong edge selection changes invalidate cache')
    o[1000]=2;out=evaluate(d,o);assert out.GetPolygonCount()==256
    sig2=signature(out);o.SetDirty(c4d.DIRTYFLAGS_DATA)
    out=evaluate(d,o,c4d.BUILDFLAGS_EXTERNALRENDERER);assert signature(out)==sig2
    report['checks'].append('2 iterations; identical viewport/render geometry')
    # Existing user weights must have no influence.
    w=mesh.MakeTag(c4d.Tsds);w.InitFromObject();w.SetAllPointWeights([1.]*24)
    assert signature(evaluate(d,o))==sig2
    report['checks'].append('existing SDS weights ignored; Phong is the only crease input')
    o[1000]=0;out=evaluate(d,o);assert signature(out)==source
    assert not out.GetBit(c4d.BIT_CONTROLOBJECT)
    report['checks'].append('zero iterations passthrough')
    # A primitive also exercises evaluated input conversion and UV subdivision.
    cube=c4d.BaseObject(c4d.Ocube);p=cube.MakeTag(c4d.Tphong)
    p[c4d.PHONGTAG_PHONG_ANGLELIMIT]=True;p[c4d.PHONGTAG_PHONG_ANGLE]=math.radians(40)
    d2,o2=scene(cube);o2[1000]=1;out=evaluate(d2,o2)
    assert out.GetPolygonCount()==24
    assert out.GetTag(c4d.Tuvw) is not None
    assert all(max(abs(p.x),abs(p.y),abs(p.z))>=99.99 for p in out.GetAllPoints())
    report['checks'].append('primitive conversion, sharp cube at 40 degrees, UV preservation')
    # Force cancellation during calculation, then ensure the next pass recovers.
    original_check=progress.Progress.check
    cancelled=[False]
    def cancel_once(self):
        if not cancelled[0]:
            cancelled[0]=True
            raise progress.Cancelled()
        original_check(self)
    progress.Progress.check=cancel_once
    o2.SetDirty(c4d.DIRTYFLAGS_DATA)
    d2.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    progress.Progress.check=original_check
    assert cancelled[0] and not progress._jobs
    assert evaluate(d2,o2).GetPolygonCount()==24
    report['checks'].append('cancellation clears status and automatically retries')
    # Check that rim strips are part of the surrounding closed mesh, including
    # three-way corners. Every topological edge must have exactly two faces.
    def closed(m):
        edges={}
        for poly in m.GetAllPolygons():
            for a,b in ((poly.a,poly.b),(poly.b,poly.c),(poly.c,poly.d),(poly.d,poly.a)):
                if a==b:continue
                key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1
        assert edges and all(v==2 for v in edges.values()),'Open/nonmanifold bevel connection'
    o2[1000]=3
    base=evaluate(d2,o2);base_sig=signature(base);base_count=base.GetPolygonCount()
    o2[1001]=10.0
    profiles=[]
    profile_sums=[]
    for roundness in (-1.,0.,1.):
        o2[1003]=roundness
        rim=evaluate(d2,o2);closed(rim)
        assert rim.GetPolygonCount()>base_count
        assert rim.GetTag(c4d.Tuvw) is not None
        profiles.append(signature(rim))
        cross=[p.x+p.y for p in rim.GetAllPoints() if abs(p.z)<1e-5 and p.x>85 and p.y>85]
        assert len(cross)>=5,cross
        profile_sums.append((min(cross),max(cross)))
    assert profiles[0]!=profiles[1] and profiles[1]!=profiles[2]
    assert abs(profile_sums[1][0]-190)<1e-4 and abs(profile_sums[1][1]-190)<1e-4,profile_sums
    assert profile_sums[0][0]<189.9 and profile_sums[2][1]>190.1,profile_sums
    report['profile_cross_section_sums']=profile_sums
    counts=[]
    for sub in (0,1,3,5):
        o2[1002]=sub
        rim=evaluate(d2,o2);closed(rim);counts.append(rim.GetPolygonCount())
    assert counts==sorted(set(counts)),counts
    o2[1002]=3
    sig=signature(evaluate(d2,o2));o2.SetDirty(c4d.DIRTYFLAGS_DATA)
    assert signature(evaluate(d2,o2,c4d.BUILDFLAGS_EXTERNALRENDERER))==sig
    o2[1001]=0.;assert signature(evaluate(d2,o2))==base_sig
    o2[1001]=10.
    report['bevel_polygon_counts']=counts
    report['checks'].append('bevel roundness -1/0/1; profile loops 0/1/3/5; closed connected corner topology; UVs; render parity; width zero exact bypass')
    # Curved crease: bevel must not split the band into disconnected pieces or
    # introduce new open seams. The two original boundary rings remain open.
    o[1000]=2;o[1001]=.05
    curved=evaluate(d,o)
    edge_counts={};adj={}
    for poly in curved.GetAllPolygons():
        for a,b in ((poly.a,poly.b),(poly.b,poly.c),(poly.c,poly.d),(poly.d,poly.a)):
            if a==b:continue
            key=tuple(sorted((a,b)));edge_counts[key]=edge_counts.get(key,0)+1
            adj.setdefault(a,set()).add(b);adj.setdefault(b,set()).add(a)
    assert all(v in (1,2) for v in edge_counts.values())
    assert sum(v==1 for v in edge_counts.values())==64
    seen=set();todo=[next(iter(adj))]
    while todo:
        vertex=todo.pop()
        if vertex in seen:continue
        seen.add(vertex);todo.extend(adj[vertex]-seen)
    assert len(seen)==len(adj)
    report['checks'].append('curved crease bevel is one connected surface with no new open seams')
    # Render in the isolated test document, with a dedicated camera.
    camera=c4d.BaseObject(c4d.Ocamera);d2.InsertObject(camera)
    camera.SetAbsPos(c4d.Vector(380,270,-480))
    camera.SetAbsRot(c4d.utils.VectorToHPB(-camera.GetAbsPos()))
    d2.GetActiveBaseDraw().SetSceneCamera(camera)
    rd=d2.GetActiveRenderData();rd[c4d.RDATA_RENDERENGINE]=c4d.RDATA_RENDERENGINE_STANDARD
    rd[c4d.RDATA_XRES]=400;rd[c4d.RDATA_YRES]=400
    bitmap=c4d.bitmaps.BaseBitmap();bitmap.Init(400,400,24)
    result=c4d.documents.RenderDocument(d2,rd.GetDataInstance(),bitmap,c4d.RENDERFLAGS_EXTERNAL)
    assert result==c4d.RENDERRESULT_OK
    count=sum(max(bitmap.GetPixel(x,y))>4 for x in range(0,400,4) for y in range(0,400,4))
    assert count>100,'Render is empty'
    bitmap.Save(str(OUT.parent/'render-check.png'),c4d.FILTER_PNG)
    report['checks'].append('Standard renderer produces visible SmartSmooth geometry')
    report['render_nonblack_samples']=count
    report['passed']=True
except BaseException:
    report['error']=traceback.format_exc();traceback.print_exc()
finally:
    for d in docs:c4d.documents.KillDocument(d)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2))
    print('SMARTSMOOTH_REPORT',json.dumps(report))
