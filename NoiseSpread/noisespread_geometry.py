"""Deterministic surface advancing-front disk packing. No host dependencies."""
import bisect
import math
import random

def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,s): return tuple(x*s for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def length(a): return math.sqrt(dot(a,a))
def unit(a): return mul(a,1./max(length(a),1e-30))
def frame(n):
    x=unit(cross((0.,0.,1.) if abs(n[2])<.9 else (1.,0.,0.),n))
    return x,cross(x,n)

def closest(p,a,b,c):
    """Closest triangle point with barycentric coordinates (Ericson regions)."""
    ab,ac,ap=sub(b,a),sub(c,a),sub(p,a)
    d1,d2=dot(ab,ap),dot(ac,ap)
    if d1<=0 and d2<=0: return a,(1.,0.,0.)
    bp=sub(p,b); d3,d4=dot(ab,bp),dot(ac,bp)
    if d3>=0 and d4<=d3: return b,(0.,1.,0.)
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:
        v=d1/(d1-d3); return add(a,mul(ab,v)),(1-v,v,0.)
    cp=sub(p,c); d5,d6=dot(ab,cp),dot(ac,cp)
    if d6>=0 and d5<=d6: return c,(0.,0.,1.)
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:
        w=d2/(d2-d6); return add(a,mul(ac,w)),(1-w,0.,w)
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:
        w=(d4-d3)/((d4-d3)+(d5-d6)); return add(b,mul(sub(c,b),w)),(0.,1-w,w)
    inv=1./(va+vb+vc); v,w=vb*inv,vc*inv
    return add(a,add(mul(ab,v),mul(ac,w))),(1-v-w,v,w)

class Surface:
    """Triangle BVH; payloads belong to host (e.g. UVW / source transform)."""
    def __init__(self,triangles,payloads=None):
        self.triangles=[]; self.normals=[]; self.payloads=[]; self.cdf=[]
        total=0.
        for i,t in enumerate(triangles):
            n=cross(sub(t[1],t[0]),sub(t[2],t[0])); area=length(n)*.5
            if area<1e-16: continue
            if not all(math.isfinite(v) for p in t for v in p): raise ValueError('Non-finite surface')
            self.triangles.append(t); self.normals.append(unit(n))
            self.payloads.append(payloads[i] if payloads else None)
            total+=area; self.cdf.append(total)
        if not self.triangles: raise ValueError('No nondegenerate polygons in the selected surface')
        self.area=total
        self.tree=self._build(list(range(len(self.triangles))))

    def _build(self,ids):
        lo=tuple(min(self.triangles[i][j][k] for i in ids for j in range(3)) for k in range(3))
        hi=tuple(max(self.triangles[i][j][k] for i in ids for j in range(3)) for k in range(3))
        if len(ids)<=8: return lo,hi,ids,None
        axis=max(range(3),key=lambda k:hi[k]-lo[k])
        ids.sort(key=lambda i:sum(p[axis] for p in self.triangles[i]))
        mid=len(ids)//2
        return lo,hi,self._build(ids[:mid]),self._build(ids[mid:])

    def project(self,p,max_distance=float('inf')):
        best=max_distance*max_distance; result=None; stack=[self.tree]
        def bound(node):
            return sum(max(node[0][k]-p[k],0.,p[k]-node[1][k])**2 for k in range(3))
        while stack:
            node=stack.pop()
            if bound(node)>best: continue
            if node[3] is None:
                for i in node[2]:
                    q,bary=closest(p,*self.triangles[i]); delta=sub(p,q); d=dot(delta,delta)
                    if d<=best: best=d; result=(q,self.normals[i],i,bary)
            else:
                a,b=node[2],node[3]
                if bound(a)<bound(b): stack.extend((b,a))
                else: stack.extend((a,b))
        return result

    def sample(self,rng):
        i=min(len(self.triangles)-1,bisect.bisect_left(self.cdf,rng.random()*self.area))
        u=math.sqrt(rng.random()); v=rng.random(); bary=(1-u,u*(1-v),u*v)
        t=self.triangles[i]
        p=tuple(sum(t[j][k]*bary[j] for j in range(3)) for k in range(3))
        return p,self.normals[i],i,bary

class Grid:
    def __init__(self,cell): self.cell=cell; self.cells={}; self.items=[]
    def key(self,p): return tuple(math.floor(v/self.cell) for v in p)
    def nearby(self,p):
        a,b,c=self.key(p)
        for x in range(a-1,a+2):
            for y in range(b-1,b+2):
                for z in range(c-1,c+2):
                    for i in self.cells.get((x,y,z),()): yield self.items[i]
    def accepts(self,p,r):
        # Deliberately use chord distance, a conservative bound on surface distance.
        return all(dot(sub(p,q[0]),sub(p,q[0])) >= (r+q[1])**2*(1-1e-10) for q in self.nearby(p))
    def insert(self,item):
        self.cells.setdefault(self.key(item[0]),[]).append(len(self.items)); self.items.append(item)

def pack(surface,radii,sample_scale,size=1.,feather=0.,seed=137,max_count=5000,
         attempts=12000,check=None):
    """Return (position,radius,normal,source,scale,triangle,barycentric) records.

    Contact propagation gives hexagonal domains for equal radii. Noise is sampled
    at each final center. Rejected candidates never shrink to fit a gap: the
    specified field remains authoritative. Bounded deterministic gap reseeding.
    """
    if not radii or min(radii)<=0: raise ValueError('Source footprint must have a positive radius')
    if not math.isfinite(size) or size<=0: return [],'Size is zero'
    feather=max(0.,min(.99,feather)); rng=random.Random(seed)
    maximum=max(radii)*size*(1+feather)
    grid=Grid(2*maximum); queue=0; probes=0; gap_trials=0
    # A single domain direction keeps planar equal-radius packing hexagonal.
    phase=rng.random()*math.tau
    def candidate(hit,src):
        nonlocal probes
        probes+=1
        if check and probes%128==0: check()
        value=max(0.,min(1.,float(sample_scale(hit)))) if feather else .5
        if not math.isfinite(value): raise ValueError('Noise returned a non-finite sample')
        scale=size*(1-feather+2*feather*value)
        return (hit[0],radii[src]*scale,hit[1],src,scale,hit[2],hit[3])
    def accept(item):
        if grid.accepts(item[0],item[1]): grid.insert(item); return True
        return False
    def contact(parent,direction,src):
        r=radii[src]*parent[4]; hit=None
        # Solve distance = r(parent)+r(noise at new point), retaining size field.
        distance=parent[1]+r
        for _ in range(9 if feather else 3):
            target=add(parent[0],mul(direction,distance))
            hit=surface.project(target,max_distance=max(distance*.65,1e-8))
            if not hit or dot(parent[2],hit[1])<.25: return
            item=candidate(hit,src)
            actual=length(sub(hit[0],parent[0])); wanted=parent[1]+item[1]
            if actual<1e-10: return
            error=wanted-actual
            if abs(error)<wanted*1e-6: break
            distance=max(wanted*.25,distance+error*.85)
        if hit:
            # Tiny outward correction improves roundoff at exact contacts.
            if actual<wanted:
                hit=surface.project(add(parent[0],mul(direction,distance+max(error,0.)+wanted*2e-7)),max_distance=distance*.65)
                if not hit: return
                item=candidate(hit,src)
            accept(item)
    try:
        while len(grid.items)<max_count and probes<max_count*220+attempts:
            if queue<len(grid.items):
                parent=grid.items[queue]; queue+=1
                x,z=frame(parent[2]); src=rng.randrange(len(radii))
                steps=6 if feather==0 and max(radii)-min(radii)<1e-9 else 24
                for j in range(steps):
                    angle=phase+j*math.tau/steps
                    contact(parent,add(mul(x,math.cos(angle)),mul(z,math.sin(angle))),src)
                    if len(grid.items)>=max_count: break
                # Two-contact candidates close triangular gaps left by variable radii.
                if steps>6 and len(grid.items)<max_count:
                    neighbors=list(grid.nearby(parent[0]))
                    neighbors.sort(key=lambda q:dot(sub(q[0],parent[0]),sub(q[0],parent[0])))
                    for other in neighbors[1:9]:
                        delta=sub(other[0],parent[0]); distance=length(delta)
                        if distance<1e-9 or dot(parent[2],other[2])<.8: continue
                        r=radii[src]*parent[4]
                        for side in (-1,1):
                            item=None
                            for _ in range(5):
                                a,b=parent[1]+r,other[1]+r
                                along=(a*a-b*b+distance*distance)/(2*distance)
                                h2=a*a-along*along
                                if h2<=0: break
                                tangent=unit(cross(parent[2],delta))
                                target=add(parent[0],add(mul(delta,along/distance),mul(tangent,side*math.sqrt(h2))))
                                hit=surface.project(target,max_distance=a*.4)
                                if hit is None: break
                                item=candidate(hit,src); r=item[1]*(1+1e-6)
                            if item is not None: accept(item)
                            if len(grid.items)>=max_count: break
                        if len(grid.items)>=max_count: break
            else:
                if gap_trials>=attempts: break
                gap_trials+=1
                accept(candidate(surface.sample(rng),rng.randrange(len(radii))))
        status='Instance limit reached' if len(grid.items)>=max_count else 'Packing complete (finite gap search)'
    except InterruptedError:
        status='Cancelled; partial packing'
    return grid.items,status
