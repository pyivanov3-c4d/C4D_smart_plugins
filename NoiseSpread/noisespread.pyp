"""NoiseSpread 1.0.2 — dense surface render-instance generator, Cinema 4D 2026."""
import math
import os
import sys
import threading
import traceback
import c4d
from c4d import plugins, bitmaps
from c4d.modules import render

ROOT=os.path.dirname(__file__)
if ROOT not in sys.path: sys.path.insert(0,ROOT)
import noisespread_geometry as geo

PLUGIN_ID=1069993  # Local ID. Obtain a Maxon ID before public redistribution.
SIZE,FEATHER,NOISE,SELECTION,SEED,LIMIT,STATUS=11000,11001,11002,11003,11004,11005,11006
VERSION='1.0.2'

def xyz(v): return v.x,v.y,v.z
def vec(p): return c4d.Vector(*p)

def meshes(node,parent,depth=0):
    """Walk one evaluated subtree (never consume the next top-level source)."""
    if depth>64: raise ValueError('Hierarchy exceeds 64 levels')
    matrix=parent*node.GetMl()
    deform=node.GetDeformCache()
    cache=node.GetCache()
    if deform is not None or cache is not None:
        child=deform if deform is not None else cache
    else:
        if node.CheckType(c4d.Opolygon): yield node,matrix
        child=node.GetDown()
    while child is not None:
        yield from meshes(child,matrix,depth+1)
        child=child.GetNext()

def read_surface(node,selection):
    triangles=[]; payloads=[]; matched=False; point_count=0
    for mesh,matrix in meshes(node,c4d.Matrix()):
        points=mesh.GetAllPoints(); point_count+=len(points)
        if point_count>300000: raise ValueError('Surface exceeds 300,000 points; reduce subdivisions')
        chosen=None
        if selection:
            chosen=c4d.BaseSelect()
            for tag in mesh.GetTags():
                if tag.CheckType(c4d.Tpolygonselection) and tag.GetName()==selection:
                    chosen.Merge(tag.GetBaseSelect()); matched=True
        uvtag=mesh.GetTag(c4d.Tuvw)
        transformed=[xyz(matrix*p) for p in points]
        for i,poly in enumerate(mesh.GetAllPolygons()):
            if chosen is not None and not chosen.IsSelected(i): continue
            uv=uvtag.GetSlow(i) if uvtag else None
            indices=(poly.a,poly.b,poly.c,poly.d)
            for corners in ((0,1,2),) if poly.c==poly.d else ((0,1,2),(0,2,3)):
                triangles.append(tuple(transformed[indices[j]] for j in corners))
                payloads.append((~matrix,tuple(xyz(uv['abcd'[j]]) for j in corners) if uv else None))
                if len(triangles)>300000: raise ValueError('Surface exceeds 300,000 triangles')
    if selection and not matched: raise ValueError('Polygon selection not found: '+selection)
    return geo.Surface(triangles,payloads)

def source_radius(evaluated,scale,with_extent=False):
    """Exact disk about +Y for evaluated vertices, including off-center axes."""
    radius=0.; extent=0.; count=0
    # Root rotation and position are intentionally replaced by surface alignment.
    root=~evaluated.GetMl()
    for mesh,matrix in meshes(evaluated,root):
        for point in mesh.GetAllPoints():
            p=matrix*point
            radius=max(radius,math.hypot(p.x*scale.x,p.z*scale.z)); count+=1
            extent=max(extent,math.sqrt((p.x*scale.x)**2+(p.y*scale.y)**2+(p.z*scale.z)**2))
            if count>300000: raise ValueError('Source exceeds 300,000 points')
    if radius<=1e-8: raise ValueError('Source has no polygon footprint in its XZ plane')
    return (radius,extent) if with_extent else radius

def bounds_of(node):
    corners=[]
    for mesh,matrix in meshes(node,c4d.Matrix()):
        center,rad=mesh.GetMp(),mesh.GetRad()
        for x in (-1,1):
            for y in (-1,1):
                for z in (-1,1): corners.append(xyz(matrix*(center+c4d.Vector(x*rad.x,y*rad.y,z*rad.z))))
    if not corners: return (0.,0.,0.),(0.,0.,0.)
    return tuple(min(p[k] for p in corners) for k in range(3)),tuple(max(p[k] for p in corners) for k in range(3))

class NoiseSampler:
    def __init__(self,shader,doc,world,surface):
        if shader is None or not shader.CheckType(c4d.Xnoise):
            raise ValueError('Size Noise must contain a native Noise shader')
        self.shader=shader.GetClone(c4d.COPYFLAGS_NONE)
        self.space=shader[c4d.SLA_NOISE_SPACE]
        self.world=world; self.surface=surface
        if self.space in (c4d.SLA_NOISE_SPACE_SCREEN,c4d.SLA_NOISE_SPACE_RASTER):
            raise ValueError('Screen/Raster Noise needs render context; use World, Object, Texture, UV or Camera')
        self.camera=None
        if self.space==c4d.SLA_NOISE_SPACE_CAMERA:
            bd=doc.GetRenderBaseDraw(); camera=bd.GetSceneCamera(doc) or bd.GetEditorCamera()
            self.camera=~camera.GetMg()
        # Without VolumeData the native shader falls back to UV coordinates.
        # Explicitly supply the selected space on an evaluation-only clone.
        self.shader[c4d.SLA_NOISE_SPACE]=c4d.SLA_NOISE_SPACE_UV
        self.shader[c4d.SLA_NOISE_USE_AS_ENV]=False
        self.cd=render.ChannelData()
        self.cd.t=doc.GetTime().Get() if doc else 0.
        self.cd.d=c4d.Vector(0.); self.cd.off=0.; self.cd.scale=0.
        self.cd.texflag=0
        irs=render.InitRenderStruct(doc); irs.linear_workflow=False
        if self.shader.InitRender(irs)!=c4d.INITRENDERRESULT_OK:
            self.shader.FreeRender()
            raise ValueError('Cinema 4D could not initialize the Noise shader')
    def close(self): self.shader.FreeRender()
    def __call__(self,hit):
        p,n,index,bary=hit
        inverse,uvw=self.surface.payloads[index]
        if self.space==c4d.SLA_NOISE_SPACE_UV:
            if uvw is None: raise ValueError('UV Noise requires a UVW tag on the surface')
            position=vec(tuple(sum(uvw[j][k]*bary[j] for j in range(3)) for k in range(3)))
        elif self.space==c4d.SLA_NOISE_SPACE_WORLD: position=self.world*vec(p)/100.
        elif self.space==c4d.SLA_NOISE_SPACE_CAMERA: position=self.camera*(self.world*vec(p))/100.
        else: position=inverse*vec(p)/100.
        self.cd.p=position; self.cd.n=vec(n)
        color=self.shader.Sample(self.cd)
        value=(color.x+color.y+color.z)/3.
        if not math.isfinite(value): raise ValueError('Non-finite native Noise output')
        return max(0.,min(1.,value))

class NoiseSpread(plugins.ObjectData):
    def Init(self,op,isCloneInit=False):
        for key in (SIZE,FEATHER): self.InitAttr(op,float,[key])
        for key in (SEED,LIMIT): self.InitAttr(op,int,[key])
        self.InitAttr(op,str,[SELECTION])
        if not isCloneInit:
            op[SIZE]=1.; op[FEATHER]=0.; op[SEED]=137; op[LIMIT]=5000; op[SELECTION]=''
            shader=c4d.BaseShader(c4d.Xnoise)
            shader[c4d.SLA_NOISE_SPACE]=c4d.SLA_NOISE_SPACE_WORLD
            op.InsertShader(shader); op[NOISE]=shader
        self.status='First child: surface. Remaining children: sources (+Y normal).'
        self.state=threading.local(); self.signature=None
        self.retry=False
        self.bounds=((0.,0.,0.),(100.,100.,100.))
        return True

    def GetDimension(self,op,mp,rad):
        center,extent=self.bounds
        mp.x,mp.y,mp.z=center
        rad.x,rad.y,rad.z=extent

    def set_bounds(self,lo,hi):
        self.bounds=(tuple((a+b)*.5 for a,b in zip(lo,hi)),tuple((b-a)*.5 for a,b in zip(lo,hi)))

    def CheckDirty(self,op,doc):
        state=[doc.GetTime().Get() if doc else 0.,op.GetMg()]
        def visit(node,depth=0):
            while node:
                if depth>64 or len(state)>10000: return
                state.append((node,node.GetDirty(c4d.DIRTYFLAGS_DATA|c4d.DIRTYFLAGS_MATRIX|c4d.DIRTYFLAGS_CHILDREN)))
                for tag in node.GetTags(): state.append((tag,tag.GetDirty(c4d.DIRTYFLAGS_DATA)))
                visit(node.GetDown(),depth+1); node=node.GetNext()
        visit(op.GetDown())
        shader=op[NOISE]
        if shader: state.append((shader,shader.GetDirty(c4d.DIRTYFLAGS_ALL)))
        state=tuple(state)
        if self.retry or state!=self.signature: self.signature=state; op.SetDirty(c4d.DIRTYFLAGS_DATA)

    def GetDDescription(self,op,description,flags):
        if not description.LoadDescription(op.GetType()): return False
        bc=description.GetParameterI(c4d.DescID(STATUS))
        if bc is not None: bc[c4d.DESC_NAME]=VERSION+' | '+getattr(self,'status','')
        return True,flags|c4d.DESCFLAGS_DESC_LOADED

    def GetVirtualObjects(self,op,hh):
        result=c4d.BaseObject(c4d.Onull); result.SetName('NoiseSpread instances')
        if getattr(self.state,'busy',False): return result
        self.state.busy=True; sampler=None
        try:
            if self.retry: op.SetDirty(c4d.DIRTYFLAGS_DATA)
            self.retry=False
            first=op.GetDown()
            if first is None:
                self.set_bounds((0.,0.,0.),(0.,0.,0.))
                self.status='Add a surface as first child, then source objects.'; return result
            clone=op.GetAndCheckHierarchyClone(hh,first,c4d.HIERARCHYCLONEFLAGS_ASPOLY,True)
            if not clone or clone['clone'] is None:
                self.status='Waiting for evaluated children'; return result
            if not clone['dirty']: return clone['clone']
            if first.GetNext() is None:
                self.status='Surface visible; add source objects below it.'
                self.set_bounds(*bounds_of(clone['clone']))
                return clone['clone']
            # With multiple inputs C4D wraps the evaluated sibling chain in a Null.
            surface_node=clone['clone'].GetDown()
            if surface_node is None: raise ValueError('Evaluated hierarchy has no surface')
            visible_surface=surface_node.GetClone(c4d.COPYFLAGS_NONE)
            def release(node):
                node.DelBit(c4d.BIT_CONTROLOBJECT)
                child=node.GetDown()
                while child: release(child); child=child.GetNext()
            release(visible_surface)
            visible_surface.InsertUnderLast(result)
            lo,hi=bounds_of(visible_surface)
            self.set_bounds(lo,hi)
            surface=read_surface(surface_node,(op[SELECTION] or '').strip())
            sources=[]; prototypes=[]; radii=[]; scales=[]; extents=[]
            library=c4d.BaseObject(c4d.Onull); library.SetName('Source prototypes')
            library.SetEditorMode(c4d.MODE_OFF); library.SetRenderMode(c4d.MODE_OFF)
            library.InsertUnderLast(result)
            original=first.GetNext(); evaluated=surface_node.GetNext()
            while original is not None:
                if evaluated is None: raise ValueError('Evaluated source hierarchy is incomplete')
                m=original.GetMl(); scale=c4d.Vector(m.v1.GetLength(),m.v2.GetLength(),m.v3.GetLength())
                sources.append(original); scales.append(scale)
                radius,extent=source_radius(evaluated,scale,True)
                radii.append(radius); extents.append(extent)
                # Render instances cannot reference children consumed by a generator.
                # Keep one evaluated prototype per source inside our output cache.
                master=evaluated.GetClone(c4d.COPYFLAGS_NONE)
                master.SetMl(c4d.Matrix())
                release(master)
                master.SetName(original.GetName()+' [prototype]')
                master.SetEditorMode(c4d.MODE_UNDEF); master.SetRenderMode(c4d.MODE_UNDEF)
                master.InsertUnderLast(library); prototypes.append(master)
                original=original.GetNext(); evaluated=evaluated.GetNext()
            feather=max(0.,min(.99,float(op[FEATHER])))
            if feather: sampler=NoiseSampler(op[NOISE],op.GetDocument(),op.GetMg(),surface)
            thread=c4d.threading.GeGetCurrentThread()
            def check():
                if thread and thread.TestBreak(): raise InterruptedError()
            items,status=geo.pack(surface,radii,sampler,float(op[SIZE]),feather,int(op[SEED]),max(1,min(20000,int(op[LIMIT]))),check=check)
            if status.startswith('Cancelled'): raise InterruptedError()
            for i,(p,r,n,src,s,tri,bary) in enumerate(items):
                if i%128==0: check()
                instance=c4d.BaseObject(c4d.Oinstance)
                instance[c4d.INSTANCEOBJECT_LINK]=prototypes[src]
                instance[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE]=c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE_SINGLEINSTANCE
                instance[c4d.INSTANCEOBJECT_DRAW_MODE]=c4d.INSTANCEOBJECT_DRAW_MODE_FULL
                x,z=geo.frame(n); scale=scales[src]
                instance.SetMl(c4d.Matrix(vec(p),vec(x)*(s*scale.x),vec(n)*(s*scale.y),vec(z)*(s*scale.z)))
                instance.SetName(sources[src].GetName()+' '+str(i+1))
                instance.InsertUnderLast(result)
                extent=extents[src]*s
                lo=tuple(min(lo[k],p[k]-extent) for k in range(3))
                hi=tuple(max(hi[k],p[k]+extent) for k in range(3))
            self.set_bounds(lo,hi)
            self.status='{} instances | {}'.format(len(items),status)
            return result
        except InterruptedError:
            # A cancellation is not a valid empty/partial result. Returning that
            # hierarchy made C4D keep a surface-only cache indefinitely in editor.
            # None requests a fresh build; CheckDirty also retries on the next pass.
            self.retry=True
            self.status='Calculation interrupted; retrying on next update'
            return None
        except ValueError as error:
            self.status=str(error); return result
        except Exception as error:
            self.status=str(error); traceback.print_exc(); return result
        finally:
            if sampler is not None: sampler.close()
            self.state.busy=False

if __name__=='__main__':
    icon=bitmaps.BaseBitmap()
    if icon.InitWith(os.path.join(ROOT,'res','icon.png'))[0]!=c4d.IMAGERESULT_OK: icon=None
    if not plugins.RegisterObjectPlugin(PLUGIN_ID,'NoiseSpread',NoiseSpread,'Onoisespread',c4d.OBJECT_GENERATOR|c4d.OBJECT_INPUT,icon):
        raise RuntimeError('NoiseSpread registration failed (plugin ID conflict)')
