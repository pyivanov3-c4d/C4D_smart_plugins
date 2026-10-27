"""Bounded, dependency-free planar liquid outline kernel. Units are scene units."""
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

def edt1(f):
    n=len(f); v=[0]*n; z=[0.]*(n+1); d=[0.]*n
    k=0; z[0]=-1e30; z[1]=1e30
    for q in range(1,n):
        s=((f[q]+q*q)-(f[v[k]]+v[k]*v[k]))/(2.*(q-v[k]))
        while s<=z[k]:
            k-=1
            s=((f[q]+q*q)-(f[v[k]]+v[k]*v[k]))/(2.*(q-v[k]))
        k+=1; v[k]=q; z[k]=s; z[k+1]=1e30
    k=0
    for q in range(n):
        while z[k+1]<q: k+=1
        d[q]=(q-v[k])**2+f[v[k]]
    return d

def edt(mask,w,h,target,check):
    rows=[]
    for y in range(h):
        check(); rows.extend(edt1([0. if bool(v)==target else 1e12 for v in mask[y*w:(y+1)*w]]))
    for x in range(w):
        check(); col=edt1([rows[y*w+x] for y in range(h)])
        for y in range(h): rows[y*w+x]=col[y]
    return rows

def signed_field(rings,w,h,origin,step,check):
    mask=bytearray(w*h)
    for y in range(h):
        check(); py=origin[1]+y*step; cuts=[]
        for ring in rings:
            for a,b in zip(ring,ring[1:]+ring[:1]):
                if (a[1]>py)!=(b[1]>py): cuts.append(a[0]+(py-a[1])*(b[0]-a[0])/(b[1]-a[1]))
        cuts.sort()
        for a,b in zip(cuts[::2],cuts[1::2]):
            left=max(0,int(math.ceil((a-origin[0])/step))); right=min(w,int(math.ceil((b-origin[0])/step)))
            if right>left: mask[y*w+left:y*w+right]=b'\1'*(right-left)
    # One unsigned boundary transform replaces two full inside/outside transforms.
    boundary=bytearray(w*h)
    for y in range(h):
        check()
        for x in range(w):
            i=y*w+x; v=mask[i]
            boundary[i]=((x>0 and mask[i-1]!=v) or (x+1<w and mask[i+1]!=v) or
                         (y>0 and mask[i-w]!=v) or (y+1<h and mask[i+w]!=v))
    distance=edt(boundary,w,h,True,check)
    return [(-1. if mask[i] else 1.)*(math.sqrt(distance[i])+.5)*step for i in range(w*h)]

def liquid(a,b,collapse,fallow,facing=1.,minimum_gap=0.):
    """Compact attraction. The midpoint crosses zero precisely at gap=collapse."""
    gap=max(0.,a+b)
    if gap<=collapse: k=gap+collapse
    elif fallow>0 and gap<collapse+fallow:
        t=(gap-collapse)/fallow
        t=t*t*(3.-2.*t)  # Flat endpoints keep the strengthened field continuous.
        # Compact inverse-square attenuation: increasing Fallow drives weight
        # toward one and the neck toward collapse, without crossing the threshold.
        weight=max(0.,min(1.,(1./((1.+t)*(1.+t))-.25)/.75))
        directional=min(1.,(gap-collapse)/max(collapse*.5,1e-8))
        directional=directional*directional*(3.-2.*directional)
        weight*=1.-directional*(1.-facing)
        # Square the remaining separation, rather than the attraction itself:
        # 50% attraction becomes 75%, 80% becomes 96%, approaching a thin neck.
        weight=1.-(1.-weight)*(1.-weight)
        # Keep a resolvable slit until Collapse is actually reached. Without it,
        # sub-cell gaps alias into accidental bridges and tiny isolated loops.
        weight=min(weight,1.-max(1e-7,min(1.,minimum_gap/gap)))
        # Calibrate the field to actual boundary travel, not blend strength.
        # For locally parallel facing sides, each boundary moves weight*gap/2.
        # The old k=gap*(1+weight) gave only quadratic, barely visible motion.
        k=gap*(1.+math.sqrt(weight*(2.-weight)))
    else: k=gap  # Baseline changes positive field values only; zero outline is unchanged.
    if k<=1e-12: return min(a,b)
    q=max(0.,1.-abs(a-b)/k)
    return min(a,b)-.25*k*q*q

def contours(field,w,h,origin,step,check):
    # Marching squares, shared edge identities, asymptotic saddle resolution.
    positions={}; neighbors={}
    def edge(x,y,e,values):
        corners=((x,y),(x+1,y),(x+1,y+1),(x,y+1))
        u,v=((0,1),(1,2),(2,3),(3,0))[e]
        a,b=corners[u],corners[v]; key=tuple(sorted((a,b)))
        if key not in positions:
            t=values[u]/(values[u]-values[v])
            positions[key]=(origin[0]+(a[0]+(b[0]-a[0])*t)*step,origin[1]+(a[1]+(b[1]-a[1])*t)*step)
        return key
    for y in range(h-1):
        check()
        for x in range(w-1):
            ids=(y*w+x,y*w+x+1,(y+1)*w+x+1,(y+1)*w+x)
            vals=[field[i] for i in ids]
            crossing=[e for e,(a,b) in enumerate(((0,1),(1,2),(2,3),(3,0))) if (vals[a]<0)!=(vals[b]<0)]
            if len(crossing)==2: pairs=[crossing]
            elif len(crossing)==4:
                center=sum(vals)*.25<0
                pairs=[(0,1),(2,3)] if center==(vals[0]<0) else [(0,3),(1,2)]
            else: continue
            for a,b in pairs:
                a,b=edge(x,y,a,vals),edge(x,y,b,vals)
                neighbors.setdefault(a,[]).append(b); neighbors.setdefault(b,[]).append(a)
    rings=[]; seen=set()
    for start in neighbors:
        if start in seen: continue
        ring=[]; current=start; previous=None
        while current not in seen:
            seen.add(current); ring.append(positions[current])
            choices=neighbors[current]
            following=next((v for v in choices if v!=previous),None)
            previous,current=current,following
            if current is None: break
        if current==start and len(ring)>=3: rings.append(ring)
    return rings

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
        errors=[length(sub(p,evaluate(c,t))) for p,t in zip(samples,ts)]
        worst=max(range(len(errors)),key=errors.__getitem__)
        if errors[worst]<=tolerance or hi-lo<=2:
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
    dim=len(ring[0]); count=len(ring)
    center=tuple(sum(p[a] for p in ring)/count for a in range(dim))
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

def process(groups,collapse,fallow,smooth,check=None,resolution=320,cache=None):
    """Support any common plane, retaining the cheap axis-aligned path."""
    if sum(any(closed and curves for curves,closed in group) for group in groups)<=1:
        return _process_planar(groups,collapse,fallow,smooth,check,resolution,cache)
    pts=[p for group in groups for curves,closed in group if closed for c in curves for p in c]
    if not pts: return [],'No closed child splines'
    spans=[max(p[i] for p in pts)-min(p[i] for p in pts) for i in range(3)]
    if min(spans)<=max(1e-5,max(spans)*1e-4):
        return _process_planar(groups,collapse,fallow,smooth,check,resolution,cache)
    origin=pts[0]
    u=max((sub(p,origin) for p in pts),key=length)
    def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    def dot(a,b): return sum(x*y for x,y in zip(a,b))
    normal=max((cross(u,sub(p,origin)) for p in pts),key=length)
    if length(normal)<1e-12: return _process_planar(groups,collapse,fallow,smooth,check,resolution,cache)
    u=tuple(x/length(u) for x in u); normal=tuple(x/length(normal) for x in normal)
    v=cross(normal,u)
    if max(abs(dot(sub(p,origin),normal)) for p in pts)>max(1e-5,max(spans)*1e-4):
        return _process_planar(groups,collapse,fallow,smooth,check,resolution,cache)
    basis=(u,v,normal)
    def project(p): return tuple(dot(sub(p,origin),axis) for axis in basis)
    transformed=[[([tuple(project(p) for p in c) for c in curves],closed) for curves,closed in group] for group in groups]
    result,status=_process_planar(transformed,collapse,fallow,smooth,check,resolution,cache)
    def restore(p): return tuple(origin[i]+sum(p[j]*basis[j][i] for j in range(3)) for i in range(3))
    return [([tuple(restore(p) for p in c) for c in curves],closed) for curves,closed in result],status

def _process_planar(groups,collapse,fallow,smooth,check=None,resolution=320,cache=None):
    check=check or WorkBudget()
    valid=[[(curves,True) for curves,closed in group if closed and curves] for group in groups]
    valid=[g for g in valid if g]
    originals=[p for g in valid for p in g]
    if not originals: return [],'No closed child splines'
    pts=[p for curves,_ in originals for c in curves for p in c]
    ranges=[max(p[i] for p in pts)-min(p[i] for p in pts) for i in range(3)]
    scale=max(ranges); tolerance=max(scale/2000,1e-6)
    # A single child must only undergo overall smoothing, never liquid union.
    def smoothed(paths):
        if smooth<=0: return paths
        result=[]
        for curves,_ in paths:
            r=round_drop(flatten(curves,tolerance,check),smooth)
            result.append((fit_closed(r,tolerance,check),True))
        return result
    if len(valid)==1: return smoothed(originals),'Single child: smoothing only'
    flat_axis=min(range(3),key=lambda i:ranges[i]); axes=[i for i in range(3) if i!=flat_axis]
    if ranges[flat_axis]>max(1e-5,scale*1e-4):
        return smoothed(originals),'Non-coplanar input: smoothing only (use a common plane)'
    level=sum(p[flat_axis] for p in pts)/len(pts)
    shapes=[]; retained=[]
    for group in valid:
        try:
            rings=[]
            for curves,_ in group:
                r=flatten(curves,tolerance,check)
                if len(r)>=3: rings.append([(p[axes[0]],p[axes[1]]) for p in r])
            shapes.extend(islands(rings))
        except EvaluationStopped:
            retained.extend(group)
    # Partition distant shapes to avoid resolution loss across large empty spaces.
    boxes=[(min(p[0] for r in s for p in r),min(p[1] for r in s for p in r),max(p[0] for r in s for p in r),max(p[1] for r in s for p in r)) for s in shapes]
    influence=collapse+fallow; pending=set(range(len(shapes))); clusters=[]
    while pending:
        cluster=[pending.pop()]
        for i in cluster:
            a=boxes[i]
            for j in list(pending):
                b=boxes[j]; dx=max(0,a[0]-b[2],b[0]-a[2]); dy=max(0,a[1]-b[3],b[1]-a[3])
                if math.hypot(dx,dy)<=influence+tolerance: pending.remove(j); cluster.append(j)
        clusters.append(cluster)
    output=list(retained); largest_step=0.; stopped=0
    def lift(r,fit_tolerance=None):
        points=[]
        for p in r:
            q=[0.,0.,0.]; q[flat_axis]=level; q[axes[0]],q[axes[1]]=p; points.append(tuple(q))
        return (fit_closed(points,fit_tolerance,check) if fit_tolerance is not None else [line(a,b) for a,b in zip(points,points[1:]+points[:1])],True)
    for cluster in clusters:
        try:
            check()
            if len(cluster)==1:
                # Use original cubics when the island can be identified without edits.
                for ring in shapes[cluster[0]]:
                    matched=next((p for p in originals if all(abs(p[0][0][0][axes[k]]-ring[0][k])<1e-8 for k in (0,1))),None)
                    if matched: output.extend(smoothed([matched]))
                    else: output.append(lift(round_drop(ring,smooth),tolerance))
                continue
            if len(cluster)>24: raise EvaluationStopped('More than 24 interacting islands')
            b=[boxes[i] for i in cluster]; span=max(max(v[2] for v in b)-min(v[0] for v in b),max(v[3] for v in b)-min(v[1] for v in b))
            step=max(span/resolution,1e-7); largest_step=max(largest_step,step)
            pad=max(4*step,collapse*.6)
            origin=(min(v[0] for v in b)-pad,min(v[1] for v in b)-pad)
            w=int(math.ceil((max(v[2] for v in b)+pad-origin[0])/step))+1
            h=int(math.ceil((max(v[3] for v in b)+pad-origin[1])/step))+1
            if w*h>350000: raise EvaluationStopped('Distance/grid size limit')
            field_key=(tuple(tuple(tuple(r) for r in shapes[i]) for i in cluster),w,h,origin,step)
            contour_key=(field_key,collapse,fallow)
            memo=cache if cache is not None else {}
            raw=memo.get('contours',{}).get(contour_key)
            if raw is None:
                saved=memo.get('fields')
                if saved is not None and saved[0]==field_key:
                    fields=saved[1]
                else:
                    fields=[signed_field(shapes[i],w,h,origin,step,check) for i in cluster]
                    if w*h*len(fields)<=500000: memo['fields']=(field_key,fields)
                    else: memo.pop('fields',None)
                field=[]
                two=len(fields)==2
                for index in range(w*h):
                    if index%w==0: check()
                    if two: ia,ib=0,1; a,b=fields[0][index],fields[1][index]
                    else:
                        a=b=float('inf'); ia=ib=0
                        for candidate,values in enumerate(fields):
                            value=values[index]
                            if value<a: a,b=value,a; ia,ib=candidate,ia
                            elif value<b: b=value; ib=candidate
                    facing=1.
                    gap=a+b
                    if collapse<gap<collapse+fallow:
                        x=index%w; y=index//w
                        left=y*w+max(0,x-8); right=y*w+min(w-1,x+8)
                        down=max(0,y-8)*w+x; up=min(h-1,y+8)*w+x
                        fa,fb=fields[ia],fields[ib]
                        ax,ay=fa[right]-fa[left],fa[up]-fa[down]
                        bx,by=fb[right]-fb[left],fb[up]-fb[down]
                        norm=math.sqrt((ax*ax+ay*ay)*(bx*bx+by*by))
                        # Pull only mutually facing sides, never inflate the backs.
                        facing=max(0.,min(1.,-(ax*bx+ay*by)/norm)) if norm>1e-20 else 0.
                    field.append(liquid(a,b,collapse,fallow,facing,step*2.5))
                # Reject sub-cell loops caused by quantization at a thin neck.
                raw=[r for r in contours(field,w,h,origin,step,check) if abs(area(r))>=step*step*2.]
                saved=memo.setdefault('contours',{})
                if len(saved)>=4: saved.clear()
                saved[contour_key]=raw
            for ring in raw:
                # Filter ~2 grid cells before fitting, independent of user Smooth.
                perimeter=sum(length(sub(b,a)) for a,b in zip(ring,ring[1:]+ring[:1]))
                antialias=80.*step/max(perimeter,1e-9)
                ring=smooth_ring(ring,antialias,step)
                ring=round_drop(ring,smooth,step)
                output.append(lift(ring,step*.65))
        except EvaluationStopped:
            stopped+=1
            for index in cluster:
                for ring in shapes[index]:
                    matched=next((p for p in originals if all(abs(p[0][0][0][axes[k]]-ring[0][k])<1e-8 for k in (0,1))),None)
                    output.append(matched if matched else lift(ring))
    return output,'{} closed contours | field tolerance ~{:.4g}'.format(len(output),largest_step)+(' | {} groups retained at work limit'.format(stopped+len(retained)) if stopped or retained else '')
