"""Local planar offset limits and expansion of a safe reference bevel."""
from collections import defaultdict
from math import floor
import smartboolean_cleanup as g
from smartboolean_retopology import normal
from smartboolean_spatial import BoxIndex, bounds

def feature_edges(points,faces,edges,seam,tol):
    def face_normal(face):
        n=[0.,0.,0.]
        for a,b in zip(face,face[1:]+face[:1]):
            cross=g.cross(points[a],points[b])
            for k in range(3):n[k]+=cross[k]
        length=g.length(n)
        return tuple(x/length for x in n) if length>tol*tol else (0.,0.,0.)
    normals=[face_normal(f) for f in faces]
    return [e for e,sides in edges.items() if e not in seam and
            (len(sides)!=2 or abs(g.dot(normals[sides[0][0]],normals[sides[1][0]]))<1-1e-7)]


def spatial_plan(points,faces,edges,seam,vertices,width,tol):
    """Keep 3D feature-boundary limits when a seam wraps multiple planes.

    The native reference bevel supplies each point's 3D trajectory. There is
    no single extrusion axis here, so a local limit scales that whole profile.
    Coplanar tessellation edges are excluded from the boundary tests.
    """
    degree=defaultdict(int)
    for a,b in seam:
        if len(edges.get((a,b),()))!=2:return None
        degree[a]+=1;degree[b]+=1
    if any(n!=2 for n in degree.values()):return None
    reference=min(width*.02,min(g.length(g.sub(points[a],points[b])) for a,b in seam)*.1)
    if reference<=tol*100:return None
    return dict(points=points,axis=(0.,0.,0.),velocity={},
                caps={v:width for v in vertices},reference=reference,width=width,
                tolerance=tol,seam=seam,orthogonal=False,spatial=True,
                features=feature_edges(points,faces,edges,seam,tol))


def plan(points,faces,seam,width,tol,progress=None):
    if not points or not seam:return None
    edges=g.edge_map(faces);vertices={v for e in seam for v in e}
    origin=points[next(iter(vertices))]
    adjacent={i for e in seam for i,j in edges.get(e,())}
    axis=next((n for i in sorted(adjacent) for n in [normal(points,faces[i])]
        if g.length(n)>.5 and all(abs(g.dot(g.sub(points[v],origin),n))<=tol for v in vertices)),None)
    if axis is None:return spatial_plan(points,faces,edges,seam,vertices,width,tol)
    directions={v:[] for v in vertices};orthogonal=True
    for a,b in seam:
        delta=g.sub(points[b],points[a]);length=g.length(delta)
        if length<=tol:return None
        ns=[normal(points,faces[i]) for i,j in edges.get((a,b),())]
        if len(ns)!=2:return None
        orthogonal=orthogonal and abs(g.dot(ns[0],ns[1]))<=1e-6
        flat=[i for i,j in edges.get((a,b),()) if all(abs(g.dot(g.sub(points[v],origin),axis))<=tol for v in faces[i])]
        if len(flat)!=1:return None
        inward=g.cross(axis,tuple(x/length for x in delta));f=faces[flat[0]]
        center=tuple(sum(points[v][k] for v in f)/len(f) for k in range(3))
        if g.dot(g.sub(center,points[a]),inward)<0:inward=tuple(-x for x in inward)
        directions[a].append(inward);directions[b].append(inward)
    velocity={}
    for v,ns in directions.items():
        if len(ns)!=2:return None
        denom=1+g.dot(ns[0],ns[1])
        if denom<1e-8:return None
        velocity[v]=tuple((ns[0][k]+ns[1][k])/denom for k in range(3))
    caps={v:width for v in vertices};turn_links=defaultdict(set)
    for a,b in seam:
        delta=g.sub(points[b],points[a]);length=g.length(delta)
        speed=g.dot(g.sub(velocity[b],velocity[a]),delta)/length
        if speed < -1e-10:
            turn_links[a].add(b);turn_links[b].add(a)
            event=length/-speed
            if event*.85<width:
                # Keep a visible offset contour rather than an almost collapsed
                # fan: at constant curvature this retains 15% of its radius.
                safe=max(tol,event-max(tol*16,event*.15))
                caps[a]=min(caps[a],safe);caps[b]=min(caps[b],safe)
    # One rounded concave turn needs one offset, not a separate radius at each
    # sample. Pointwise radii trace a focal curve and produce a pointed fan.
    remaining=set(turn_links)
    while remaining:
        start=remaining.pop();component={start};todo=[start]
        while todo:
            for v in turn_links[todo.pop()]:
                if v in remaining:remaining.remove(v);component.add(v);todo.append(v)
        local=min(caps[v] for v in component)
        for v in component:caps[v]=local
    # A concave gap (including gaps between letters) closes by vertex/edge
    # contact before an individual edge necessarily collapses.
    def area(a,b):return g.dot(g.cross(a,b),axis)
    def at(v,t):return tuple(points[v][k]+velocity[v][k]*t for k in range(3))
    boxes={v:tuple((min(points[v][k],at(v,width)[k])-tol,
                    max(points[v][k],at(v,width)[k])+tol) for k in range(3)) for v in vertices}
    vertex_order=list(vertices)
    index=BoxIndex([tuple(boxes[v][k][0] for k in range(3))+tuple(boxes[v][k][1] for k in range(3)) for v in vertex_order])
    for number,(a,b) in enumerate(seam):
        if progress and number%16==0:progress(number,len(seam),'Checking bevel intersections')
        box=tuple((min(boxes[a][k][0],boxes[b][k][0]),max(boxes[a][k][1],boxes[b][k][1])) for k in range(3))
        edge=g.sub(points[b],points[a]);dv=g.sub(velocity[b],velocity[a])
        query=tuple(box[k][0] for k in range(3))+tuple(box[k][1] for k in range(3))
        for vi in index.query(query):
            v=vertex_order[vi]
            if v in (a,b) or any(boxes[v][k][1]<box[k][0] or boxes[v][k][0]>box[k][1] for k in range(3)):continue
            rel=g.sub(points[v],points[a]);rv=g.sub(velocity[v],velocity[a])
            A=area(dv,rv);B=area(edge,rv)+area(dv,rel);C=area(edge,rel)
            if abs(A)<1e-12:roots=[] if abs(B)<1e-12 else [-C/B]
            else:
                disc=B*B-4*A*C
                if disc<0:continue
                root=disc**.5;q=-.5*(B+(root if B>=0 else -root))
                roots=[q/A,C/q] if abs(q)>1e-30 else [-B/(2*A)]
            for t in roots:
                if t<=tol or t>width:continue
                if g.segment_distance2(at(v,t),at(a,t),at(b,t))<=tol*tol*16:
                    safe=max(tol,t-max(tol*16,t*.001))
                    for u in (a,b,v):caps[u]=min(caps[u],safe)
    # Limit transitions locally along the seam, without capping distant stations.
    links=defaultdict(list)
    for a,b in seam:
        distance=g.length(g.sub(points[a],points[b]))
        links[a].append((b,distance));links[b].append((a,distance))
    import heapq
    queue=[(c,v) for v,c in caps.items()];heapq.heapify(queue)
    while queue:
        c,v=heapq.heappop(queue)
        if c>caps[v]:continue
        for u,d in links[v]:
            candidate=c+d*.5
            if candidate<caps[u]:caps[u]=candidate;heapq.heappush(queue,(candidate,u))
    reference=min(width*.02,min(caps.values())*.1)
    if reference<=tol*100:return None
    features=feature_edges(points,faces,edges,seam,tol)
    return dict(points=points,axis=axis,velocity=velocity,caps=caps,
                reference=reference,width=width,tolerance=tol,seam=seam,orthogonal=orthogonal,features=features)

def expand(first,second,setup,faces=None,progress=None):
    """Extrapolate matching native reference topology with station-local widths."""
    if len(first)!=len(second):return None
    source=setup['points'];axis=setup['axis'];caps=setup['caps']
    ref=setup['reference'];width=setup['width'];tol=setup['tolerance']
    cache={};stations={};result=[];bins=defaultdict(list);records=[];feature_caps={};slides={}
    feature_neighbors=defaultdict(list)
    for a,b in setup['features']:
        feature_neighbors[a].append(b);feature_neighbors[b].append(a)
    def continuation(anchor,direction,vertex):
        height=g.dot(direction,axis)
        if abs(height)<1e-8:return None
        target=g.dot(anchor,axis)+height*width
        start=g.dot(source[vertex],axis)
        for other in feature_neighbors[vertex]:
            delta=g.sub(source[other],source[vertex]);along=g.dot(delta,axis)
            transverse=tuple(delta[k]-along*axis[k] for k in range(3))
            if g.length(transverse)>tol*128 or along*height<=0:continue
            finish=start+along
            if min(start,finish)-tol<=target<=max(start,finish)+tol:
                shift=g.sub(source[vertex],anchor);sh=g.dot(shift,axis)
                transverse=tuple(shift[k]-sh*axis[k] for k in range(3))
                direction_flat=tuple(direction[k]-height*axis[k] for k in range(3))
                return transverse,height,direction_flat,sh
        return None
    cell=max(width,tol*1000)
    features=setup['features']
    feature_index=BoxIndex([bounds(source[a],source[b]) for a,b in features])
    for a,b in setup['seam']:
        lo=[floor((min(source[a][k],source[b][k])-tol*128)/cell) for k in range(3)]
        hi=[floor((max(source[a][k],source[b][k])+tol*128)/cell) for k in range(3)]
        # Extremely long diagonal edges should not allocate an unbounded grid.
        if (hi[0]-lo[0]+1)*(hi[1]-lo[1]+1)*(hi[2]-lo[2]+1)>100000:return None
        for x in range(lo[0],hi[0]+1):
            for y in range(lo[1],hi[1]+1):
                for z in range(lo[2],hi[2]+1):bins[(x,y,z)].append((a,b))
    for number,(p,q) in enumerate(zip(first,second)):
        if progress and number%32==0:progress(number,len(first),'Building bevel profiles')
        delta=g.sub(q,p)
        if g.length(delta)<tol:records.append((tuple(p),None,None,None));continue
        anchor=tuple(2*p[k]-q[k] for k in range(3))
        key=tuple(round(x/(tol*128)) for x in anchor)
        if key not in cache:
            candidates=bins.get(tuple(floor(x/cell) for x in anchor),())
            if not candidates:return None
            a,b=min(candidates,key=lambda e:g.segment_distance2(anchor,source[e[0]],source[e[1]]))
            if g.segment_distance2(anchor,source[a],source[b])>(tol*128)**2:return None
            edge=g.sub(source[b],source[a])
            t=max(0.,min(1.,g.dot(g.sub(anchor,source[a]),edge)/g.dot(edge,edge)))
            cache[key]=caps[a]*(1-t)+caps[b]*t
            stations[key]=(a,b,t)
        # Stop an entire local profile when its surface endpoint reaches a
        # genuine feature edge. Coplanar tessellation does not impose a limit.
        direction=tuple(x/ref for x in delta)
        feature_caps.setdefault(key,setup.get('overrides',{}).get(key,width))
        end=tuple(anchor[k]+direction[k]*width for k in range(3))
        for fi in feature_index.query(bounds(anchor,end,tol*128)):
            a,b=features[fi]
            A,B=source[a],source[b]
            if any(max(min(A[k],B[k])-max(anchor[k],end[k]),min(anchor[k],end[k])-max(A[k],B[k]))>tol*128 for k in range(3)):continue
            edge=g.sub(B,A);cross=g.cross(direction,edge);denom=g.dot(cross,cross)
            if denom<1e-16:continue
            rel=g.sub(A,anchor)
            t=g.dot(g.cross(rel,edge),cross)/denom
            u=g.dot(g.cross(rel,direction),cross)/denom
            if t<=tol*128 or t>width or u < -tol or u>1+tol:continue
            residual=tuple(anchor[k]+direction[k]*t-A[k]-edge[k]*u for k in range(3))
            if g.length(residual)<=tol*128:
                vertex=a if g.length(g.sub(tuple(anchor[k]+direction[k]*t for k in range(3)),A))<=tol*128 else b if g.length(g.sub(tuple(anchor[k]+direction[k]*t for k in range(3)),B))<=tol*128 else None
                slide=continuation(anchor,direction,vertex) if vertex is not None else None
                if slide is not None:
                    if key not in slides or abs(slide[1])>abs(slides[key][1]):slides[key]=slide
                    continue
                feature_caps[key]=min(feature_caps[key],max(tol,t-max(tol*16,t*.001)))
        records.append((anchor,delta,key,cache[key]))
    vertex_features={v:width for v in caps}
    for key,value in feature_caps.items():
        a,b,t=stations[key]
        targets=(a,) if t<=1e-6 else (b,) if t>=1-1e-6 else (a,b)
        for v in targets:vertex_features[v]=min(vertex_features[v],value)
    links=defaultdict(list)
    for a,b in setup['seam']:
        distance=g.length(g.sub(source[a],source[b]))*.25
        links[a].append((b,distance));links[b].append((a,distance))
    import heapq
    queue=[(value,v) for v,value in vertex_features.items()];heapq.heapify(queue)
    while queue:
        value,v=heapq.heappop(queue)
        if value>vertex_features[v]:continue
        for u,d in links[v]:
            if value+d<vertex_features[u]:
                vertex_features[u]=value+d;heapq.heappush(queue,(value+d,u))
    for anchor,delta,key,local in records:
        if delta is None:result.append(anchor);continue
        a,b,t=stations[key]
        feature=min(feature_caps[key],vertex_features[a]*(1-t)+vertex_features[b]*t)
        local=min(local,feature);height=g.dot(delta,axis)
        vertical=min(width,feature) if setup['orthogonal'] else local
        point=tuple(anchor[k]+(delta[k]-axis[k]*height)*local/ref+axis[k]*height*vertical/ref for k in range(3))
        if key in slides:
            transverse,end_height,direction_flat,corner_height=slides[key]
            if abs(end_height*vertical)>abs(corner_height):
                correction=tuple(transverse[k]-direction_flat[k]*local for k in range(3))
                blend=max(0.,min(1.,height/(ref*end_height)))
                point=tuple(point[k]+correction[k]*blend for k in range(3))
        result.append(point)
    if faces is not None:
        affected=set();feature_bins=defaultdict(set)
        def cells(A,B):
            lo=[floor((min(A[k],B[k])-tol*128)/cell) for k in range(3)]
            hi=[floor((max(A[k],B[k])+tol*128)/cell) for k in range(3)]
            if (hi[0]-lo[0]+1)*(hi[1]-lo[1]+1)*(hi[2]-lo[2]+1)>100000:return
            for x in range(lo[0],hi[0]+1):
                for y in range(lo[1],hi[1]+1):
                    for z in range(lo[2],hi[2]+1):yield (x,y,z)
        for e in setup['features']:
            for key in cells(source[e[0]],source[e[1]]):feature_bins[key].add(e)
        output_edges=g.edge_map(faces)
        for number,(a,b) in enumerate(output_edges):
            if progress and number%64==0:progress(number,len(output_edges),'Validating bevel connections')
            if records[a][1] is None and records[b][1] is None:continue
            A,B=result[a],result[b];direction=g.sub(B,A)
            candidates=set()
            for key in cells(A,B):candidates.update(feature_bins.get(key,()))
            for c,d in candidates:
                C,D=source[c],source[d];edge=g.sub(D,C)
                cross=g.cross(direction,edge);denom=g.dot(cross,cross)
                if denom<1e-16:continue
                rel=g.sub(C,A);t=g.dot(g.cross(rel,edge),cross)/denom;u=g.dot(g.cross(rel,direction),cross)/denom
                if not (1e-6<t<1-1e-6 and 1e-6<u<1-1e-6):continue
                if g.length(tuple(A[k]+direction[k]*t-C[k]-edge[k]*u for k in range(3)))>tol*128:continue
                for v in (a,b):
                    if records[v][2] is not None:affected.add(records[v][2])
        if affected:
            depth=setup.get('depth',0)
            if depth>=12:return None
            overrides=dict(setup.get('overrides',{}))
            for key in affected:overrides[key]=feature_caps[key]*.8
            retry=dict(setup,overrides=overrides,depth=depth+1)
            return expand(first,second,retry,faces,progress)
    return result

