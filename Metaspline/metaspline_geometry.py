"""Bounded spline sampling, fitting and rounding utilities. Units are scene units."""
import math
import time

class EvaluationStopped(Exception): pass

class WorkBudget:
    def __init__(self, seconds=6., cancel=None):
        self.end = time.monotonic()+seconds
        self.cancel = cancel
    def __call__(self):
        if time.monotonic()>self.end or (self.cancel and self.cancel()):
            raise EvaluationStopped('Geometry budget reached')

def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def length(a): return math.sqrt(sum(x*x for x in a))
def line(a,b): return (a,tuple((2*x+y)/3 for x,y in zip(a,b)),tuple((x+2*y)/3 for x,y in zip(a,b)),b)
def cubic(c,t):
    u=1-t
    return tuple(u*u*u*c[0][i]+3*u*u*t*c[1][i]+3*u*t*t*c[2][i]+t*t*t*c[3][i] for i in range(3))

def flatten(curves, tolerance, check):
    out=[]
    def visit(c,depth):
        check()
        chord=length(sub(c[3],c[0]))
        excess=sum(length(sub(c[i+1],c[i])) for i in range(3))-chord
        if depth>=10 or excess<=tolerance*.2:
            out.append(c[0]); return
        a,b,d=[tuple((x+y)*.5 for x,y in zip(c[i],c[i+1])) for i in range(3)]
        e,f=[tuple((x+y)*.5 for x,y in zip(p,q)) for p,q in ((a,b),(b,d))]
        m=tuple((x+y)*.5 for x,y in zip(e,f))
        visit((c[0],a,e,m),depth+1); visit((m,f,d,c[3]),depth+1)
    for c in curves: visit(c,0)
    if len(out)>12000: raise EvaluationStopped('Contour point limit')
    return out

def inside(p,ring):
    x,y=p; hit=False
    for a,b in zip(ring,ring[1:]+ring[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: hit=not hit
    return hit

def area(r): return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(r,r[1:]+r[:1]))*.5

def islands(rings):
    """Even-odd nesting: outer contours interact, holes stay with their owner."""
    parents=[]
    for i,r in enumerate(rings):
        candidates=[j for j,s in enumerate(rings) if abs(area(s))>abs(area(r)) and inside(r[0],s)]
        parents.append(min(candidates,key=lambda j:abs(area(rings[j]))) if candidates else None)
    def depth(i):
        d=0
        while parents[i] is not None: i=parents[i]; d+=1
        return d
    return [[r]+[rings[j] for j in range(len(rings)) if parents[j]==i and depth(j)%2] for i,r in enumerate(rings) if depth(i)%2==0]

def fit_closed(ring,tolerance,check=None):
    """Adaptive least-squares cubic reconstruction with shared knot tangents.

    Chord-parameter residual bounds subdivision; four initial arcs prevent a
    closed curve's coincident endpoints from making the fit singular.
    """
    check=check or (lambda:None)
    points=[]
    for p in ring:
        if not points or length(sub(p,points[-1]))>1e-10: points.append(tuple(p))
    if len(points)>1 and length(sub(points[0],points[-1]))<1e-10: points.pop()
    n=len(points)
    if n<3: return []
    def unit(v):
        size=length(v)
        return tuple(x/max(size,1e-20) for x in v)
    tangent=[unit(sub(points[(i+1)%n],points[(i-1)%n])) for i in range(n)]
    def dot(a,b): return sum(x*y for x,y in zip(a,b))
    def evaluate(c,t):
        u=1-t
        return tuple(u**3*c[0][i]+3*u*u*t*c[1][i]+3*u*t*t*c[2][i]+t**3*c[3][i] for i in range(len(c[0])))
    result=[]
    def fit(lo,hi):
        check()
        samples=[points[i%n] for i in range(lo,hi+1)]
        a,b=samples[0],samples[-1]; ta,tb=tangent[lo%n],tangent[hi%n]
        distances=[0.]
        for p,q in zip(samples,samples[1:]): distances.append(distances[-1]+length(sub(q,p)))
        total=distances[-1]
        ts=[v/max(total,1e-20) for v in distances]
        aa=ab=bb=ra=rb=0.
        for p,t in zip(samples,ts):
            u=1-t; b1=3*u*u*t; b2=3*u*t*t
            va=tuple(b1*x for x in ta); vb=tuple(-b2*x for x in tb)
            base=tuple((u**3+b1)*x+(t**3+b2)*y for x,y in zip(a,b))
            residual=sub(p,base)
            aa+=dot(va,va); ab+=dot(va,vb); bb+=dot(vb,vb)
            ra+=dot(va,residual); rb+=dot(vb,residual)
        determinant=aa*bb-ab*ab
        alpha=(ra*bb-rb*ab)/determinant if abs(determinant)>1e-15 else total/3
        beta=(rb*aa-ra*ab)/determinant if abs(determinant)>1e-15 else total/3
        if min(alpha,beta)<=1e-10 or max(alpha,beta)>total:
            alpha=beta=length(sub(b,a))/3
        c=(a,tuple(x+alpha*y for x,y in zip(a,ta)),tuple(x-beta*y for x,y in zip(b,tb)),b)
        errors=[length(sub(p,evaluate(c,t)))/(tolerance(p) if callable(tolerance) else tolerance) for p,t in zip(samples,ts)]
        worst=max(range(len(errors)),key=errors.__getitem__)
        if errors[worst]<=1. or hi-lo<=2:
            result.append(c)
        else:
            split=lo+max(1,min(hi-lo-1,worst)); fit(lo,split); fit(split,hi)
    cuts=sorted(set([0,n//4,n//2,3*n//4,n]))
    for lo,hi in zip(cuts,cuts[1:]): fit(lo,hi)
    return result

def smooth_ring(ring,amount,step=None):
    if amount<=0: return ring
    # Arc-length resampling makes Smooth independent of input knot spacing.
    perimeter=sum(length(sub(b,a)) for a,b in zip(ring,ring[1:]+ring[:1]))
    if perimeter<=1e-12: return ring
    n=max(16,min(600,int(perimeter/max(step or perimeter/300,1e-9))))
    out=[]; distance=0.; target=0.; interval=perimeter/n
    for a,b in zip(ring,ring[1:]+ring[:1]):
        span=length(sub(b,a))
        while span>0 and target<distance+span and len(out)<n:
            t=(target-distance)/span; out.append(tuple(x+(y-x)*t for x,y in zip(a,b))); target+=interval
        distance+=span
    # Three sliding box filters approximate Gaussian diffusion in O(n).
    sigma=amount*n*.025
    ideal=(math.sqrt(1.+4.*sigma*sigma)-1.)*.5
    radius=min(n//2-1,int(ideal)); mix=min(1.,ideal-radius)
    def box(values,r):
        count=len(values); width=2*r+1; dim=len(values[0])
        sums=[sum(values[j%count][a] for j in range(-r,r+1)) for a in range(dim)]
        result=[]
        for i in range(count):
            result.append(tuple(v/width for v in sums))
            for a in range(dim): sums[a]+=values[(i+r+1)%count][a]-values[(i-r)%count][a]
        return result
    for _ in range(3):
        low=box(out,radius); high=box(out,radius+1)
        out=[tuple(a+(b-a)*mix for a,b in zip(p,q)) for p,q in zip(low,high)]
    return out

def round_drop(ring,amount,step=None):
    """Area-preserving diffusion, progressing to a round equilibrium drop."""
    if amount<=0: return ring
    dim=len(ring[0])
    # Vertex density is highly uneven around a new neck. Use an arc-length
    # reference centroid; a raw vertex mean caused a jump even at tiny Smooth.
    reference=smooth_ring(ring,1e-12,step)
    center=tuple(sum(p[a] for p in reference)/len(reference) for a in range(dim))
    # Polygon area vector also works for arbitrary planar 3D single children.
    def surface(points):
        total=[0.,0.,0.]
        for p,q in zip(points,points[1:]+points[:1]):
            a=list(p)+[0.]*(3-dim); b=list(q)+[0.]*(3-dim)
            total[0]+=a[1]*b[2]-a[2]*b[1]
            total[1]+=a[2]*b[0]-a[0]*b[2]
            total[2]+=a[0]*b[1]-a[1]*b[0]
        return length(total)*.5
    target=surface(ring)
    out=smooth_ring(ring,amount*10.,step)
    origin=tuple(sum(p[a] for p in out)/len(out) for a in range(dim))
    factor=math.sqrt(target/max(surface(out),1e-20))
    out=[tuple(center[a]+(p[a]-origin[a])*factor for a in range(dim)) for p in out]
    # A first-harmonic frame keeps the circle in-plane and consistently oriented.
    n=len(out); u=[0.]*dim; v=[0.]*dim
    for i,p in enumerate(out):
        angle=math.tau*i/n
        for a in range(dim):
            u[a]+=(p[a]-center[a])*math.cos(angle)
            v[a]+=(p[a]-center[a])*math.sin(angle)
    ul=length(u)
    if ul<1e-12: return out
    u=[x/ul for x in u]; dot=sum(a*b for a,b in zip(u,v))
    v=[b-dot*a for a,b in zip(u,v)]; vl=length(v)
    if vl<1e-12: return out
    v=[x/vl for x in v]; radius=math.sqrt(target/math.pi)
    blend=amount*amount*(3.-2.*amount)
    result=[]
    for i,p in enumerate(out):
        angle=math.tau*i/n
        q=tuple(center[a]+radius*(u[a]*math.cos(angle)+v[a]*math.sin(angle)) for a in range(dim))
        result.append(tuple(a+(b-a)*blend for a,b in zip(p,q)))
    factor=math.sqrt(target/max(surface(result),1e-20))
    return [tuple(center[a]+(p[a]-center[a])*factor for a in range(dim)) for p in result]

def process(groups,collapse,fallow,smooth,check=None,resolution=320,cache=None,progress=None,viscosity=.25):
    from metaspline_vector import process as vector_process
    return vector_process(groups,collapse,fallow,smooth,check,resolution,cache,progress,viscosity)
