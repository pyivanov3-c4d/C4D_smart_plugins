"""Collision-resolving bevel layers built from the union of swept edge regions."""
import math
from collections import defaultdict, Counter
from st_geometry import (GeometryError, area, inside, sub, dot, cross, unit,
                         validate_loop, triangulate, nested, clean_contour)
from st_union import union_loops


def connect_band_vertices(points, triangles, constraints, eps):
    """Connect stranded layer vertices across the band, never across its border.

    Projected Delaunay can create a flat ear between three vertices on the
    same offset layer. Flip its unconstrained diagonal to the next layer
    instead, provided the combined projected region is strictly convex.
    """
    from st_geometry import orient
    faces=list(triangles)
    def flat(face):
        heights=[points[i][2] for i in face]
        return max(heights)-min(heights)<=eps
    for _ in range(len(faces)):
        adjacency=defaultdict(list)
        for i,face in enumerate(faces):
            for j,a in enumerate(face):adjacency[tuple(sorted((face[j-1],a)))].append(i)
        changed=False
        for (a,b),neighbors in adjacency.items():
            if (a,b) in constraints or len(neighbors)!=2:continue
            i,j=neighbors
            before=int(flat(faces[i]))+int(flat(faces[j]))
            if not before:continue
            c=next(k for k in faces[i] if k not in (a,b))
            d=next(k for k in faces[j] if k not in (a,b))
            if c==d or tuple(sorted((c,d))) in adjacency:continue
            if orient(points[c],points[d],points[a])*orient(points[c],points[d],points[b])>=-eps**4:continue
            new=[(c,d,a),(d,c,b)]
            new=[f if orient(*(points[k] for k in f))>0 else (f[0],f[2],f[1]) for f in new]
            if any(orient(*(points[k] for k in f))<=eps*eps for f in new):continue
            if sum(int(flat(f)) for f in new)>=before:continue
            faces[i],faces[j]=new
            changed=True
            break
        if not changed:break
    return faces


def quad_pairs(points,triangles,eps):
    """Keep two vertices per layer and preserve the existing triangulation."""
    from st_geometry import orient
    adjacency=defaultdict(list)
    for index,tri in enumerate(triangles):
        for i,a in enumerate(tri):adjacency[tuple(sorted((tri[i-1],a)))].append(index)
    consumed=set();quads=[]
    for edge,neighbors in adjacency.items():
        if len(neighbors)!=2 or any(i in consumed for i in neighbors):continue
        if abs(points[edge[0]][2]-points[edge[1]][2])<=eps:continue
        pair=[triangles[i] for i in neighbors]
        ids=set(pair[0])|set(pair[1])
        if len(ids)!=4:continue
        levels=sorted(points[i][2] for i in ids)
        if abs(levels[0]-levels[1])>eps or abs(levels[2]-levels[3])>eps:continue
        boundary={}
        for tri in pair:
            for i,a in enumerate(tri):
                b=tri[(i+1)%3]
                if tuple(sorted((a,b)))!=edge:boundary[a]=b
        ring=[edge[0]]
        for _ in range(3):ring.append(boundary[ring[-1]])
        if len(set(ring))!=4 or ring[2]!=edge[1]:continue
        if any(orient(points[ring[i-1]],points[a],points[ring[(i+1)%4]])<=eps*eps for i,a in enumerate(ring)):continue
        # C4D chooses a quad's render diagonal. Only merge coplanar pairs;
        # a twisted collision quad otherwise changes the intended surface.
        a,b,c,d=(points[idx] for idx in ring)
        normal=cross(sub(b,a),sub(c,a))
        length=math.sqrt(dot(normal,normal))
        if length<=eps*eps or abs(dot(normal,sub(d,a)))/length>eps*4:continue
        consumed.update(neighbors);quads.append(tuple(ring))
    return [tri for i,tri in enumerate(triangles) if i not in consumed]+quads


def membership(loops):
    records=[(p,1 if area(p)>0 else -1,
              min(v[0] for v in p),max(v[0] for v in p),
              min(v[1] for v in p),max(v[1] for v in p)) for p in loops]
    def contains(q):
        return sum(sign for p,sign,x0,x1,y0,y1 in records
                   if x0<=q[0]<=x1 and y0<=q[1]<=y1 and inside(q,p))>0
    return contains


def difference(outer,inner,eps):
    if not inner:return outer
    a,b=membership(outer),membership(inner)
    return union_loops(outer+inner,eps,_predicate=lambda p:a(p) and not b(p),_regions=True)


def offset_regions(original,distance,eps):
    """Sweep each original edge; overlapping sweeps are welded by arrangement."""
    patches=[]
    for loop in original:
        shifted=[]
        for i,b in enumerate(loop):
            a,c=loop[i-1],loop[(i+1)%len(loop)]
            u=unit(sub(b,a));v=unit(sub(c,b))
            n1,n2=(u[1],-u[0]),(v[1],-v[0])
            denom=1+dot(n1,n2)
            if denom<1e-8:raise GeometryError('Offset has a reversing corner.')
            delta=tuple(distance*(n1[k]+n2[k])/denom for k in range(2))
            if math.hypot(*delta)>abs(distance)*12:
                raise GeometryError('Offset miter exceeds 12 times width; soften the sharp corner.')
            shifted.append(tuple(b[k]+delta[k] for k in range(2)))
        for i,a in enumerate(loop):
            j=(i+1)%len(loop)
            for triangle in ((a,loop[j],shifted[j]),(a,shifted[j],shifted[i])):
                s=area(triangle)
                if abs(s)>eps*eps:
                    patches.append(list(triangle) if s>0 else list(reversed(triangle)))
    a,b=membership(original),membership(patches)
    predicate=(lambda p:a(p) or b(p)) if distance>0 else (lambda p:a(p) and not b(p))
    return union_loops(original+patches,eps,_predicate=predicate,_regions=True)


def build_welded(base,contours,width,subdivisions,profile=None,closed=True,
                 quad_bands=False,return_edges=False,quality=False,preserve_regions=False):
    origin=base[0]
    n=unit(tuple(sum(cross(sub(base[i-1],origin),sub(p,origin))[k] for i,p in enumerate(base)) for k in range(3)))
    if n[max(range(3),key=lambda k:abs(n[k]))]<0:n=tuple(-v for v in n)
    u=unit(sub(base[1],origin));v=unit(cross(n,u))
    project=lambda p:(dot(sub(p,origin),u),dot(sub(p,origin),v),dot(sub(p,origin),n))
    b3=[project(p) for p in base];b=[p[:2] for p in b3]
    span=max(max(p[k] for p in b)-min(p[k] for p in b) for k in (0,1));eps=max(span*1e-8,1e-9)
    if math.dist(b[0],b[-1])<=eps:b.pop()
    if any(abs(p[2])>eps*10 for p in b3):raise GeometryError('First spline must be planar.')
    if area(b)<0:b.reverse()
    validate_loop(b,eps)
    loops=[]; heights=[]
    for contour in contours:
        p=[project(q) for q in contour];heights.extend(q[2] for q in p)
        loop=[q[:2] for q in p]
        if math.dist(loop[0],loop[-1])<=eps:loop.pop()
        if area(loop)<0 and not preserve_regions:loop.reverse()
        validate_loop(loop,eps)
        loop,_=clean_contour(loop,[0.]*len(loop),width,eps)
        nested(b,loop,eps);loops.append(loop)
    height=sum(heights)/len(heights)
    if max(heights)-min(heights)>eps*10:
        raise GeometryError('Collision welding requires a common projected relief height.')
    steps=subdivisions+1
    if width<=eps and not closed:raise GeometryError('Closed off requires positive Spathe Width for nonzero relief height.')
    outer=[loops]+[offset_regions(loops,width*j/steps,eps) for j in range(1,steps+1)]
    for loop in outer[-1]:
        if area(loop)>0:nested(b,loop,eps)
    inner=[loops]
    if not closed:
        for j in range(1,steps+1):inner.append(offset_regions(loops,-width*j/steps,eps))
    points=[];faces=[];crease=[];bins=defaultdict(list)
    def vertex(p,z):
        q=(p[0],p[1],z);cell=tuple(math.floor(x/eps) for x in q)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for dz in (-1,0,1):
                    for idx in bins[(cell[0]+dx,cell[1]+dy,cell[2]+dz)]:
                        if math.dist(points[idx],q)<=eps:return idx
        idx=len(points);points.append(q);bins[cell].append(idx);return idx
    def factor(j):
        if j==0:return height
        if j==steps:return 0.
        t=1-j/steps;f=profile(t) if profile else math.sin(t*math.pi/2)
        if not math.isfinite(f):raise GeometryError('Curve returned a non-finite height.')
        return height*max(0.,min(1.,f))
    def fill(regions,borders,quality_fill=False,band=False):
        # Border coordinates retain the exact layer height; arrangements may
        # add collinear points, whose heights are interpolated on their edge.
        lookup=[]
        for rings,z in borders:
            for ring in rings:
                for i,p in enumerate(ring):lookup.append((ring[i-1],p,z))
        lookup=[(a,b,z,min(a[0],b[0])-eps*20,max(a[0],b[0])+eps*20,
                 min(a[1],b[1])-eps*20,max(a[1],b[1])+eps*20) for a,b,z in lookup]
        height_cache={}
        def z_at(p):
            key=tuple(p)
            if key in height_cache:return height_cache[key]
            best=(float('inf'),0.)
            for a,b,z,x0,x1,y0,y1 in lookup:
                if not (x0<=p[0]<=x1 and y0<=p[1]<=y1):continue
                ab=sub(b,a);den=dot(ab,ab)
                if den<=eps*eps:continue
                t=max(0.,min(1.,dot(sub(p,a),ab)/den))
                d=math.dist(p,tuple(a[k]+t*ab[k] for k in range(2)))
                if d<best[0]:best=(d,z)
            if best[0]>eps*20:raise GeometryError('Welded layer lost its boundary height.')
            height_cache[key]=best[1]
            return best[1]
        positives=[r for r in regions if area(r)>0]
        negatives=[r for r in regions if area(r)<0]
        for ring in positives:
            holes=[h for h in negatives if inside(h[0],ring) and
                   not any(other is not ring and abs(area(other))<abs(area(ring)) and inside(h[0],other) for other in positives)]
            ids=[vertex(p,z_at(p)) for p in ring]
            hole_ids=[[vertex(p,z_at(p)) for p in h] for h in holes]
            from st_quality import surface_spacing
            spacing=surface_spacing(b) if quality_fill and quality else None
            triangles=triangulate(points,ids,hole_ids,eps,quality_spacing=spacing)
            if band and quad_bands:
                from st_quality import flip_edges
                constraints={tuple(sorted((ring[i-1],idx))) for ring in [ids]+hole_ids for i,idx in enumerate(ring)}
                triangles=flip_edges(points,triangles,constraints,eps)
                triangles=connect_band_vertices(points,triangles,constraints,eps)
            faces.extend(quad_pairs(points,triangles,eps) if band and quad_bands else triangles)
    if closed:fill(loops,[(loops,height)],True)
    if width<=eps:
        for ring in loops:
            top=[vertex(p,height) for p in ring]
            bottom=[vertex(p,0.) for p in ring]
            for i,a in enumerate(top):
                j=(i+1)%len(ring)
                faces.append((bottom[i],bottom[j],top[j],a))
    for j in range(1,steps+1):
        fill(difference(outer[j],outer[j-1],eps),[(outer[j-1],factor(j-1)),(outer[j],factor(j))],band=True)
    if not closed:
        for j in range(1,steps+1):
            fill(difference(inner[j-1],inner[j],eps),[(inner[j-1],factor(j-1)),(inner[j],factor(j))],band=True)
        fill(inner[-1],[(inner[-1],0.)],True)
    fill(difference([b],outer[-1],eps),[([b],0.),(outer[-1],0.)],True)
    for ring in loops:
        ids=[vertex(p,height) for p in ring];crease.extend((ids[i-1],idx) for i,idx in enumerate(ids))
    counts=Counter(tuple(sorted((f[i-1],idx))) for f in faces for i,idx in enumerate(f))
    if any(n>2 for n in counts.values()):raise GeometryError('Welded bevel has a non-manifold edge.')
    from st_geometry import on_segment
    for (a,c),count in counts.items():
        if count==1 and not any(on_segment(b[i-1],p,points[a],eps*4) and on_segment(b[i-1],p,points[c],eps*4) for i,p in enumerate(b)):
            raise GeometryError('Welded bevel has an open internal seam.')
    world=[tuple(origin[k]+p[0]*u[k]+p[1]*v[k]+p[2]*n[k] for k in range(3)) for p in points]
    return (world,faces,crease) if return_edges else (world,faces)
