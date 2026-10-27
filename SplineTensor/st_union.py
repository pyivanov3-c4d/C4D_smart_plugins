"""Planar polygon union by boundary arrangement; no external dependencies."""
import math
from st_spatial import segment_pairs
from collections import defaultdict
from st_geometry import (GeometryError, area, inside, orient, on_segment,
                         validate_loop, unit, sub, cross, dot)


def union_loops(loops, eps, _predicate=None, _regions=False):
    loops = [list(p) if area(p)>0 or _regions else list(reversed(p)) for p in loops]
    if not _regions:
        for p in loops:
            validate_loop(p,eps)
    segments = [(p[i-1],b) for p in loops for i,b in enumerate(p)]
    cuts = [[0.,1.] for _ in segments]
    def parameter(p,a,b):
        v=sub(b,a)
        return dot(sub(p,a),v)/dot(v,v)
    for i,j in segment_pairs(segments,eps):
        a,b=segments[i];c,d=segments[j]
        r=sub(b,a)
        s=sub(d,c)
        den=r[0]*s[1]-r[1]*s[0]
        q=sub(c,a)
        if abs(den)>eps*max(math.hypot(*r),math.hypot(*s)):
            t=(q[0]*s[1]-q[1]*s[0])/den
            u=(q[0]*r[1]-q[1]*r[0])/den
            if -1e-12<=t<=1+1e-12 and -1e-12<=u<=1+1e-12:
                cuts[i].append(max(0.,min(1.,t)))
                cuts[j].append(max(0.,min(1.,u)))
        else:
            for p in (c,d):
                if on_segment(a,b,p,eps): cuts[i].append(max(0.,min(1.,parameter(p,a,b))))
            for p in (a,b):
                if on_segment(c,d,p,eps): cuts[j].append(max(0.,min(1.,parameter(p,c,d))))
    # Weld independently calculated intersection positions using nearby bins.
    points=[]
    bins=defaultdict(list)
    def vertex(p):
        cell=(math.floor(p[0]/eps),math.floor(p[1]/eps))
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for i in bins[(cell[0]+dx,cell[1]+dy)]:
                    if math.hypot(*sub(points[i],p))<=eps:
                        return i
        i=len(points); points.append(p); bins[cell].append(i)
        return i
    edges=set()
    for (a,b),ts in zip(segments,cuts):
        r=sub(b,a)
        ts=sorted(set(ts))
        for lo,hi in zip(ts,ts[1:]):
            p=tuple(a[k]+lo*r[k] for k in range(2))
            q=tuple(a[k]+hi*r[k] for k in range(2))
            length=math.hypot(*sub(q,p))
            if length<=eps: continue
            mid=tuple((p[k]+q[k])/2 for k in range(2))
            delta=min(eps*4,length*.01)
            normal=(-(q[1]-p[1])/length,(q[0]-p[0])/length)
            left=tuple(mid[k]+delta*normal[k] for k in range(2))
            right=tuple(mid[k]-delta*normal[k] for k in range(2))
            il=_predicate(left) if _predicate else any(inside(left,loop) for loop in loops)
            ir=_predicate(right) if _predicate else any(inside(right,loop) for loop in loops)
            if il==ir: continue
            a_id,b_id=vertex(p),vertex(q)
            edges.add((a_id,b_id) if il else (b_id,a_id))
    outgoing=defaultdict(list)
    incoming=defaultdict(list)
    for a,b in edges:
        outgoing[a].append(b); incoming[b].append(a)
    if any((len(outgoing[i])!=len(incoming[i]) or not outgoing[i]) if _regions else
           (len(outgoing[i])!=1 or len(incoming[i])!=1) for i in set(outgoing)|set(incoming)):
        raise GeometryError('Union has point-touching or ambiguous boundaries. Slightly overlap or separate the shapes.')
    result=[]
    unused=set(edges)
    while unused:
        a,b=min(unused); start=a; loop=[]
        while True:
            loop.append(points[a]); unused.remove((a,b)); previous=a; a=b
            if a==start: break
            if _regions and len(outgoing[a])>1:
                reverse=math.atan2(points[previous][1]-points[a][1],points[previous][0]-points[a][0])
                b=min(outgoing[a],key=lambda idx:(reverse-math.atan2(points[idx][1]-points[a][1],points[idx][0]-points[a][0]))%math.tau)
            else:b=outgoing[a][0]
            if (a,b) not in unused: raise GeometryError('Union boundary could not be closed.')
        # Remove split points on straight boundaries before offsetting.
        changed=True
        while changed and len(loop)>3 and not _regions:
            changed=False
            for i,p in enumerate(loop):
                if on_segment(loop[i-1],loop[(i+1)%len(loop)],p,eps):
                    loop.pop(i); changed=True; break
        # At exact contact a region can have two simple boundaries sharing
        # one vertex. Split that walk before validating each boundary.
        pending=[loop]
        while pending:
            part=pending.pop()
            seen={}; split=False
            for i,p in enumerate(part):
                key=tuple(p)
                if key in seen:
                    j=seen[key]
                    pending.extend((part[j:i],part[:j]+part[i:]))
                    split=True
                    break
                seen[key]=i
            if split:continue
            if len(part)<3:continue
            validate_loop(part,eps)
            if area(part)<0 and not _regions:
                raise GeometryError('Union encloses a hole. Hole-shaped relief unions are not supported yet.')
            result.append(part)
    if not result and not _regions: raise GeometryError('Union has no usable area.')
    return result


def unite_contours(base, contours, height_vector=None, nested_masks=False):
    """Project shapes, combine by union or even-odd mask, then lift uniformly."""
    origin=base[0]
    normal=(0.,0.,0.)
    for i,p in enumerate(base):
        c=cross(sub(base[i-1],origin),sub(p,origin))
        normal=tuple(normal[k]+c[k] for k in range(3))
    normal=unit(normal)
    if normal[max(range(3),key=lambda k:abs(normal[k]))]<0:
        normal=tuple(-x for x in normal)
    u=unit(sub(base[1],origin)); v=unit(cross(normal,u))
    scale=max(max(p[k] for p in base)-min(p[k] for p in base) for k in range(3))
    eps=max(scale*1e-8,1e-9)
    height=(dot(height_vector,normal) if height_vector is not None else
            sum(dot(sub(p,origin),normal) for p in contours[0])/len(contours[0]))
    def lift(p):
        return tuple(origin[k]+p[0]*u[k]+p[1]*v[k]+height*normal[k] for k in range(3))
    loops=[]
    for contour in contours:
        loop=[(dot(sub(p,origin),u),dot(sub(p,origin),v)) for p in contour]
        if len(loop)>1 and math.hypot(*sub(loop[0],loop[-1]))<=eps: loop.pop()
        loops.append(loop)
    # At zero distance do not insert edges, even for overlapping children.
    if abs(height)<=eps:
        return [[lift(p) for p in loops[0]]]
    if not nested_masks:
        return [[lift(p) for p in loop] for loop in union_loops(loops,eps)]
    for loop in loops:validate_loop(loop,eps)
    def filled(p):
        return sum(inside(p,loop) for loop in loops)%2==1
    regions=union_loops(loops,eps,_predicate=filled,_regions=True)
    return [[lift(p) for p in loop] for loop in regions]
