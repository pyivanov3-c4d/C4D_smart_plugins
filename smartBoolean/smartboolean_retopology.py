"""Conforming local planar collar reconstruction. No Cinema 4D dependency."""
import math
from collections import defaultdict, Counter
import smartboolean_cleanup as g
from smartboolean_earcut import earcut

def transfer_uv(points, faces, uv, new_points, new_faces, tolerance, strict=True):
    """Copy unchanged UV corners; interpolate only consistent planar UV charts.

    Reject discontinuous charts rather than silently erase a UV seam.
    """
    def key(p): return tuple(round(c/tolerance) for c in p)
    exact={tuple(key(points[v]) for v in f):i for i,f in enumerate(faces)}
    vertex_faces=defaultdict(set)
    for i,f in enumerate(faces):
        for v in f:vertex_faces[key(points[v])].add(i)
    def plane(p,f):
        n=normal(p,f)
        return tuple(round(c,6) for c in n)+(round(g.dot(n,p[f[0]]),6),)
    planes=defaultdict(list)
    for i,f in enumerate(faces): planes[plane(points,f)].append(i)
    models={}
    def model(k):
        if k in models: return models[k]
        members=planes.get(k,[])
        if not members: raise ValueError('No source UV plane')
        i=members[0]; f=faces[i]; A,B,C=(points[v] for v in f[:3])
        u,v=g.sub(B,A),g.sub(C,A)
        uu,uv,vv=g.dot(u,u),g.dot(u,v),g.dot(v,v)
        det=uu*vv-uv*uv
        if det<=tolerance**4: raise ValueError('Degenerate UV source')
        a,b,c=uv_faces[i][:3]
        def evaluate(p):
            q=g.sub(p,A); qu,qv=g.dot(q,u),g.dot(q,v)
            s,t=(qu*vv-qv*uv)/det,(qv*uu-qu*uv)/det
            return tuple(a[j]+s*(b[j]-a[j])+t*(c[j]-a[j]) for j in range(3))
        for j in members if strict else []:
            for vertex,value in zip(faces[j],uv_faces[j]):
                if g.length(g.sub(evaluate(points[vertex]),value))>1e-5:
                    raise ValueError('Discontinuous or non-affine UV chart')
        models[k]=evaluate
        return evaluate
    uv_faces=uv
    result=[]
    for f in new_faces:
        old=exact.get(tuple(key(new_points[v]) for v in f))
        if old is not None: result.append(uv_faces[old]); continue
        # Splitting a nonplanar quad or inserting a boundary station does not
        # require a new planar UV chart: retain its corner/edge UV values.
        candidates=set()
        for v in f:candidates.update(vertex_faces.get(key(new_points[v]),()))
        boundary_uv=None
        for i in sorted(candidates):
            source=faces[i];values=[]
            for v in f:
                p=new_points[v];value=None
                for j,a in enumerate(source):
                    b=source[(j+1)%len(source)]
                    if g.segment_distance2(p,points[a],points[b])>tolerance*tolerance:continue
                    d=g.sub(points[b],points[a]);den=g.dot(d,d)
                    t=max(0.,min(1.,g.dot(g.sub(p,points[a]),d)/den)) if den else 0.
                    u,w=uv_faces[i][j],uv_faces[i][(j+1)%len(source)]
                    value=tuple(u[k]+t*(w[k]-u[k]) for k in range(3));break
                if value is None:break
                values.append(value)
            if len(values)==len(f):boundary_uv=values;break
        if boundary_uv is not None:result.append(boundary_uv);continue
        evaluate=model(plane(new_points,f))
        result.append([evaluate(new_points[v]) for v in f])
    return result

def normal(points, face):
    v=g.cross(g.sub(points[face[1]],points[face[0]]),g.sub(points[face[2]],points[face[0]]))
    s=g.length(v)
    return tuple(x/s for x in v) if s else (0.,0.,0.)

def boundary_loops(faces):
    edges={}
    for f in faces:
        for a,b in zip(f,f[1:]+f[:1]):
            key=tuple(sorted((a,b)))
            if key in edges: del edges[key]
            else: edges[key]=(a,b)
    links={}
    for a,b in edges.values():
        if a in links: raise ValueError('Branching patch boundary')
        links[a]=b
    loops=[]
    while links:
        start=next(iter(links)); v=start; loop=[]
        while v in links:
            loop.append(v); v=links.pop(v)
        if v!=start: raise ValueError('Open patch boundary')
        loops.append(loop)
    return loops

def triangulate(points, loops, n, tolerance):
    axis=max(range(3),key=lambda i:abs(n[i]))
    axes=[i for i in range(3) if i!=axis]
    def xy(v): return (points[v][axes[0]],points[v][axes[1]])
    def area(r):
        return sum(xy(a)[0]*xy(b)[1]-xy(b)[0]*xy(a)[1] for a,b in zip(r,r[1:]+r[:1]))*.5
    loops=sorted(loops,key=lambda r:abs(area(r)),reverse=True)
    ids=[]; holes=[]
    for ring in loops:
        if ids: holes.append(len(ids))
        ids.extend(ring)
    coords=[c for v in ids for c in xy(v)]
    indices=earcut(coords,holes,2)
    triangles=[tuple(ids[indices[i+j]] for j in range(3)) for i in range(0,len(indices),3)]
    # Earcut can drop collinear boundary vertices; reinsert them as constrained
    # edge splits so the untouched grid has no T-junctions.
    used={v for tri in triangles for v in tri}
    for v in set(ids)-used:
        found=False
        for i,tri in enumerate(triangles):
            for j in range(3):
                a,b,c=tri[j],tri[(j+1)%3],tri[(j+2)%3]
                if g.segment_distance2(points[v],points[a],points[b])<=tolerance*tolerance:
                    triangles[i]=(a,v,c); triangles.append((v,b,c)); found=True; break
            if found: break
        if not found: raise ValueError('Cannot reconnect boundary vertex %d'%v)
    # Align every triangle to the original patch orientation.
    triangles=[t if g.dot(normal(points,t),n)>0 else (t[0],t[2],t[1]) for t in triangles]
    required={tuple(sorted((a,b))) for r in loops for a,b in zip(r,r[1:]+r[:1])}
    edges=Counter(tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1]))
    if {e for e,c in edges.items() if c==1}!=required or any(c>2 for c in edges.values()):
        raise ValueError('Nonconforming triangulation')
    target=abs(area(loops[0]))-sum(abs(area(r)) for r in loops[1:])
    actual=sum(abs(area(list(t))) for t in triangles)
    if abs(target-actual)>max(tolerance*tolerance,target*1e-8):
        raise ValueError('Triangulation area mismatch')
    # Refine until no shorter valid diagonal remains. A fixed number of passes
    # leaves long fans on dense strips: each pass advances only one station.
    from collections import deque
    adjacency=defaultdict(set)
    def tri_edges(t):
        return [tuple(sorted((a,b))) for a,b in zip(t,t[1:]+t[:1])]
    for i,t in enumerate(triangles):
        for e in tri_edges(t): adjacency[e].add(i)
    pending=deque(adjacency); queued=set(adjacency)
    while pending:
        edge=pending.popleft(); queued.discard(edge)
        sides=adjacency.get(edge,())
        if len(sides)!=2: continue
        a,b=edge; i,j=sorted(sides)
        c=next(v for v in triangles[i] if v not in edge)
        d=next(v for v in triangles[j] if v not in edge)
        if c==d or g.length(g.sub(points[c],points[d]))>=g.length(g.sub(points[a],points[b]))-tolerance: continue
        if tuple(sorted((c,d))) in adjacency: continue
        old=triangles[i]
        if any(old[k]==b and old[(k+1)%3]==a for k in range(3)): a,b=b,a
        t1,t2=(c,a,d),(c,d,b)
        if min(g.dot(g.cross(g.sub(points[t[1]],points[t[0]]),g.sub(points[t[2]],points[t[0]])),n) for t in (t1,t2))<=tolerance*tolerance: continue
        affected=set()
        for index in (i,j):
            for e in tri_edges(triangles[index]):
                adjacency[e].discard(index); affected.add(e)
                if not adjacency[e]: del adjacency[e]
        triangles[i],triangles[j]=t1,t2
        for index in (i,j):
            for e in tri_edges(triangles[index]):
                adjacency[e].add(index); affected.add(e)
        for e in sorted(affected):
            if e not in queued:
                pending.append(e); queued.add(e)
    return triangles

def rebuild(points, faces, seam_edges, width, tolerance):
    """Return explicit triangles/quads with uniform seam stations and small collar.

    Unsupported/nonplanar patches raise rather than changing their shape.
    The caller can retain the native fallback in that case.
    """
    points=list(map(tuple,points)); faces=list(map(tuple,faces))
    spans=g.straight_segments(points,seam_edges,tolerance)
    if not spans: raise ValueError('No seam')
    lookup=g.Segments(spans,width*1.02)
    # A uniform right-angle miter reaches sqrt(2)*width from the seam corner.
    # The straight-span tube alone leaves a stepped grid boundary INSIDE that
    # miter, causing overlapping planar transitions and hooked connections.
    corners=set(p for span in spans for p in span)
    corner_radius=width*1.02*math.sqrt(2.)
    near=[lookup.near(p,width*1.02) or
          any(g.length(g.sub(p,c))<=corner_radius for c in corners) for p in points]
    band=[any(near[v] for v in f) for f in faces]
    normals=[normal(points,f) for f in faces]
    parent=list(range(len(faces)))
    def find(v):
        while parent[v]!=v: parent[v]=parent[parent[v]]; v=parent[v]
        return v
    for edge,sides in g.edge_map(faces).items():
        if len(sides)!=2 or edge in seam_edges: continue
        i,j=sides[0][0],sides[1][0]
        if not (band[i] and band[j]) or g.dot(normals[i],normals[j])<1.-1e-10: continue
        origin=points[faces[i][0]]
        if any(abs(g.dot(g.sub(points[v],origin),normals[i]))>tolerance for v in faces[i]+faces[j]): continue
        parent[find(j)]=find(i)
    groups=defaultdict(list)
    for i,b in enumerate(band):
        if b: groups[find(i)].append(i)
    # A hard corner is shared by two planar patches. Native Melt cannot remove
    # its old collinear grid stations, so remove them from BOTH patch boundaries
    # before beveling. Keep every vertex used by the untouched outside mesh.
    protected={v for i,f in enumerate(faces) if not band[i] for v in f}
    protected.update(v for edge in seam_edges for v in edge)
    boundary_neighbors=defaultdict(set)
    for (a,b),sides in g.edge_map(faces).items():
        if len(sides)==2 and find(sides[0][0])==find(sides[1][0]): continue
        if not any(band[i] for i,j in sides): continue
        boundary_neighbors[a].add(b); boundary_neighbors[b].add(a)
    redundant=set()
    for v,neighbors in boundary_neighbors.items():
        if v in protected or len(neighbors)!=2: continue
        a,b=neighbors
        if g.segment_distance2(points[v],points[a],points[b])<=tolerance*tolerance:
            redundant.add(v)
    # Uniform sampling removes close pairs from the two operands' different
    # grid spacings. Corners remain exact and are shared by both surface sides.
    coord={tuple(round(c/tolerance) for c in p):i for i,p in enumerate(points)}
    def vertex(p):
        key=tuple(round(c/tolerance) for c in p)
        if key not in coord: coord[key]=len(points); points.append(tuple(p))
        return coord[key]
    samples=[]
    for a,b in spans:
        distance=g.length(g.sub(b,a))
        count=max(1,int(math.ceil(distance/max(width,tolerance*10))))
        if count>10000: raise ValueError('Seam sampling limit')
        samples.append([vertex(tuple(a[k]+(b[k]-a[k])*i/count for k in range(3))) for i in range(count+1)])
    def replacement(a,b):
        for span_index,(A,B) in enumerate(spans):
            if not(g.segment_distance2(points[a],A,B)<=tolerance*tolerance and g.segment_distance2(points[b],A,B)<=tolerance*tolerance): continue
            v=g.sub(B,A); vv=g.dot(v,v)
            ta=g.dot(g.sub(points[a],A),v)/vv; tb=g.dot(g.sub(points[b],A),v)/vv
            sequence=samples[span_index]; count=len(sequence)-1
            if ta<tb:
                return [idx for k,idx in enumerate(sequence) if ta-1e-9<=k/count<tb-1e-9]
            return [idx for k,idx in reversed(list(enumerate(sequence))) if tb+1e-9<k/count<=ta+1e-9]
        raise ValueError('Unmatched seam edge')
    result=[f for i,f in enumerate(faces) if not band[i]]
    origins=[i for i,b in enumerate(band) if not b]
    for members in groups.values():
        loops=boundary_loops([faces[i] for i in members])
        rings=[]
        for ring in loops:
            new=[]
            for a,b in zip(ring,ring[1:]+ring[:1]):
                if tuple(sorted((a,b))) in seam_edges: new.extend(replacement(a,b))
                elif a not in redundant: new.append(a)
            if len(new)<3: raise ValueError('Patch collapsed')
            rings.append(new)
        # Every original patch must be planar; curved regions use the fallback.
        n=normals[members[0]]; origin=points[faces[members[0]][0]]
        if any(abs(g.dot(g.sub(points[v],origin),n))>tolerance for i in members for v in faces[i]): raise ValueError('Nonplanar patch')
        tris=triangulate(points,rings,n,tolerance)
        result.extend(tris); origins.extend([-1]*len(tris))
    counts=Counter(tuple(sorted((a,b))) for f in result for a,b in zip(f,f[1:]+f[:1]))
    original=g.edge_map(faces)
    if all(len(s)==2 for s in original.values()) and any(c!=2 for c in counts.values()):
        raise ValueError('Rebuild would open the mesh')
    used=sorted({v for f in result for v in f}); remap={v:i for i,v in enumerate(used)}
    return [points[v] for v in used], [tuple(remap[v] for v in f) for f in result], origins, spans


def remove_collapsed_faces(points, faces, tolerance):
    """Remove only faces whose vertices all lie on one line segment.

    Native bevel can leave these at old subdivided corner stations. They have
    no surface area, but add spurious third/fourth incident faces to edges.
    Non-collinear folded quads are not silently discarded.
    """
    result=[]; collapsed_vertices=set()
    for face in faces:
        a,b=max(((a,b) for a in face for b in face),
                key=lambda ab:g.length(g.sub(points[ab[0]],points[ab[1]])))
        if all(g.segment_distance2(points[v],points[a],points[b])<=tolerance*tolerance for v in face):
            collapsed_vertices.update(face)
            continue
        result.append(tuple(face))
    # A flat triangle can join one long edge to two shorter edges. Removing it
    # alone opens a T-junction. Insert its existing stations into the adjacent
    # long edge, and triangulate that polygon with the same boundary vertices.
    if collapsed_vertices:
        conforming=[]
        for face in result:
            ring=[]
            for a,b in zip(face,face[1:]+face[:1]):
                ring.append(a)
                delta=g.sub(points[b],points[a]);den=g.dot(delta,delta)
                if den<=tolerance*tolerance:continue
                stations=[]
                for v in collapsed_vertices-set(face):
                    t=g.dot(g.sub(points[v],points[a]),delta)/den
                    if 0<t<1 and g.segment_distance2(points[v],points[a],points[b])<=tolerance*tolerance:
                        stations.append((t,v))
                ring.extend(v for t,v in sorted(stations))
            if len(ring)==len(face):conforming.append(face)
            elif len(face)==3:
                triangles=[face]
                for v in ring:
                    if v in face:continue
                    for i,tri in enumerate(triangles):
                        split=False
                        for j,a in enumerate(tri):
                            b,c=tri[(j+1)%3],tri[(j+2)%3]
                            if v not in tri and g.segment_distance2(points[v],points[a],points[b])<=tolerance*tolerance:
                                triangles[i]=(a,v,c);triangles.append((v,b,c));split=True;break
                        if split:break
                conforming.extend(triangles)
            else:conforming.extend(triangulate(points,[ring],normal(points,face),tolerance))
        result=conforming
    return result

def finish_patches(points, faces, groups, tolerance):
    """Expose real, locally refined triangle edges in planar transition n-gons."""
    replacements={}; removed=set()
    for members in groups:
        if len(members)<2: continue
        patch=[tuple(faces[i]) for i in members]
        n=normal(points,patch[0]); origin=points[patch[0][0]]
        if any(abs(g.dot(g.sub(points[v],origin),n))>tolerance for f in patch for v in f): continue
        try: tris=triangulate(points,boundary_loops(patch),n,tolerance)
        except ValueError: continue
        replacements[min(members)]=tris; removed.update(members)
    result=[]
    for i,face in enumerate(faces):
        if i in replacements: result.extend(replacements[i])
        elif i not in removed: result.append(tuple(face))
    return result
