"""Vector pipeline: native polygon union -> distance bridges -> local attraction.

No image, occupancy grid, distance raster or contour tracing is used.
"""
import importlib.util
import math
import os
import sys
import metaspline_geometry as g

_name='_metaspline_clipper'
_folder=os.path.join(os.path.dirname(__file__),'vendor','cp%d%d'%sys.version_info[:2],'pyclipper')
if _name not in sys.modules:
    spec=importlib.util.spec_from_file_location(_name,os.path.join(_folder,'__init__.py'),submodule_search_locations=[_folder])
    if spec is None or spec.loader is None: raise ImportError('Metaspline requires the bundled Windows CPython 3.11/3.12 clipping library')
    module=importlib.util.module_from_spec(spec);sys.modules[_name]=module
    spec.loader.exec_module(module)
pc=sys.modules[_name]

def box(ring):
    return min(p[0] for p in ring),min(p[1] for p in ring),max(p[0] for p in ring),max(p[1] for p in ring)

def box_distance(a,b):
    return math.hypot(max(0.,a[0]-b[2],b[0]-a[2]),max(0.,a[1]-b[3],b[1]-a[3]))

class Clip:
    def __init__(self,tolerance): self.scale=100./tolerance;self.tolerance=tolerance
    def ints(self,rings):
        return [[(round(x*self.scale),round(y*self.scale)) for x,y in r] for r in rings if len(r)>=3]
    def floats(self,rings): return [[(x/self.scale,y/self.scale) for x,y in r] for r in rings]
    def union(self,rings,evenodd=False):
        paths=self.ints(rings)
        if not paths:return []
        c=pc.Pyclipper();c.StrictlySimple=True;c.AddPaths(paths,pc.PT_SUBJECT,True)
        tree=c.Execute2(pc.CT_UNION,pc.PFT_EVENODD if evenodd else pc.PFT_NONZERO,pc.PFT_NONZERO)
        shapes=[]
        def visit(node):
            if node.Contour and not node.IsHole:
                shapes.append(self.floats([node.Contour]+[v.Contour for v in node.Childs if v.IsHole]))
            for child in node.Childs:visit(child)
        visit(tree)
        return shapes
    def capsule(self,a,b,radius):
        path=[(round(p[0]*self.scale),round(p[1]*self.scale)) for p in (a,b)]
        c=pc.PyclipperOffset(2.,self.tolerance*self.scale)
        c.AddPath(path,pc.JT_ROUND,pc.ET_OPENROUND)
        return self.floats(c.Execute(radius*self.scale))
    def close(self,shapes,radius):
        if radius<=self.tolerance:return shapes
        paths=self.ints([r for s in shapes for r in s])
        for delta in (radius,-radius):
            offset=pc.PyclipperOffset(2.,self.tolerance*self.scale)
            offset.AddPaths(paths,pc.JT_ROUND,pc.ET_CLOSEDPOLYGON)
            paths=offset.Execute(delta*self.scale)
            if not paths:return shapes
        result=self.union(self.floats(paths))
        # Integer offset cleanup can leave microscopic slivers at a join.
        minimum=self.tolerance*self.tolerance*4.
        return [[r for r in shape if abs(g.area(r))>minimum] for shape in result if abs(g.area(shape[0]))>minimum]

def neck_polygon(left,right,a,b,width,tolerance):
    """Four cubic flanks: broad tangent shoulders and a narrow central throat."""
    distance=math.dist(a,b)
    if distance<tolerance:return None
    ex,ey=(b[0]-a[0])/distance,(b[1]-a[1])/distance
    nx,ny=-ey,ex
    def local(p):dx,dy=p[0]-a[0],p[1]-a[1];return dx*ex+dy*ey,dx*nx+dy*ny
    def world(p):return a[0]+p[0]*ex+p[1]*nx,a[1]+p[0]*ey+p[1]*ny
    l=[local(p) for p in left];r=[local(p) for p in right]
    radius=min(math.sqrt(abs(g.area(left))/math.pi),math.sqrt(abs(g.area(right))/math.pi))
    shoulder=max(width*1.6,min(radius*.45,distance*.5+radius*.25))
    shoulder=min(shoulder,max(tolerance*3,min(max(p[1] for p in l),-min(p[1] for p in l),max(p[1] for p in r),-min(p[1] for p in r))*.85))
    def hit(ring,y,last):
        hits=[]
        for p,q in zip(ring,ring[1:]+ring[:1]):
            if (p[1]>y)!=(q[1]>y):
                t=(y-p[1])/(q[1]-p[1]);x=p[0]+t*(q[0]-p[0])
                dx,dy=q[0]-p[0],q[1]-p[1]
                if dx<0:dx,dy=-dx,-dy
                norm=math.hypot(dx,dy)
                hits.append((x,(dx/max(norm,1e-20),dy/max(norm,1e-20))))
        if not hits:return None
        return (max(hits,key=lambda v:v[0]) if last else min(hits,key=lambda v:v[0]))
    upper=[];lower=[];middle=distance*.5
    def sample(c):
        out=[]
        for i in range(24):
            t=i/24;u=1-t
            out.append(tuple(u**3*c[0][k]+3*u*u*t*c[1][k]+3*u*t*t*c[2][k]+t**3*c[3][k] for k in (0,1)))
        return out
    for sign,out in ((1,upper),(-1,lower)):
        lh,rh=hit(l,sign*shoulder,True),hit(r,sign*shoulder,False)
        if lh is None or rh is None:return None
        lx,lt=lh;rx,rt=rh
        start=(lx-tolerance*2,sign*shoulder);end=(rx+tolerance*2,sign*shoulder);mid=(middle,sign*width)
        reach_left=max(tolerance,middle-lx);reach_right=max(tolerance,rx-middle)
        handle_left=min(reach_left*.6,shoulder*.9);handle_right=min(reach_right*.6,shoulder*.9)
        c1=(start,(start[0]+lt[0]*handle_left,start[1]+lt[1]*handle_left),(middle-reach_left*.4,sign*width),mid)
        c2=(mid,(middle+reach_right*.4,sign*width),(end[0]-rt[0]*handle_right,end[1]-rt[1]*handle_right),end)
        out.extend(sample(c1)+sample(c2)+[end])
    ring=[world(p) for p in upper+list(reversed(lower))]
    if g.area(ring)<0:ring.reverse()
    return ring

class EdgeIndex:
    """Small bounding-box tree for repeated nearest-boundary queries."""
    def __init__(self,values):
        def build(items):
            bounds=(min(e[5] for e in items),min(e[6] for e in items),max(e[7] for e in items),max(e[8] for e in items))
            if len(items)<=8:return bounds,items,None,None
            axis=0 if bounds[2]-bounds[0]>=bounds[3]-bounds[1] else 1
            items=sorted(items,key=lambda e:e[5+axis]+e[7+axis]);middle=len(items)//2
            return bounds,None,build(items[:middle]),build(items[middle:])
        self.root=build(values) if values else None

def edges(ring):
    result=[]
    for a,b in zip(ring,ring[1:]+ring[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];n=dx*dx+dy*dy
        if n>1e-20:result.append((a[0],a[1],dx,dy,1./n,min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])))
    return EdgeIndex(result)

def nearest(p,segments,limit=float('inf')):
    px,py=p;best=limit*limit;answer=None
    def bound(node):
        b=node[0];x=max(b[0]-px,0.,px-b[2]);y=max(b[1]-py,0.,py-b[3]);return x*x+y*y
    stack=[segments.root] if segments.root else []
    while stack:
        node=stack.pop()
        if bound(node)>best:continue
        _,items,left,right=node
        if items is None:
            if bound(left)<bound(right):stack.extend((right,left))
            else:stack.extend((left,right))
            continue
        for x,y,dx,dy,inv,x0,y0,x1,y1 in items:
            t=max(0.,min(1.,((px-x)*dx+(py-y)*dy)*inv))
            q=(x+t*dx,y+t*dy);d=(px-q[0])**2+(py-q[1])**2
            if d<best:best=d;answer=q
    return (math.sqrt(best),answer)

def closest(a,b,check,limit):
    best=limit;pair=None;ea,eb=edges(a),edges(b)
    for source,target,reverse in ((a,eb,False),(b,ea,True)):
        for i,p in enumerate(source):
            if i%32==0:check()
            distance,q=nearest(p,target,best)
            if q is not None and distance<best:
                best=distance;pair=(q,p) if reverse else (p,q)
    return best,pair

def resample(ring,spacing,count=None):
    lengths=[math.dist(a,b) for a,b in zip(ring,ring[1:]+ring[:1])]
    total=sum(lengths)
    if total<1e-12:return ring
    count=count or max(24,min(400,int(math.ceil(total/max(spacing,1e-9)))))
    interval=total/count;out=[];position=0.;target=0.
    for a,b,span in zip(ring,ring[1:]+ring[:1],lengths):
        while span>0 and target<position+span and len(out)<count:
            t=(target-position)/span
            out.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])));target+=interval
        position+=span
    return out

def attract(shapes,collapse,fallow,tolerance,check,progress):
    if fallow<=0 or len(shapes)<2:return shapes,False
    extent=max(max(b[2]-b[0],b[3]-b[1]) for b in [box(s[0]) for s in shapes])
    rings=[resample(s[0],max(tolerance*4,extent/180.)) for s in shapes]
    bounds=[box(r) for r in rings];segments=[edges(r) for r in rings]
    changes=[];changed=False;influence=collapse+fallow
    for i,ring in enumerate(rings):
        progress('Fallow: smoothing facing regions',55+20.*i/len(rings));check()
        candidates=[j for j in range(len(rings)) if i!=j and box_distance(bounds[i],bounds[j])<influence]
        moved=[];sign=1. if g.area(ring)>=0 else -1.
        for k,p in enumerate(ring):
            if k%16==0:check()
            before,after=ring[k-1],ring[(k+1)%len(ring)]
            tx,ty=after[0]-before[0],after[1]-before[1];size=math.hypot(tx,ty)
            nx,ny=sign*ty/max(size,1e-20),-sign*tx/max(size,1e-20)
            best=influence;q=None
            for j in candidates:
                distance,point=nearest(p,segments[j],best)
                if point is not None:best=distance;q=point
            if q is None or best<=tolerance:
                moved.append(p);continue
            facing=max(0.,((q[0]-p[0])*nx+(q[1]-p[1])*ny)/best)
            t=max(0.,min(1.,(best-collapse)/fallow));t=t*t*(3.-2.*t)
            weight=max(0.,(1./(1.+t)**2-.25)/.75)
            weight=1.-(1.-weight)**2
            # Keep an analytic slit; never weld through Fallow alone.
            amount=min(.47*weight*facing*facing,.5-tolerance*3/max(best,1e-20))
            if amount>1e-5:changed=True
            moved.append((p[0]+max(0.,amount)*(q[0]-p[0]),p[1]+max(0.,amount)*(q[1]-p[1])))
        # Relax displacement, not the source contour: far-away edges stay fixed.
        displacement=[(q[0]-p[0],q[1]-p[1]) for p,q in zip(ring,moved)]
        for _ in range(3):
            displacement=[tuple((displacement[k-1][a]+2*v[a]+displacement[(k+1)%len(ring)][a])*.25 for a in (0,1)) for k,v in enumerate(displacement)]
        changes.append([(p[0]+d[0],p[1]+d[1]) for p,d in zip(ring,displacement)])
    return [[ring]+shapes[i][1:] for i,ring in enumerate(changes)],changed

def frame(points):
    origin=points[0];u=max((g.sub(p,origin) for p in points),key=g.length)
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    normal=max((cross(u,g.sub(p,origin)) for p in points),key=g.length)
    if g.length(normal)<1e-12:return None
    u=tuple(x/g.length(u) for x in u);normal=tuple(x/g.length(normal) for x in normal);v=cross(normal,u)
    return origin,u,v,normal

def process(groups,collapse,fallow,smooth,check=None,resolution=320,cache=None,progress=None,viscosity=.25):
    check=check or g.WorkBudget();progress=progress or (lambda *args:None)
    collapse=max(0.,float(collapse));fallow=max(0.,float(fallow));smooth=max(0.,min(1.,float(smooth)))
    viscosity=max(0.,min(1.,float(viscosity)))
    # Fourfold response in log space around the established 25% default:
    # both faster low-viscosity growth and slower high-viscosity growth.
    growth_power=1.75*((1.+3.*viscosity)/1.75)**4
    shoulder_power=2.*((1.+4.*viscosity)/2.)**4
    valid=[[(curves,True) for curves,closed in group if closed and curves] for group in groups]
    valid=[group for group in valid if group];originals=[path for group in valid for path in group]
    if not originals:return [],'No closed child splines'
    key=tuple(tuple(tuple(tuple(tuple(p) for p in c) for c in curves) for curves,_ in group) for group in valid)
    result_key=(key,collapse,fallow,smooth,viscosity)
    cache=cache if cache is not None else {}
    if cache.get('result_key')==result_key:return cache['result']
    progress('Preparing vector contours',5);check()
    points=[p for curves,_ in originals for c in curves for p in c]
    if len(points)>400000:raise g.EvaluationStopped('Input span limit')
    if not all(math.isfinite(v) for p in points for v in p):raise ValueError('Non-finite input coordinate')
    basis=frame(points)
    extent=max(max(p[a] for p in points)-min(p[a] for p in points) for a in range(3))
    tolerance=max(extent/8000.,1e-6)
    def smoothing_only():
        if smooth<=0:return originals
        return [(g.fit_closed(g.round_drop(g.flatten(curves,tolerance,check),smooth),tolerance,check),True) for curves,_ in originals]
    if len(valid)==1 or basis is None:
        result=(smoothing_only(),'Single child: smoothing only')
    else:
        origin,u,v,normal=basis
        def dot(a,b):return sum(x*y for x,y in zip(a,b))
        if max(abs(dot(g.sub(p,origin),normal)) for p in points)>max(extent*1e-4,1e-5):
            result=(smoothing_only(),'Non-coplanar input: smoothing only')
        else:
            def project(p):d=g.sub(p,origin);return dot(d,u),dot(d,v)
            def restore(p):return tuple(origin[a]+p[0]*u[a]+p[1]*v[a] for a in range(3))
            clip=Clip(tolerance)
            if cache.get('union_key')==key:
                union=cache['union'];input_area=cache['input_area'];input_count=cache['input_count']
            else:
                input_shapes=[]
                for i,group in enumerate(valid):
                    check();progress('Union: resolving closed children',10+20.*i/len(valid))
                    rings=[[project(p) for p in g.flatten(curves,tolerance,check)] for curves,_ in group]
                    input_shapes.extend(clip.union(rings,True))
                input_area=sum(sum(g.area(r) for r in shape) for shape in input_shapes)
                input_count=len(input_shapes)
                progress('Union: combining overlapping shapes',30)
                union=clip.union([r for s in input_shapes for r in s])
                cache.clear();cache.update(union_key=key,union=union,input_area=input_area,input_count=input_count)
            check()
            if len(union)>96:raise g.EvaluationStopped('More than 96 disconnected vector islands')
            # Both sides use the same pulled shoulders before and after contact.
            # This avoids a pop from pointed lobes to an unrelated capsule.
            pre_key=(key,collapse,fallow)
            if cache.get('pre_key')==pre_key:
                prepared=cache['prepared'];attracted=cache['attracted']
            else:
                prepared,attracted=attract(union,collapse,fallow,tolerance,check,
                    lambda label,pct:progress('Fallow: forming liquid shoulders',35+(pct-55)*.65))
                if attracted:
                    validation=clip.union([r for shape in prepared for r in shape])
                    expected=(len(union),sum(len(shape)-1 for shape in union))
                    if (len(validation),sum(len(shape)-1 for shape in validation))!=expected:
                        prepared=union;attracted=False
                cache.update(pre_key=pre_key,prepared=prepared,attracted=attracted)
            bridge_key=(key,collapse,fallow,viscosity)
            if cache.get('bridge_key')==bridge_key:
                local=cache['bridged'];bridge_count=cache['bridge_count'];necks=cache['necks']
            else:
                bridges=[];necks=[];strength=0.;bounds=[box(shape[0]) for shape in union]
                pairs=[(i,j) for i in range(len(union)) for j in range(i+1,len(union)) if collapse>0 and box_distance(bounds[i],bounds[j])<collapse]
                for k,(i,j) in enumerate(pairs):
                    check();progress('Collapse: growing liquid necks',50+20.*k/max(1,len(pairs)))
                    distance,pair=closest(union[i][0],union[j][0],check,collapse)
                    if pair is None or distance>=collapse:continue
                    depth=max(0.,min(1.,1.-distance/collapse));strength=max(strength,depth)
                    radius=min(math.sqrt(abs(g.area(union[i][0]))/math.pi),math.sqrt(abs(g.area(union[j][0]))/math.pi))
                    # Width grows from distance penetration with zero initial slope.
                    # The tiny floor is only for integer clipping robustness.
                    width=max(tolerance*.1,min(radius*.55,collapse*.65)*depth**growth_power)
                    _,pulled=closest(prepared[i][0],prepared[j][0],check,collapse+tolerance)
                    a,b=pulled if pulled else pair
                    necks.append(((a[0]+b[0])*.5,(a[1]+b[1])*.5,width,depth,max(radius*.4,collapse*.25)))
                    neck=neck_polygon(prepared[i][0],prepared[j][0],a,b,width,tolerance)
                    if neck is not None:bridges.append(neck)
                    else:bridges.extend(clip.capsule(a,b,width))
                local=clip.union([r for shape in prepared for r in shape]+bridges) if bridges else prepared
                bridge_count=len(bridges)
                # Round concave shoulders progressively, and keep that rounding
                # when the source outlines themselves finally overlap.
                if input_count>len(union):strength=1.
                if strength>0 and collapse>0:
                    rounded=[]
                    for shape in local:
                        check();rounded.extend(clip.close([shape],collapse*.35*strength**shoulder_power))
                    local=rounded
                cache.update(bridge_key=bridge_key,bridged=local,bridge_count=bridge_count,necks=necks)
            check();progress('Reconstructing sparse Bezier curves',80)
            union_area=sum(sum(g.area(r) for r in s) for s in union)
            untouched=(not bridge_count and not attracted and len(union)==input_count and abs(union_area-input_area)<tolerance*tolerance)
            if untouched and smooth<=0:output=originals
            else:
                output=[];rings=[r for s in local for r in s]
                for i,r in enumerate(rings):
                    check();progress('Fitting closed Bezier contours',80+18.*i/max(1,len(rings)))
                    if smooth>0 or (attracted and bridge_count):
                        original=r
                        maturity=min((n[3]**growth_power for n in necks),default=1.)
                        # Broad drop relaxation must not erase a newly born neck.
                        # Its full strength arrives with bridge maturity; 100%
                        # remains the explicit round-drop endpoint.
                        effective=smooth*(maturity+(1.-maturity)*smooth**8)
                        r=g.round_drop(r,effective) if smooth>0 else g.smooth_ring(r,.15)
                        if necks and effective<.03:
                            source=resample(original,1.,count=len(r))
                            protected=[]
                            for p,q in zip(source,r):
                                weight=0.
                                for cx,cy,width,depth,radius in necks:
                                    distance=math.hypot(p[0]-cx,p[1]-cy)/max(radius,1e-10)
                                    t=max(0.,min(1.,(distance-.35)/.65))
                                    spatial=1.-t*t*(3.-2.*t)
                                    maturity=max(0.,min(1.,(depth-.55)/.45))
                                    weight=max(weight,spatial*(1.-maturity*maturity*(3.-2.*maturity))*(1.-smooth**8))
                                protected.append((q[0]+(p[0]-q[0])*weight,q[1]+(p[1]-q[1])*weight))
                            r=protected
                    # Smooth short polygon-edge changes before reconstructing a
                    # compact cubic outline; no raster-scale filtering is involved.
                    if smooth<=0 and attracted and not bridge_count:r=g.smooth_ring(r,.15)
                    def local_fit_tolerance(p):
                        x,y=project(p);allowed=tolerance*4.
                        for cx,cy,width,depth,radius in necks:
                            t=min(1.,math.hypot(x-cx,y-cy)/max(radius*.35,1e-10))
                            allowed=min(allowed,width*.2+(tolerance*4.-width*.2)*t*t)
                        return max(tolerance*.02,allowed)
                    fit_tolerance=local_fit_tolerance if necks and smooth<1. else tolerance*4.
                    curves=g.fit_closed([restore(p) for p in r],fit_tolerance,check)
                    if curves:output.append((curves,True))
            result=(output,'Vector | {} contours | {} bridges | fit {:.4g}'.format(len(output),bridge_count,tolerance*4.))
    cache.update(result_key=result_key,result=result)
    progress('Complete',100)
    return result
