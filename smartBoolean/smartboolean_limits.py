"""Independent short-side limits for seams on an extrusion's planar surface."""
from collections import deque
import smartboolean_cleanup as g
from smartboolean_retopology import normal

def planar_clearance(points, faces, seam, tolerance, requested):
    """Limit against unselected feature boundaries on the seam's flat side."""
    edges=g.edge_map(faces);vertices={v for e in seam for v in e}
    if not vertices:return requested
    origin=points[next(iter(vertices))]
    normals=[normal(points,f) for f in faces]
    adjacent={i for e in seam for i,j in edges.get(e,())}
    axis=next((normals[i] for i in sorted(adjacent) if g.length(normals[i])>.5 and
        all(abs(g.dot(g.sub(points[v],origin),normals[i]))<=tolerance for v in vertices)),None)
    if axis is None:return requested
    flat={i for i,f in enumerate(faces) if all(abs(g.dot(g.sub(points[v],origin),axis))<=tolerance for v in f)}
    links=[[] for f in faces]
    for e,sides in edges.items():
        if e in seam or len(sides)!=2:continue
        a,b=sides[0][0],sides[1][0]
        if a in flat and b in flat:links[a].append(b);links[b].append(a)
    region=flat & adjacent;todo=deque(region)
    while todo:
        for j in links[todo.popleft()]:
            if j not in region:region.add(j);todo.append(j)
    boundary=[e for e,sides in edges.items() if e not in seam and
              any(i in region for i,j in sides) and
              (len(sides)!=2 or not all(i in region for i,j in sides))]
    limit=requested
    for a,b in boundary:
        A,B=points[a],points[b]
        for c,d in seam:
            C,D=points[c],points[d]
            if any(max(min(A[k],B[k])-max(C[k],D[k]),min(C[k],D[k])-max(A[k],B[k]))>limit for k in range(3)):continue
            distance=min(g.segment_distance2(A,C,D),g.segment_distance2(B,C,D),
                         g.segment_distance2(C,A,B),g.segment_distance2(D,A,B))**.5
            if distance>tolerance:limit=min(limit,max(tolerance,distance-tolerance*4))
    return limit

def plan(points, faces, seam, width, tolerance):
    """Find straight wall clearance, ignoring coplanar grid subdivisions.

    Return None for unsupported/nonplanar seams. No topology is changed here.
    """
    if not seam: return None
    edges=g.edge_map(faces)
    vertices={v for e in seam for v in e}
    origin=points[next(iter(vertices))]
    normals=[normal(points,f) for f in faces]
    adjacent={i for e in seam for i,j in edges.get(e,())}
    axis=None
    for i in sorted(adjacent):
        n=normals[i]
        if g.length(n)>.5 and all(abs(g.dot(g.sub(points[v],origin),n))<=tolerance for v in vertices):
            axis=n;break
    if axis is None: return None
    def level(v): return g.dot(g.sub(points[v],origin),axis)
    wall={i for i,n in enumerate(normals) if g.length(n)>.5 and abs(g.dot(n,axis))<1e-6}
    seeds=adjacent & wall
    if not seeds: return None
    links=[[] for f in faces]
    for e,sides in edges.items():
        if e in seam or len(sides)!=2: continue
        a,b=sides[0][0],sides[1][0]
        if a in wall and b in wall: links[a].append(b);links[b].append(a)
    region=set(seeds);todo=deque(seeds)
    while todo:
        for j in links[todo.popleft()]:
            if j not in region: region.add(j);todo.append(j)
    limits={-1:[],1:[]}
    for e,sides in edges.items():
        if e in seam: continue
        inside=[i for i,j in sides if i in region]
        if not inside or len(inside)==len(sides) and len(sides)==2: continue
        values=[level(v) for v in e]
        for sign in (-1,1):
            if min(sign*t for t in values)>tolerance:
                limits[sign].append(min(sign*t for t in values))
    spans={}
    for sign,values in limits.items():
        if not values: continue
        # Only a constant-height extrusion strip is supported. A varying height
        # requires per-station clipping, not a global deformation of that side.
        h=min(values)
        if max(values)-h>tolerance*10: continue
        if width>h+tolerance: spans[sign]=(h,(width+tolerance*4)/h)
    return (origin,axis,spans) if spans else None

def transform(points, limiter, inverse=False):
    origin,axis,spans=limiter
    result=[]
    for p in points:
        t=g.dot(g.sub(p,origin),axis);sign=1 if t>=0 else -1
        if sign not in spans: result.append(tuple(p));continue
        h,scale=spans[sign];u=abs(t)
        if inverse:
            v=u/scale if u<=h*scale else u-h*(scale-1)
        else:
            v=u*scale if u<=h else u+h*(scale-1)
        shift=sign*v-t
        result.append(tuple(p[k]+axis[k]*shift for k in range(3)))
    return result
