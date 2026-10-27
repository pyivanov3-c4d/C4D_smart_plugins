"""Bounded local mesh refinement and constrained Delaunay edge flips."""
import math
from st_density import current_density
from collections import defaultdict, deque


def orient(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def distance_to_segment(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy),t


def surface_spacing(points):
    """One sampling scale for every fill, derived from the main boundary."""
    return max(max(p[k] for p in points)-min(p[k] for p in points) for k in (0,1))/(24*math.sqrt(current_density()))


def prepare_boundary(points,boundary,holes):
    """Add points on long outer edges near the relief's closest projections."""
    spacing=surface_spacing([points[i] for i in boundary])
    cuts=[[] for _ in boundary]
    edges=[(boundary[i],boundary[(i+1)%len(boundary)]) for i in range(len(boundary))]
    for loop in holes:
        for i in loop:
            nearest=min((distance_to_segment(points[i],points[a],points[b])+(k,) for k,(a,b) in enumerate(edges)))
            cuts[nearest[2]].append(nearest[1])
    refined=[]
    for k,(a,b) in enumerate(edges):
        pa,pb=points[a],points[b]
        length=math.hypot(pb[0]-pa[0],pb[1]-pa[1])
        # Prefer projections; fill only the remaining large gaps uniformly.
        ts=[0.,1.]
        for t in sorted(cuts[k]):
            if min(abs(t-s)*length for s in ts)>=spacing*.45:
                ts.append(t)
        ts.sort()
        filled=[]
        for lo,hi in zip(ts,ts[1:]):
            count=max(1,int(math.ceil((hi-lo)*length/(spacing*1.4))))
            filled.extend(lo+(hi-lo)*j/count for j in range(count))
        refined.append(a)
        for t in filled[1:]:
            refined.append(len(points))
            points.append(tuple(pa[j]+t*(pb[j]-pa[j]) for j in range(3)))
    return refined,spacing


def improve(points,faces,boundary,holes,spacing,eps):
    """Keep all constraints; insert a bounded near-neighbor-spaced interior grid."""
    from st_geometry import inside
    faces=list(faces)
    loops=[boundary]+holes
    constraints={tuple(sorted((loop[i-1],j))) for loop in loops for i,j in enumerate(loop)}
    edges=list(constraints)
    outer=[points[i] for i in boundary]
    hole_xy=[[points[i] for i in loop] for loop in holes]
    xmin,xmax=min(p[0] for p in outer),max(p[0] for p in outer)
    ymin,ymax=min(p[1] for p in outer),max(p[1] for p in outer)
    step=max(spacing,math.sqrt((xmax-xmin)*(ymax-ymin)/(256*current_density())))
    # Spatial bins avoid searching all mesh vertices for each candidate.
    buckets=defaultdict(list)
    def cell(p): return (math.floor(p[0]/step),math.floor(p[1]/step))
    for i in {j for f in faces for j in f}: buckets[cell(points[i])].append(i)
    added=0
    for iy in range(int((ymax-ymin)/step)+1):
        for ix in range(int((xmax-xmin)/step)+1):
            p=(xmin+(ix+.5)*step,ymin+(iy+.5)*step,0.)
            if not inside(p,outer) or any(inside(p,h) for h in hole_xy): continue
            cx,cy=cell(p)
            nearby=[i for dx in (-1,0,1) for dy in (-1,0,1) for i in buckets[(cx+dx,cy+dy)]]
            if any(math.hypot(p[0]-points[i][0],p[1]-points[i][1])<step*.55 for i in nearby): continue
            if any(distance_to_segment(p,points[a],points[b])[0]<step*.25 for a,b in edges): continue
            replacements=[]
            for fi,f in enumerate(faces):
                values=[orient(points[f[k]],points[f[(k+1)%3]],p) for k in range(3)]
                if min(values)<-eps*eps: continue
                edge=next((k for k in range(3) if abs(values[k])<=eps*math.dist(points[f[k]],points[f[(k+1)%3]])),None)
                if edge is None:
                    replacements=[(fi,f,None)]
                else:
                    # A point on a shared diagonal must split both incident
                    # triangles, even when floating-point tests disagree.
                    a,b=f[edge],f[(edge+1)%3]
                    pa,pb=points[a],points[b]
                    _,t=distance_to_segment(p,pa,pb)
                    p=tuple(pa[k]+t*(pb[k]-pa[k]) for k in range(3))
                    if min(math.dist(p,pa),math.dist(p,pb))<=eps:break
                    for fj,other in enumerate(faces):
                        if a in other and b in other:
                            k=next(k for k in range(3) if {other[k],other[(k+1)%3]}=={a,b})
                            replacements.append((fj,other,k))
                break
            if not replacements: continue
            # Interpolate the containing triangle: raised caps must retain
            # their height instead of inserting samples on the base plane.
            f=replacements[0][1]
            a,b,c=(points[i] for i in f)
            total=orient(a,b,c)
            z=(orient(b,c,p)*a[2]+orient(c,a,p)*b[2]+orient(a,b,p)*c[2])/total
            p=(p[0],p[1],z)
            index=len(points)
            points.append(p); buckets[cell(p)].append(index)
            for fi,f,edge in reversed(replacements):
                if edge is None:
                    new=[(f[0],f[1],index),(f[1],f[2],index),(f[2],f[0],index)]
                else:
                    a,b,c=f[edge],f[(edge+1)%3],f[(edge+2)%3]
                    new=[(a,index,c),(index,b,c)]
                faces[fi:fi+1]=new
            added+=1
            if added>=256*current_density(): break
        if added>=256*current_density(): break
    faces=flip_edges(points,faces,constraints,eps)
    boundary_vertices={i for loop in loops for i in loop}
    faces=connect_to_flat_interior(points,faces,constraints,boundary_vertices)
    return flip_edges(points,faces,constraints,eps,boundary_vertices)


def connect_to_flat_interior(points,faces,constraints,boundary_vertices):
    """Replace every interior boundary-to-boundary chord with flat-area links.

    Reuse an interior vertex or split both incident faces with a welded
    interior sample. Relax new samples within their flat surface region.
    Actual boundary edges (the shared bevel rim) are never split or removed.
    """
    faces=list(faces)
    first_new=len(points)
    chords={tuple(sorted((f[i-1],v))) for f in faces for i,v in enumerate(f)
            if f[i-1] in boundary_vertices and v in boundary_vertices
            and tuple(sorted((f[i-1],v))) not in constraints}
    for a,b in sorted(chords):
        incident=[i for i,f in enumerate(faces) if a in f and b in f]
        if not incident:continue
        # Prefer an existing interior point before inserting a new sample.
        # This avoids tiny half-edges when a short chord is removable.
        if len(incident)==2:
            i,j=incident
            c=next(v for v in faces[i] if v not in (a,b))
            d=next(v for v in faces[j] if v not in (a,b))
            if c!=d and not (c in boundary_vertices and d in boundary_vertices):
                if orient(points[c],points[d],points[a])*orient(points[c],points[d],points[b])<0:
                    new=[(c,d,a),(d,c,b)]
                    new=[f if orient(*(points[v] for v in f))>0 else (f[0],f[2],f[1]) for f in new]
                    faces[i],faces[j]=new
                    continue
        index=len(points)
        center=tuple((points[a][k]+points[b][k])*.5 for k in range(3))
        surrounding={v for fi in incident for v in faces[fi]}
        # Place a flat-area sample away from a narrow rim corner whenever
        # the neighboring triangles admit it, keeping every fan positive.
        mean=tuple(sum(points[v][k] for v in surrounding)/len(surrounding) for k in range(3))
        best=min(math.dist(center,points[v]) for v in surrounding)
        for t in (1.,.75,.5,.25):
            candidate=tuple(center[k]*(1-t)+mean[k]*t for k in range(3))
            valid=True
            for fi in incident:
                f=faces[fi]
                edge=next(j for j in range(3) if {f[j],f[(j+1)%3]}=={a,b})
                u,v,w=f[edge],f[(edge+1)%3],f[(edge+2)%3]
                if orient(points[u],candidate,points[w])<=1e-18 or orient(candidate,points[v],points[w])<=1e-18:
                    valid=False;break
            score=min(math.dist(candidate,points[v]) for v in surrounding)
            if valid and score>best:center=candidate;best=score
        points.append(center)
        for fi in reversed(incident):
            f=faces[fi]
            edge=next(j for j in range(3) if {f[j],f[(j+1)%3]}=={a,b})
            u,v,w=f[edge],f[(edge+1)%3],f[(edge+2)%3]
            faces[fi:fi+1]=[(u,index,w),(index,v,w)]
    # Relax only newly inserted flat points; keep all original samples fixed.
    for _ in range(4):
        for index in range(first_new,len(points)):
            incident=[f for f in faces if index in f]
            neighbors={v for f in incident for v in f if v!=index}
            if not neighbors:continue
            old=points[index]
            mean=tuple(sum(points[v][k] for v in neighbors)/len(neighbors) for k in range(3))
            best=min(math.dist(old,points[v]) for v in neighbors)
            for t in (1.,.5,.25):
                candidate=tuple(old[k]*(1-t)+mean[k]*t for k in range(3))
                if any(orient(*(candidate if v==index else points[v] for v in f))<=1e-18 for f in incident):continue
                score=min(math.dist(candidate,points[v]) for v in neighbors)
                if score>best:points[index]=candidate;best=score
    return faces


def flip_edges(points,faces,constraints,eps,boundary_vertices=None):
    """Lawson flips on convex adjacent triangles; constrained edges never move."""
    faces=list(faces)
    adjacency=defaultdict(set)
    def edges(f): return [tuple(sorted((f[i-1],j))) for i,j in enumerate(f)]
    for i,f in enumerate(faces):
        for e in edges(f): adjacency[e].add(i)
    queue=deque(adjacency)
    attempts=0
    limit=max(1000,len(faces)*100)
    while queue and attempts<limit:
        edge=queue.popleft(); attempts+=1
        neighbors=adjacency.get(edge,())
        if edge in constraints or len(neighbors)!=2: continue
        i,j=sorted(neighbors); a,b=edge
        c=next(v for v in faces[i] if v not in edge)
        d=next(v for v in faces[j] if v not in edge)
        if boundary_vertices is not None and c in boundary_vertices and d in boundary_vertices: continue
        if c==d or tuple(sorted((c,d))) in adjacency and adjacency[tuple(sorted((c,d)))]: continue
        if orient(points[c],points[d],points[a])*orient(points[c],points[d],points[b])>=-eps**4: continue
        # Translate to d and scale to avoid large coordinate powers.
        scale=max(math.hypot(points[v][0]-points[d][0],points[v][1]-points[d][1]) for v in (a,b,c))
        if scale<=eps: continue
        (ax,ay),(bx,by),(cx,cy)=[((points[v][0]-points[d][0])/scale,(points[v][1]-points[d][1])/scale) for v in (a,b,c)]
        det=(ax*ax+ay*ay)*(bx*cy-by*cx)-(bx*bx+by*by)*(ax*cy-ay*cx)+(cx*cx+cy*cy)*(ax*by-ay*bx)
        if orient(points[a],points[b],points[c])<0: det=-det
        if det<=1e-12: continue
        new=[(c,d,a),(d,c,b)]
        new=[f if orient(*(points[v] for v in f))>0 else (f[0],f[2],f[1]) for f in new]
        if any(orient(*(points[v] for v in f))<=eps*eps for f in new): continue
        for fi in (i,j):
            for e in edges(faces[fi]): adjacency[e].discard(fi)
        faces[i],faces[j]=new
        for fi in (i,j):
            for e in edges(faces[fi]):
                adjacency[e].add(fi); queue.append(e)
    return faces
