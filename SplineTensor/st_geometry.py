"""SplineTensor geometry kernel. Standard Python only; coordinates are tuples.

Planar constraints are validated before and after Earcut triangulation. Inputs
which cannot be represented without intersections are rejected, never repaired
by silently deleting contours. See README.md for the supported domain.
"""
import math
from collections import Counter
from st_earcut import earcut
from st_spatial import segment_pairs
from st_density import current_density


class GeometryError(ValueError):
    pass


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def unit(a):
    n = math.sqrt(dot(a, a))
    if n < 1e-15:
        raise GeometryError('Degenerate plane or edge.')
    return tuple(x/n for x in a)


def orient(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def area(p):
    return sum(p[i-1][0]*q[1]-q[0]*p[i-1][1] for i, q in enumerate(p))/2


def on_segment(a, b, p, eps):
    length = math.hypot(b[0]-a[0], b[1]-a[1])
    return (abs(orient(a, b, p)) <= eps*length and
            min(a[0], b[0])-eps <= p[0] <= max(a[0], b[0])+eps and
            min(a[1], b[1])-eps <= p[1] <= max(a[1], b[1])+eps)


def intersects(a, b, c, d, eps):
    if (max(a[0], b[0])+eps < min(c[0], d[0]) or
        max(c[0], d[0])+eps < min(a[0], b[0]) or
        max(a[1], b[1])+eps < min(c[1], d[1]) or
        max(c[1], d[1])+eps < min(a[1], b[1])):
        return False
    if any((on_segment(a, b, c, eps), on_segment(a, b, d, eps),
            on_segment(c, d, a, eps), on_segment(c, d, b, eps))):
        return True
    return orient(a, b, c)*orient(a, b, d) < 0 and orient(c, d, a)*orient(c, d, b) < 0


def inside(p, loop):
    result = False
    for i, b in enumerate(loop):
        a = loop[i-1]
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                result = not result
    return result


def validate_loop(p, eps):
    if len(p) < 3 or abs(area(p)) <= eps*eps:
        raise GeometryError('Contour has no usable projected area.')
    n = len(p)
    for i in range(n):
        a, b = p[i], p[(i+1) % n]
        if math.hypot(a[0]-b[0], a[1]-b[1]) <= eps:
            raise GeometryError('Duplicate or collapsed projected edge.')
        # Adjacent edges may meet, but must not double back.
        c = p[(i+2) % n]
        if on_segment(a, b, c, eps) or on_segment(b, c, a, eps):
            raise GeometryError('Contour doubles back on an adjacent edge.')
        for j in range(i+1, n):
            if j == i+1 or (i == 0 and j == n-1):
                continue
            if intersects(a, b, p[j], p[(j+1) % n], eps):
                raise GeometryError('Contour or offset self-intersects. Reduce Spathe Width or edit spline.')


def nested(outer, inner, eps):
    for i, a in enumerate(outer):
        b = outer[i-1]
        for j, c in enumerate(inner):
            if intersects(a, b, c, inner[j-1], eps):
                raise GeometryError('Contours touch or cross. Reduce Spathe Width or move contour inward.')
    if not inside(inner[0], outer):
        raise GeometryError('Second contour and its full band must lie inside the first spline.')


def offset(p, width, eps):
    """CCW polygon outward miter offset, retaining vertex correspondence."""
    out = []
    for i, b in enumerate(p):
        a, c = p[i-1], p[(i+1) % len(p)]
        u = unit((b[0]-a[0], b[1]-a[1]))
        v = unit((c[0]-b[0], c[1]-b[1]))
        n1, n2 = (u[1], -u[0]), (v[1], -v[0])
        denom = 1 + dot(n1, n2)
        if denom < 1e-8:
            raise GeometryError('Offset has a reversing corner.')
        delta = tuple(width*(n1[k]+n2[k])/denom for k in range(2))
        if math.hypot(*delta) > abs(width)*12:
            raise GeometryError('Offset miter exceeds 12 times width; soften the sharp corner.')
        out.append((b[0]+delta[0], b[1]+delta[1]))
    validate_loop(out, eps)
    if area(out) <= eps*eps:
        raise GeometryError('Inner offset collapsed. Reduce Spathe Width.')
    nested(out, p, eps) if width > 0 else nested(p, out, eps)
    return out


def convex_inset(p, distance, eps):
    """Intersection of inward edge half-planes; empty when the inset vanishes."""
    poly = list(p)
    for i,b in enumerate(p):
        a=p[i-1]
        length=math.dist(a,b)
        clipped=[]
        for j,q in enumerate(poly):
            r=poly[j-1]
            dr=orient(a,b,r)/length-distance
            dq=orient(a,b,q)/length-distance
            if (dr>=0) != (dq>=0):
                t=dr/(dr-dq)
                clipped.append(tuple(r[k]+t*(q[k]-r[k]) for k in range(2)))
            if dq>=0:clipped.append(q)
        poly=clipped
        if len(poly)<3:return []
    return poly if abs(area(poly))>eps*eps else []


def triangulate(points, outer_ids, inner_ids, eps, strip=False, quality_spacing=None):
    """Constrained region triangulation with boundary, area and crossing checks."""
    holes = (inner_ids if inner_ids and isinstance(inner_ids[0], list)
             else [inner_ids] if inner_ids else [])
    ids = list(outer_ids)
    starts = []
    for hole in holes:
        starts.append(len(ids))
        ids.extend(hole)
    xy = [points[i][:2] for i in ids]
    if strip:
        n = len(outer_ids)
        raw = []
        for i in range(n):
            j = (i+1) % n
            raw.extend((i, j, n+j, i, n+j, n+i))
    else:
        raw = earcut([v for p in xy for v in p], starts or None, 2)
    faces = []
    for k in range(0, len(raw), 3):
        tri = [ids[j] for j in raw[k:k+3]]
        s = orient(*(points[j] for j in tri))
        if abs(s) <= eps*eps:
            if not strip:
                # Earcut can emit zero-area ears on collinear sampled edges.
                # Restore their boundary samples below, then validate the
                # complete boundary, covered area and all edge intersections.
                continue
            raise GeometryError('Triangulation produced a degenerate face; simplify spline.')
        if s < 0:
            if strip:
                raise GeometryError('Offset band folds over. Reduce Spathe Width.')
            tri.reverse()
        faces.append(tuple(tri))
    # Earcut may remove collinear boundary samples. Reinsert every such sample
    # into adjacent triangles so interpolation points and welded seams survive.
    used = {i for f in faces for i in f}
    for p in ids:
        replacement = []
        inserted = False
        for f in faces:
            if p in f:
                replacement.append(f)
                continue
            for k in range(3):
                a, b, c = f[k], f[(k+1) % 3], f[(k+2) % 3]
                if on_segment(points[a], points[b], points[p], eps):
                    replacement.extend(((a, p, c), (p, b, c)))
                    inserted = True
                    break
            else:
                replacement.append(f)
        if not inserted and p not in used:
            raise GeometryError('Triangulation could not retain a spline sample.')
        faces = replacement
    boundaries = set()
    for loop in [outer_ids] + holes:
        boundaries.update(tuple(sorted((loop[i-1], j))) for i, j in enumerate(loop))
    if quality_spacing is not None and not strip:
        from st_quality import improve
        faces=improve(points,faces,outer_ids,holes,quality_spacing,eps)
    counts = Counter(tuple(sorted((f[i-1], f[i]))) for f in faces for i in range(3))
    if {e for e, n in counts.items() if n == 1} != boundaries or any(n > 2 for n in counts.values()):
        raise GeometryError('Triangulation lost a boundary sample; simplify collinear spline samples.')
    expected = abs(area([points[i] for i in outer_ids]))
    for hole in holes:
        expected -= abs(area([points[i] for i in hole]))
    actual = sum(orient(*(points[j] for j in f))/2 for f in faces)
    if any(orient(*(points[j] for j in f)) <= eps*eps for f in faces):
        raise GeometryError('Spline samples are too close for a valid triangulation.')
    if abs(actual-expected) > max(eps*eps*10, expected*1e-8):
        raise GeometryError('Triangulation area validation failed.')
    edges = list(counts)
    segments=[(points[a],points[b]) for a,b in edges]
    for i,j in segment_pairs(segments,eps):
        a,b=edges[i];c,d=edges[j]
        if len({a,b,c,d})<4:continue
        if intersects(points[a],points[b],points[c],points[d],eps):
            raise GeometryError('Triangulation edge intersection detected.')
    return faces


def clean_contour(c, heights, width, eps):
    """Remove sub-width slivers with bounded deviation and topology validation."""
    if width <= eps:
        return c, heights
    tolerance=max(eps,width*.005)
    original=list(c)
    def distance_to_edge(p,a,b):
        ab=sub(b,a); t=max(0.,min(1.,dot(sub(p,a),ab)/dot(ab,ab)))
        return math.dist(p,tuple(a[k]+t*ab[k] for k in range(2)))
    while len(c)>3:
        for i,p in enumerate(c):
            if math.dist(c[i-1],p)>=tolerance:continue
            candidate=c[:i]+c[i+1:]
            if any(min(distance_to_edge(q,candidate[j-1],r) for j,r in enumerate(candidate))
                   >tolerance for q in original):continue
            try:validate_loop(candidate,eps)
            except GeometryError:continue
            c=candidate;heights.pop(i)
            break
        else:break
    return c, heights


def build(base, contour, width=0.0, subdivisions=3, profile=None, closed=True, _partition=False, _quality=False):
    """Return (3D vertices, triangle indices); inputs in generator local space.

    Subdivisions = interior band lines. Profile x=0 at outer foot, x=1 at
    raised contour. Both endpoints are pinned. Closed off adds an inward band.
    """
    base, contour = list(base), list(contour)
    if not math.isfinite(width) or width < 0 or not 0 <= subdivisions <= 65*current_density()-1:
        raise GeometryError('Width must be nonnegative; Subdivision must be 0..64.')
    if not all(len(p) == 3 and all(math.isfinite(v) for v in p) for p in base+contour):
        raise GeometryError('Non-finite or invalid point coordinates.')
    if len(base) < 3 or len(contour) < 3 or len(base)+len(contour) > 1200*current_density():
        raise GeometryError('Use 3 or more samples per spline and at most 1200 total samples.')
    scale = max(max(p[k] for p in base)-min(p[k] for p in base) for k in range(3))
    eps = max(scale*1e-8, 1e-9)
    for loop in (base, contour):
        if math.sqrt(dot(sub(loop[0], loop[-1]), sub(loop[0], loop[-1]))) <= eps:
            loop.pop()
    origin = base[0]
    normal = (0., 0., 0.)
    for i, p in enumerate(base):
        term = cross(sub(base[i-1], origin), sub(p, origin))
        normal = tuple(normal[k]+term[k] for k in range(3))
    normal = unit(normal)
    major = max(range(3), key=lambda k: abs(normal[k]))
    if normal[major] < 0:
        normal = tuple(-v for v in normal)
    u = unit(sub(base[1], origin))
    v = unit(cross(normal, u))
    def project(p):
        q = sub(p, origin)
        return (dot(q, u), dot(q, v), dot(q, normal))
    b3, c3 = list(map(project, base)), list(map(project, contour))
    if any(abs(p[2]) > eps*10 for p in b3):
        raise GeometryError('First spline must be planar.')
    b, c = [p[:2] for p in b3], [p[:2] for p in c3]
    heights = [p[2] for p in c3]
    if area(b) < 0:
        b.reverse()
    if area(c) < 0:
        c.reverse()
        heights.reverse()
    validate_loop(b, eps)
    # Zero relief contributes no contour edges or offset bands at all.
    if all(abs(h) <= eps for h in heights):
        flat = [(x,y,0.) for x,y in b]
        boundary = list(range(len(flat)))
        if _partition:
            return dict(points=flat,boundary=boundary,footprint=[],faces=[],quads=[],
                        frame=(origin,u,v,normal),eps=eps,skipped=True,crease=[])
        triangles = triangulate(flat,boundary,[],eps)
        world = [tuple(origin[k]+p[0]*u[k]+p[1]*v[k] for k in range(3)) for p in flat]
        return world,triangles
    validate_loop(c, eps)
    c,heights=clean_contour(c,heights,width,eps)
    nested(b, c, eps)
    points, faces, band_quads = [], [], []
    flat_edges=[]
    def remember_strip(outer, inner):
        for i in range(len(outer)):
            j = (i+1) % len(outer)
            band_quads.append((outer[i],outer[j],inner[j],inner[i]))
    def add_strip(outer, inner):
        triangles=triangulate(points,outer,inner,eps,strip=True)
        remember_strip(outer,inner)
        faces.extend(triangles)
    def ring(xy, z):
        start = len(points)
        points.extend((p[0], p[1], h) for p, h in zip(xy, z))
        return list(range(start, len(points)))
    bid = ring(b, [0.]*len(b))
    cid = ring(c, heights)
    from st_quality import surface_spacing
    fill_spacing=surface_spacing(b) if _quality else None
    if closed:
        faces.extend(triangulate(points, cid, [], eps,quality_spacing=fill_spacing))
    elif width > eps:
        previous, previous_xy = cid, c
        steps = subdivisions+1
        convex = all(orient(c[i-1],p,c[(i+1)%len(c)])>=-eps*eps for i,p in enumerate(c))
        collapsed = False
        for j in range(1, steps+1):
            if convex and not convex_inset(c,width*j/steps,eps):
                # Opposing inward bands meet before reaching the requested
                # width. Close the remaining convex region instead of
                # allowing the offset to reverse through its center.
                center=tuple(sum(p[k] for p in previous_xy)/len(previous_xy) for k in range(2))
                distance=min(orient(c[i-1],p,center)/math.dist(c[i-1],p) for i,p in enumerate(c))
                t=max(0.,min(1.,1-distance/width))
                factor=profile(t) if profile else math.sin(t*math.pi/2)
                if not math.isfinite(factor):raise GeometryError('Curve returned a non-finite height.')
                center_id=ring([center],[sum(heights)/len(heights)*max(0.,min(1.,factor))])[0]
                faces.extend((previous[i-1],idx,center_id) for i,idx in enumerate(previous))
                collapsed=True
                break
            xy = offset(c, -width*j/steps, eps)
            nested(previous_xy, xy, eps)
            t = 1-j/steps
            factor = (profile(t) if profile else math.sin(t*math.pi/2)) if j < steps else 0.
            if not math.isfinite(factor):
                raise GeometryError('Curve returned a non-finite height.')
            current = ring(xy, [h*max(0., min(1., factor)) for h in heights])
            add_strip(previous,current)
            previous, previous_xy = current, xy
        if not collapsed:
            faces.extend(triangulate(points, previous, [], eps,quality_spacing=fill_spacing))
    elif all(abs(h) <= eps for h in heights):
        faces.extend(triangulate(points, cid, [], eps))
    else:
        raise GeometryError('Closed off requires positive Spathe Width for nonzero relief height.')
    if width > eps:
        previous, previous_xy = cid, c
        steps = subdivisions+1
        for j in range(1, steps+1):
            xy = offset(c, width*j/steps, eps)
            nested(xy, previous_xy, eps)
            t = 1-j/steps
            factor = (profile(t) if profile else math.sin(t*math.pi/2)) if j < steps else 0.
            if not math.isfinite(factor):
                raise GeometryError('Curve returned a non-finite height.')
            factor = max(0., min(1., factor))
            current = ring(xy, [h*factor for h in heights])
            add_strip(current,previous)
            previous, previous_xy = current, xy
        nested(b, previous_xy, eps)
        footprint, relief = previous, list(faces)
        faces.extend(triangulate(points, bid, previous, eps))
    else:
        if all(abs(h) <= eps for h in heights):
            for i in cid:
                points[i] = (*points[i][:2], 0.)
            foot = cid
        else:
            if not (all(h > eps for h in heights) or all(h < -eps for h in heights)):
                raise GeometryError('At zero width all contour heights must have one sign or all be zero.')
            foot = ring(c, [0.]*len(c))
            for i in range(len(c)):
                j = (i+1) % len(c)
                faces.extend(((foot[i], foot[j], cid[j]), (foot[i], cid[j], cid[i])))
        footprint, relief = foot, list(faces)
        faces.extend(triangulate(points, bid, foot, eps))
    # Every internal edge is welded, and each edge has opposite directed uses.
    counts = Counter(tuple(sorted((f[i-1], f[i]))) for f in faces for i in range(3))
    boundary = {tuple(sorted((bid[i-1], j))) for i, j in enumerate(bid)}
    if {e for e, n in counts.items() if n == 1} != boundary or any(n > 2 for n in counts.values()):
        raise GeometryError('Output is not a manifold open surface.')
    world = [tuple(origin[k]+p[0]*u[k]+p[1]*v[k]+p[2]*normal[k] for k in range(3)) for p in points]
    if _partition:
        return dict(points=points, boundary=bid, footprint=footprint, faces=relief,
                    frame=(origin,u,v,normal), eps=eps, quads=band_quads,
                    crease=[(cid[i-1],j) for i,j in enumerate(cid)]+flat_edges)
    return world, faces


def build_many(base, contours, width=0.0, subdivisions=3, profile=None, closed=True, quad_bands=False, return_edges=False, quality=False):
    """One base with independent, strictly disjoint relief footprints."""
    contours = list(contours)
    if not contours:
        raise GeometryError('Add at least one closed relief spline after the base spline.')
    if len(base)+sum(len(c) for c in contours) > 1200*current_density():
        raise GeometryError('Use at most 1200 total samples across all children.')
    parts = []
    for index, contour in enumerate(contours, 2):
        try:
            parts.append(build(base,contour,width,subdivisions,profile,closed,_partition=True,_quality=quality))
        except GeometryError as exc:
            raise GeometryError('Child %d: %s' % (index,exc)) from exc
    first = parts[0]
    points = [first['points'][i] for i in first['boundary']]
    boundary = list(range(len(points)))
    faces, holes, loops, quads = [], [], [], []
    creases=[]
    eps = first['eps']
    for index, part in enumerate(parts, 2):
        if part.get('skipped'):
            continue
        loop = [part['points'][i][:2] for i in part['footprint']]
        for other in loops:
            overlap = inside(loop[0],other) or inside(other[0],loop)
            if not overlap:
                overlap = any(intersects(a,loop[i-1],b,other[j-1],eps)
                              for i,a in enumerate(loop) for j,b in enumerate(other))
            if overlap:
                raise GeometryError('Child %d: relief footprints touch, overlap or nest. Move children apart or reduce Spathe Width.' % index)
        loops.append(loop)
        mapping = {}
        base_ids = set(part['boundary'])
        for i,p in enumerate(part['points']):
            if i not in base_ids:
                mapping[i] = len(points)
                points.append(p)
        faces.extend(tuple(mapping[i] for i in f) for f in part['faces'])
        quads.extend(tuple(mapping[i] for i in q) for q in part['quads'])
        creases.extend(tuple(mapping[i] for i in edge) for edge in part['crease'])
        holes.append([mapping[i] for i in part['footprint']])
    spacing=None
    if quality and holes:
        from st_quality import prepare_boundary
        boundary,spacing=prepare_boundary(points,boundary,holes)
    faces.extend(triangulate(points,boundary,holes,eps,quality_spacing=spacing))
    counts = Counter(tuple(sorted((f[i-1],f[i]))) for f in faces for i in range(3))
    edge_boundary = {tuple(sorted((boundary[i-1],j))) for i,j in enumerate(boundary)}
    if {e for e,n in counts.items() if n == 1} != edge_boundary or any(n > 2 for n in counts.values()):
        raise GeometryError('Combined surface failed manifold validation.')
    origin,u,v,normal = first['frame']
    world = [tuple(origin[k]+p[0]*u[k]+p[1]*v[k]+p[2]*normal[k] for k in range(3)) for p in points]
    if quad_bands:
        replaced = {frozenset(t) for a,b,c,d in quads for t in ((a,b,c),(a,c,d))}
        faces = [f for f in faces if frozenset(f) not in replaced] + quads
    return (world,faces,creases) if return_edges else (world,faces)
