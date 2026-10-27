"""Trim a relief sheet to the base's projected boundary, with welded cut seams."""
import math
from collections import defaultdict, Counter
from st_geometry import (build_many as build_regular, GeometryError, sub, dot, cross, unit,
                         area, orient, validate_loop, triangulate)


def build_many(base,contours,width=0.,subdivisions=3,profile=None,**options):
    # Signed loops from nested masking carry clockwise hole boundaries.
    origin=base[0]
    n=unit(tuple(sum(cross(sub(base[i-1],origin),sub(p,origin))[k] for i,p in enumerate(base)) for k in range(3)))
    if n[max(range(3),key=lambda k:abs(n[k]))]<0:n=tuple(-v for v in n)
    u=unit(sub(base[1],origin));v=unit(cross(n,u))
    signs=[area([(dot(sub(p,origin),u),dot(sub(p,origin),v)) for p in loop]) for loop in contours]
    if any(a<0 for a in signs) and any(a>0 for a in signs):
        from st_weld import build_welded
        return build_welded(base,contours,width,subdivisions,profile,preserve_regions=True,**options)
    try:
        return build_regular(base,contours,width,subdivisions,profile,**options)
    except GeometryError as exc:
        collision=any(message in str(exc) for message in
                      ('Offset band folds over.', 'offset self-intersects',
                       'Inner offset collapsed.', 'relief footprints touch, overlap or nest.',
                       'Contours touch or cross.', 'must lie inside'))
        if not collision or width<=0:raise
        from st_weld import build_welded
        return build_welded(base,contours,width,subdivisions,profile,**options)


def build_clipped(base,contours,width=0.,subdivisions=3,profile=None,
                  closed=True,quad_bands=False,return_edges=False,quality=False,density=1):
    from st_density import density_scope
    with density_scope(density):
        return _build_clipped(base,contours,width,(subdivisions+1)*density-1,profile,
                              closed,quad_bands,return_edges,quality)


def _build_clipped(base, contours, width=0., subdivisions=3, profile=None,
                  closed=True, quad_bands=False, return_edges=False, quality=False):
    contours = list(contours)
    options = dict(closed=closed, quad_bands=quad_bands, return_edges=True, quality=quality)
    try:
        result = build_many(base, contours, width, subdivisions, profile, **options)
        return result if return_edges else result[:2]
    except GeometryError as exc:
        # Retain the existing path and its diagnostics for all other failures.
        if not any(s in str(exc) for s in ('Contours touch or cross.', 'must lie inside')):
            raise
    origin = base[0]
    normal = tuple(sum(cross(sub(base[i-1], origin), sub(p, origin))[k]
                       for i, p in enumerate(base)) for k in range(3))
    normal = unit(normal)
    if normal[max(range(3), key=lambda k: abs(normal[k]))] < 0:
        normal = tuple(-x for x in normal)
    u = unit(sub(base[1], origin)); v = unit(cross(normal, u))
    def project(p):
        q = sub(p, origin)
        return dot(q, u), dot(q, v), dot(q, normal)
    def lift(p):
        return tuple(origin[k]+u[k]*p[0]+v[k]*p[1]+normal[k]*p[2] for k in range(3))
    boundary = [project(p) for p in base]
    span = max(max(p[k] for p in boundary)-min(p[k] for p in boundary) for k in (0, 1))
    eps = max(span*1e-8, 1e-9)
    if math.dist(boundary[0], boundary[-1]) <= eps:
        boundary.pop()
    validate_loop(boundary, eps)
    if area(boundary) < 0: boundary.reverse()
    all_points = boundary+[project(p) for loop in contours for p in loop]
    margin = max(span*.1, width*13, eps*100)
    x0, y0 = (min(p[k] for p in all_points)-margin for k in (0, 1))
    x1, y1 = (max(p[k] for p in all_points)+margin for k in (0, 1))
    extended = [lift((x,y,0.)) for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]
    vertices, faces, creases = build_many(extended, contours, width, subdivisions, profile, **options)
    vertices = [project(p) for p in vertices]
    convex = all(orient(boundary[i-1], p, boundary[(i+1)%len(boundary)]) >= -eps*eps
                 for i,p in enumerate(boundary))
    if convex:
        cells = [boundary]
    else:
        cells = [[boundary[i] for i in tri] for tri in
                 triangulate(boundary, list(range(len(boundary))), [], eps)]
    points, polygons, marked = [], [], set()
    bins = defaultdict(list)
    def vertex(p):
        cell = tuple(math.floor(x/eps) for x in p)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for dz in (-1,0,1):
                    for i in bins[(cell[0]+dx,cell[1]+dy,cell[2]+dz)]:
                        if math.dist(points[i],p) <= eps: return i
        i = len(points); points.append(p); bins[cell].append(i)
        return i
    def along(p,a,b):
        ab=sub(b,a); length2=dot(ab,ab)
        if length2 <= eps*eps: return None
        t=dot(sub(p,a),ab)/length2
        if -eps/math.sqrt(length2) <= t <= 1+eps/math.sqrt(length2):
            if math.dist(p,tuple(a[k]+t*ab[k] for k in range(3))) <= eps*2:
                return t
        return None
    crease_set = {tuple(sorted(e)) for e in creases}
    for face in faces:
        source = [vertices[i] for i in face]
        source_marks = [(vertices[a],vertices[b]) for a,b in zip(face,face[1:]+face[:1])
                        if tuple(sorted((a,b))) in crease_set]
        # Fully retained quads stay quads; cut polygons follow the same planar
        # interpolation as the original mesh's two rendered triangles.
        pieces = [source]
        if len(face)==4 and not (convex and all(orient(cell[i-1],b,p)>=-eps*eps
                      for cell in cells for i,b in enumerate(cell) for p in source)):
            pieces = [[source[i] for i in tri] for tri in ((0,1,2),(0,2,3))]
        for cell in cells:
            for piece in pieces:
                poly = piece
                for i,b in enumerate(cell):
                    a=cell[i-1]; clipped=[]
                    for j,q in enumerate(poly):
                        p=poly[j-1]
                        dp,dq=orient(a,b,p),orient(a,b,q)
                        pin,qin=dp>=0.,dq>=0.
                        if pin != qin:
                            t=dp/(dp-dq)
                            clipped.append(tuple(p[k]+t*(q[k]-p[k]) for k in range(3)))
                        if qin: clipped.append(q)
                    poly=clipped
                    if len(poly)<3: break
                if len(poly)<3: continue
                ids=[]
                for p in poly:
                    idx=vertex(p)
                    if not ids or idx!=ids[-1]: ids.append(idx)
                if len(ids)>1 and ids[0]==ids[-1]: ids.pop()
                if len(set(ids))<3: continue
                normal_sum=tuple(sum(cross(sub(points[ids[j-1]],points[ids[0]]),
                                  sub(points[idx],points[ids[0]]))[k]
                                  for j,idx in enumerate(ids)) for k in range(3))
                if math.sqrt(dot(normal_sum,normal_sum))<=eps*eps: continue
                polygons.append(ids)
                for a,b in zip(ids,ids[1:]+ids[:1]):
                    if any(along(points[a],p,q) is not None and along(points[b],p,q) is not None
                           for p,q in source_marks): marked.add(tuple(sorted((a,b))))
    # Triangulation cells and source quads can introduce collinear cut points.
    # Split all shared edges at those points to avoid T junctions.
    result=[]; result_marks=set()
    for face in polygons:
        ring=[]
        for a,b in zip(face,face[1:]+face[:1]):
            candidates=[]
            for i,p in enumerate(points):
                if i in (a,b): continue
                if any(p[k]<min(points[a][k],points[b][k])-eps or
                       p[k]>max(points[a][k],points[b][k])+eps for k in range(3)): continue
                t=along(p,points[a],points[b])
                if t is not None and 0<t<1: candidates.append((t,i))
            edge=[a]+[i for _,i in sorted(candidates)]+[b]
            ring.extend(edge[:-1])
            if tuple(sorted((a,b))) in marked:
                result_marks.update(tuple(sorted(e)) for e in zip(edge,edge[1:]))
        if len(ring)<=4 and len(ring)==len(face):
            result.append(tuple(ring))
        else:
            # Interior centroid fan preserves every collinear seam vertex.
            center=vertex(tuple(sum(points[i][k] for i in ring)/len(ring) for k in range(3)))
            result.extend((a,b,center) for a,b in zip(ring,ring[1:]+ring[:1]))
    used=sorted({i for f in result for i in f})
    mapping={old:new for new,old in enumerate(used)}
    counts=Counter(tuple(sorted((f[i-1],j))) for f in result for i,j in enumerate(f))
    if any(n>2 for n in counts.values()):
        raise GeometryError('Clipped surface has an ambiguous non-manifold seam.')
    world=[lift(points[i]) for i in used]
    if world and all(abs(points[i][2])<=eps for i in used):
        flat=[(p[0],p[1],0.) for p in boundary]
        output=([lift(p) for p in flat],triangulate(flat,list(range(len(flat))),[],eps),[])
        return output if return_edges else output[:2]
    result=[tuple(mapping[i] for i in f) for f in result]
    edges=[tuple(mapping[i] for i in e) for e in result_marks if e in counts]
    output=(world,result,edges)
    return output if return_edges else output[:2]
