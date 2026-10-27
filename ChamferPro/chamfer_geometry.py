"""Radius fillets on piecewise cubic paths. No Cinema 4D dependency.

Curves outside the trim intervals are retained exactly (de Casteljau).
Each accepted fillet has the requested circle radius; conflicts are not scaled.
"""
import math
import time
from dataclasses import dataclass


class EvaluationStopped(RuntimeError):
    pass


class WorkBudget:
    """Cooperative deadline/cancellation, shared across every input contour."""
    def __init__(self, seconds=2.0, cancelled=None):
        self.deadline = time.monotonic()+seconds
        self.cancelled = cancelled
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls % 64: return
        if self.cancelled and self.cancelled():
            raise EvaluationStopped('Evaluation cancelled; original contours retained')
        if time.monotonic() > self.deadline:
            raise EvaluationStopped('Evaluation time limit; original contours retained')


def add(a, b): return tuple(x+y for x, y in zip(a, b))
def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def mul(a, s): return tuple(x*s for x in a)
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def length(a): return math.sqrt(dot(a, a))
def unit(a):
    n = length(a)
    return mul(a, 1/n) if n > 1e-15 else (0., 0., 0.)
def mix(a, b, t): return add(mul(a, 1-t), mul(b, t))
def angle(a, b): return math.acos(max(-1., min(1., dot(unit(a), unit(b)))))


def corner_angle(incoming, outgoing):
    """Smaller of the two angles between rays pointing away from a corner.

    Path tangents both follow traversal, so reverse the incoming tangent.
    The two side angles sum to 2*pi; this is independent of winding.
    """
    left = angle(mul(incoming, -1), outgoing)
    right = math.tau-left
    return min(left, right)


def line(a, b): return (a, mix(a, b, 1/3), mix(a, b, 2/3), b)


def straight_span(c):
    size=length(sub(c[3],c[0]))
    if size < 1e-12: return False
    u=unit(sub(c[3],c[0])); ts=[dot(sub(p,c[0]),u) for p in c]
    return (all(length(cross(sub(p,c[0]),u)) <= max(1e-9,size*1e-9) for p in c)
            and all(a <= b+1e-10 for a,b in zip(ts,ts[1:])))


def point(c, t):
    s = 1-t
    return add(add(mul(c[0], s*s*s), mul(c[1], 3*s*s*t)),
               add(mul(c[2], 3*s*t*t), mul(c[3], t*t*t)))


def tangent(c, t):
    v = add(add(mul(sub(c[1], c[0]), (1-t)**2),
                mul(sub(c[2], c[1]), 2*(1-t)*t)), mul(sub(c[3], c[2]), t*t))
    if length(v) < 1e-14:
        candidates = ([sub(c[1], c[0]), sub(c[2], c[0]), sub(c[3], c[0])]
                      if t < .5 else [sub(c[3], c[2]), sub(c[3], c[1]), sub(c[3], c[0])])
        v = next((v for v in candidates if length(v) > 1e-14), (0., 0., 0.))
    return unit(v)


def split(c, t):
    a, b, d = mix(c[0], c[1], t), mix(c[1], c[2], t), mix(c[2], c[3], t)
    e, f = mix(a, b, t), mix(b, d, t)
    g = mix(e, f, t)
    return (c[0], a, e, g), (g, f, d, c[3])


def trim(c, lo, hi):
    if hi < 1: c = split(c, hi)[0]
    if lo > 0: c = split(c, lo/hi)[1]
    return c


def circle_arcs(center, start, end, normal, radius):
    u, v = unit(sub(start, center)), unit(sub(end, center))
    sweep = math.atan2(dot(normal, cross(u, v)), dot(u, v))
    if sweep <= 0: sweep += math.tau
    if sweep >= math.pi-1e-7:
        raise ValueError('Reversing corner cannot be filleted safely.')
    count = max(1, math.ceil(sweep/(math.pi/4)))
    step = sweep/count
    axis = cross(normal, u)
    curves = []
    for i in range(count):
        a, b = i*step, (i+1)*step
        va = add(mul(u, math.cos(a)), mul(axis, math.sin(a)))
        vb = add(mul(u, math.cos(b)), mul(axis, math.sin(b)))
        p, q = add(center, mul(va, radius)), add(center, mul(vb, radius))
        k = 4/3*math.tan(step/4)*radius
        curves.append((p, add(p, mul(cross(normal, va), k)),
                       sub(q, mul(cross(normal, vb), k)), q))
    # Preserve exact connection coordinates after numerical solution.
    curves[0] = (start,) + curves[0][1:]
    curves[-1] = curves[-1][:3] + (end,)
    return curves


class Path:
    def __init__(self, curves, closed, check=None):
        self.curves = curves
        self.closed = closed
        self.n = len(curves)
        self.check = check or (lambda: None)

    def locate(self, t):
        if not self.closed and t >= self.n: return self.n-1, 1.
        i = math.floor(t)
        return i % self.n, t-i

    def at(self, t):
        self.check()
        i, u = self.locate(t)
        return point(self.curves[i], u), tangent(self.curves[i], u)

    def section(self, lo, hi):
        result = []
        while lo < hi-1e-10:
            self.check()
            i = math.floor(lo+1e-10)
            end = min(hi, i+1)
            result.append(trim(self.curves[i % self.n], max(0., lo-i), min(1., end-i)))
            lo = end
        return result

    def distance_parameter(self, corner, bound, distance):
        """Seed only: polyline length does not determine the final radius."""
        direction = 1 if bound > corner else -1
        p = self.at(corner)[0]
        t, accumulated = float(corner), 0.
        while direction*(bound-t) > 1e-10:
            nxt = t+direction*min(1/16, abs(bound-t))
            q = self.at(nxt)[0]
            d = length(sub(q, p))
            if accumulated+d >= distance:
                return t+(nxt-t)*(distance-accumulated)/max(d, 1e-15)
            accumulated += d
            t, p = nxt, q
        return bound


@dataclass
class Fillet:
    corner: int
    lo: float
    hi: float
    center: tuple
    arcs: list


def solve_fillet(path, corner, lower, upper, radius, turn):
    c = path.curves[corner % path.n][0]
    ti = tangent(path.curves[(corner-1) % path.n], 1.)
    to = tangent(path.curves[corner % path.n], 0.)
    normal = unit(cross(ti, to))
    if length(normal) < .5 or turn >= math.pi-1e-6: return None
    tolerance = max(1e-8, radius*1e-7)
    distance = radius*math.tan(turn/2)
    left,right = path.curves[(corner-1)%path.n],path.curves[corner%path.n]
    if straight_span(left) and straight_span(right):
        ll,lr = length(sub(left[3],left[0])),length(sub(right[3],right[0]))
        if distance < min(ll,lr)*(1-1e-10):
            # Invert the straight cubic's parameterization (native handles may
            # be zero); geometry itself has an exact line-line solution.
            def parameter(curve,target):
                size=length(sub(curve[3],curve[0])); fraction=max(0.,min(1.,target/size))
                if length(sub(curve[1],mix(curve[0],curve[3],1/3))) < size*1e-10 and length(sub(curve[2],mix(curve[0],curve[3],2/3))) < size*1e-10:
                    return fraction
                if length(sub(curve[1],curve[0])) < size*1e-10 and length(sub(curve[2],curve[3])) < size*1e-10:
                    return .5-math.sin(math.asin(1-2*fraction)/3)
                u=unit(sub(curve[3],curve[0])); low,high=0.,1.
                for _ in range(32):
                    mid=(low+high)*.5
                    if dot(sub(point(curve,mid),curve[0]),u)<target: low=mid
                    else: high=mid
                return (low+high)*.5
            lo=corner-1+parameter(left,ll-distance)
            hi=corner+parameter(right,distance)
            p=path.at(lo)[0]; q=path.at(hi)[0]
            center=add(p,mul(cross(normal,ti),radius))
            try: arcs=circle_arcs(center,p,q,normal,radius)
            except ValueError: return None
            return Fillet(corner,lo,hi,center,arcs)
        if lower == corner-1 and upper == corner+1: return None
    lo = path.distance_parameter(corner, lower, distance)
    hi = path.distance_parameter(corner, upper, distance)

    def offset(t):
        p, v = path.at(t)
        return add(p, mul(cross(normal, v), radius))

    def derivative(t, low, high):
        a, b = max(low, t-1e-5), min(high, t+1e-5)
        return mul(sub(offset(b), offset(a)), 1/max(1e-15, b-a))

    # Stay on the correct side of discontinuous corner derivatives.
    low, high = lower+1e-9, upper-1e-9
    left_end, right_start = corner-1e-9, corner+1e-9
    lo, hi = max(low, min(left_end, lo)), max(right_start, min(high, hi))
    for _ in range(45):
        residual = sub(offset(lo), offset(hi))
        error = length(residual)
        if error <= tolerance: break
        a = derivative(lo, low, left_end)
        b = mul(derivative(hi, right_start, high), -1)
        aa, ab, bb = dot(a, a), dot(a, b), dot(b, b)
        det = aa*bb-ab*ab
        if abs(det) <= 1e-20*max(1., aa*bb): return None
        ar, br = -dot(a, residual), -dot(b, residual)
        dx, dy = (ar*bb-br*ab)/det, (br*aa-ar*ab)/det
        accepted = False
        for power in range(12):
            factor = .5**power
            x = max(low, min(left_end, lo+dx*factor))
            y = max(right_start, min(high, hi+dy*factor))
            if length(sub(offset(x), offset(y))) < error:
                lo, hi, accepted = x, y, True
                break
        if not accepted: return None
    if length(sub(offset(lo), offset(hi))) > tolerance: return None
    center = mix(offset(lo), offset(hi), .5)
    # A circular 3D fillet must lie in one plane. Never flatten a 3D feature.
    for curve in path.section(lo, hi):
        if any(abs(dot(sub(p, c), normal)) > tolerance for p in curve): return None
    p, a = path.at(lo)
    q, b = path.at(hi)
    if abs(length(sub(p, center))-radius) > tolerance: return None
    if abs(length(sub(q, center))-radius) > tolerance: return None
    try: arcs = circle_arcs(center, p, q, normal, radius)
    except ValueError: return None
    if dot(tangent(arcs[0], 0), a) < 1-1e-6: return None
    if dot(tangent(arcs[-1], 1), b) < 1-1e-6: return None
    return Fillet(corner, lo, hi, center, arcs)


def round_path(curves, closed, radius, min_angle, check=None, local_limit=False):
    """Return (cubics, report). Round smaller corner openings at least min_angle."""
    report = {'rounded': 0, 'skipped': 0, 'conflicts': 0, 'rounded_corners': [],
              'limited': 0, 'radii': []}
    if not curves or radius <= 0: return list(curves), report
    path = Path(curves, closed, check)
    indices = range(path.n) if closed else range(1, path.n)
    turns = {}
    for i in indices:
        path.check()
        turns[i] = angle(tangent(curves[(i-1) % path.n], 1), tangent(curves[i], 0))
    # Stop at meaningful changes of direction; only smooth/redundant knots
    # may be consumed. This avoids erasing unrelated details to force a fit.
    barriers = sorted(i for i, t in turns.items() if t > math.radians(.05))
    candidates = []; settings = {}; radii = {}
    for k, i in enumerate(barriers):
        path.check()
        turn = turns[i]
        opening = corner_angle(tangent(curves[(i-1) % path.n], 1),
                               tangent(curves[i], 0))
        if opening+1e-9 < min_angle: continue
        lower = barriers[k-1] if k else (barriers[-1]-path.n if closed else 0)
        upper = barriers[k+1] if k+1 < len(barriers) else (barriers[0]+path.n if closed else path.n)
        # A geometry-sized search bracket avoids enormous user requests making
        # every bisection trial infeasible (or needlessly expensive).
        bound = radius
        if local_limit:
            def control_length(lo,hi):
                return sum(length(sub(c[j+1],c[j])) for k in range(lo,hi)
                           for c in [curves[k%path.n]] for j in range(3))
            bound = min(radius, (1-1e-8)*min(control_length(lower,i),control_length(i,upper)) /
                        max(math.tan(turn/2),1e-12))
        fillet = solve_fillet(path, i, lower, upper, bound, turn)
        settings[i] = (lower,upper,turn)
        used = bound
        if fillet is None and local_limit:
            low,high = 0.,bound
            for _ in range(18):
                mid = (low+high)*.5
                trial = solve_fillet(path,i,lower,upper,mid,turn)
                if trial is None: high = mid
                else: low,fillet = mid,trial
            used = low
        radii[i] = used
        if fillet: candidates.append(fillet)
        else: report['skipped'] += 1
    if local_limit:
        # Scale only an overlapping pair. Subsequent reductions cannot create
        # new overlaps on ordinary planar fillets. Preserve feasible trials.
        for _ in range(4):
            changed = False
            reductions = {}
            for k in range(len(candidates)-1 + int(closed and len(candidates)>1)):
                a,b = candidates[k],candidates[(k+1)%len(candidates)]
                shift = path.n if k+1 == len(candidates) else 0
                if a.hi <= b.lo+shift+1e-8: continue
                low,high = 0.,1.; best = None
                for _ in range(18):
                    factor = (low+high)*.5
                    la,ua,ta = settings[a.corner]; lb,ub,tb = settings[b.corner]
                    fa=solve_fillet(path,a.corner,la,ua,radii[a.corner]*factor,ta)
                    fb=solve_fillet(path,b.corner,lb,ub,radii[b.corner]*factor,tb)
                    if fa and fb and fa.hi <= fb.lo+shift+1e-8:
                        low,best = factor,(fa,fb)
                    else: high = factor
                if best:
                    for f,trial in zip((a,b),best):
                        previous = reductions.get(f.corner)
                        if previous is None or low < previous[0]:
                            reductions[f.corner] = (low,trial)
                    changed = True
            for k,f in enumerate(candidates):
                if f.corner in reductions:
                    factor,trial = reductions[f.corner]
                    radii[f.corner] *= factor
                    candidates[k] = trial
            if not changed: break
    # Reject both sides of a collision, so point order never decides which
    # of two equivalent corners receives a smaller radius or wins the space.
    rejected = set()
    for k in range(len(candidates)-1 + int(closed and len(candidates)>1)):
        a, b = candidates[k], candidates[(k+1) % len(candidates)]
        shift = path.n if k+1 == len(candidates) else 0
        if a.hi > b.lo+shift+1e-8:
            rejected.update((a.corner, b.corner))
    report['conflicts'] = len(rejected)
    fillets = [f for f in candidates if f.corner not in rejected]
    if not fillets: return list(curves), report
    output = []
    if closed:
        start = fillets[0].lo
        cursor = start
        for f in fillets:
            output.extend(path.section(cursor, f.lo))
            output.extend(f.arcs)
            cursor = f.hi
        output.extend(path.section(cursor, start+path.n))
    else:
        cursor = 0.
        for f in fillets:
            output.extend(path.section(cursor, f.lo))
            output.extend(f.arcs)
            cursor = f.hi
        output.extend(path.section(cursor, path.n))
    report['rounded'] = len(fillets)
    report['rounded_corners'] = [tuple(curves[f.corner][0]) for f in fillets]
    report['radii'] = [radii[f.corner] for f in fillets]
    report['limited'] = sum(r < radius*(1-1e-6) for r in report['radii'])
    return output, report


def clean_inner_corners(curves, closed, radius, min_angle, check=None):
    """Collapse local concave runs inside R of their virtual line intersection.

    Only closed planar contours with straight flanking spans are eligible.
    Convex turns, parallel sides and features outside the radius are retained.
    Each original span can participate in at most one cleanup.
    """
    curves = list(curves)
    if not closed or radius <= 0 or len(curves) < 4: return curves, 0
    check = check or (lambda: None)
    origin = curves[0][0]
    area = (0.,0.,0.)
    for c in curves:
        check()
        samples = [point(c,k/8) for k in range(9)]
        for a,b in zip(samples,samples[1:]):
            area = add(area,cross(sub(a,origin),sub(b,origin)))
    normal = unit(area)
    if length(normal) < .5: return curves, 0
    extent=max(length(sub(p,origin)) for c in curves for p in c)
    tolerance = max(1e-8,min(radius,extent)*1e-7)
    if any(abs(dot(sub(p,origin),normal)) > tolerance for c in curves for p in c):
        return curves, 0
    def straight(c):
        v = sub(c[3],c[0]); size = length(v)
        if size < tolerance: return False
        u = unit(v); projections = [dot(sub(p,c[0]),u) for p in c]
        deviation = max(tolerance,min(radius*.02,size*.01))
        return (all(length(cross(sub(p,c[0]),u)) <= deviation for p in c)
                and all(a <= b+tolerance for a,b in zip(projections,projections[1:])))
    def key(c): return tuple(tuple(p) for p in c)
    locked = set(); removed = 0
    while True:
        changed = False; n = len(curves)
        for start in range(n):
            check()
            prev = curves[start]
            if key(prev) in locked or not straight(prev): continue
            u = tangent(prev,1)
            best = None
            for span_count in range(1,n-2):
                check()
                middle = [curves[(start+k)%n] for k in range(1,span_count+1)]
                nxt = curves[(start+span_count+1)%n]
                chain = [prev]+middle+[nxt]
                if any(key(c) in locked for c in chain): break
                # Small directional noise on a flank may be consumed inside R;
                # a meaningful convex turn still ends the inward group.
                turns = [dot(cross(tangent(a,1),tangent(b,0)),normal)
                         for a,b in zip(chain,chain[1:])]
                if any(t > 1e-8 and angle(tangent(a,1),tangent(b,0)) > math.radians(5)
                       for t,a,b in zip(turns,chain,chain[1:])): break
                if sum(t < -1e-8 for t in turns) < 2 or not straight(nxt): continue
                if any(dot(cross(tangent(c,k/8),tangent(c,(k+1)/8)),normal) > 1e-8
                       and angle(tangent(c,k/8),tangent(c,(k+1)/8)) > math.radians(5)
                       for c in middle for k in range(8)): continue
                v = tangent(nxt,0); axis = cross(u,v); denom = dot(axis,axis)
                if denom < 1e-10 or dot(axis,normal) >= -1e-8: continue
                if corner_angle(u,v)+1e-9 < min_angle: continue
                distance = dot(cross(sub(nxt[0],prev[3]),v),axis)/denom
                apex = add(prev[3],mul(u,distance))
                if distance < -tolerance or dot(sub(apex,nxt[0]),v) > tolerance: continue
                if length(cross(sub(apex,nxt[0]),v)) > tolerance: continue
                # Control hull containment also bounds curved bridge geometry.
                if any(length(sub(p,apex)) > radius+tolerance for c in middle for p in c): continue
                a,b = line(prev[0],apex),line(apex,nxt[3])
                # Cleanup is also useful when this corner needs a locally
                # smaller radius; do not require the full request to fit here.
                if solve_fillet(Path([a,b],False,check),1,0,2,
                                min(radius, length(sub(apex,a[0]))*.01,
                                    length(sub(b[3],apex))*.01),angle(u,v)) is None: continue
                best = (a,b,span_count)
            if best:
                a,b,span_count=best
                rotated = curves[start:]+curves[:start]
                curves = [a,b]+rotated[span_count+2:]
                locked.update((key(a),key(b)))
                removed += span_count
                changed = True
            if changed: break
        if not changed: return curves, removed


def simplify_straight_runs(curves, closed, check=None):
    """Linear-time removal of redundant knots, preserving curved spans/reversals."""
    check = check or (lambda: None)
    runs=[]
    def merge(a,b):
        if length(sub(a[3],b[0])) > 1e-9: return None
        u,v=unit(sub(a[3],a[0])),unit(sub(b[3],b[0]))
        if dot(u,v)<1-1e-12 or length(cross(u,v))>1e-9: return None
        return line(a[0],b[3])
    for c in curves:
        check()
        straight=straight_span(c)
        if runs and straight and runs[-1][1]:
            merged=merge(runs[-1][0],c)
            if merged is not None:
                runs[-1]=(merged,True)
                continue
        runs.append((c,straight))
    if closed and len(runs)>1 and runs[0][1] and runs[-1][1]:
        merged=merge(runs[-1][0],runs[0][0])
        if merged is not None: runs=[(merged,True)]+runs[1:-1]
    return [c for c,_ in runs],len(curves)-len(runs)


def round_paths_fixed(paths, radius, min_angle, check=None, local_limit=False):
    """Use the requested radius; retain corners that cannot fit without overlap."""
    radius = max(0., float(radius))
    output = []
    totals = dict(rounded=0, skipped=0, conflicts=0, requested_radius=radius,
                  effective_radius=radius, cleaned=0, limited=0, redundant=0)
    for curves, closed in paths:
        if radius>0:
            curves,removed=simplify_straight_runs(curves,closed,check)
            totals['redundant']+=removed
        original = curves
        curves, cleaned = clean_inner_corners(curves, closed, radius, min_angle, check)
        result, report = round_path(curves, closed, radius, min_angle, check, local_limit)
        # Only commit cleanup when every reconstructed corner was filleted.
        original_points = {tuple(c[0]) for c in original}
        reconstructed = {tuple(c[0]) for c in curves}-original_points
        if cleaned and not reconstructed.issubset(set(report['rounded_corners'])):
            result, report = round_path(original, closed, radius, min_angle, check, local_limit)
            cleaned = 0
        totals['cleaned'] += cleaned
        output.append((result, closed))
        for key in ('rounded', 'skipped', 'conflicts', 'limited'): totals[key] += report[key]
    return output, totals


def round_paths_uniform(paths, radius, min_angle, check=None):
    """Find one feasible radius across every contour, then build all at it.

The requested radius is an upper bound. Search only contours which lower the
current bound, avoiding a full-text rebuild at every bisection step.
"""
    requested = max(0., float(radius))
    effective = requested
    def trial(curves, closed, r):
        result, report = round_path(curves, closed, r, min_angle, check)
        return result, report, report['skipped'] == 0 and report['conflicts'] == 0

    if effective > 0:
        for curves, closed in paths:
            _, _, fits = trial(curves, closed, effective)
            if fits: continue
            low, high = 0., effective
            for _ in range(17):
                mid = (low+high)*.5
                _, _, fits = trial(curves, closed, mid)
                if fits: low = mid
                else: high = mid
            effective = low
            if effective == 0: break
    output = []
    totals = {'rounded': 0, 'skipped': 0, 'conflicts': 0,
              'requested_radius': requested, 'effective_radius': effective}
    for curves, closed in paths:
        result, report, fits = trial(curves, closed, effective)
        # Curved offset feasibility need not be monotone. Never silently emit
        # different radii or a partially rounded contour after the search.
        if not fits:
            totals.update(rounded=0, skipped=report['skipped'],
                          conflicts=report['conflicts'], effective_radius=0.)
            return list(paths), totals
        output.append((result, closed))
        for key in ('rounded', 'skipped', 'conflicts'): totals[key] += report[key]
    return output, totals


def connect_paths(paths, tolerance=1e-6, check=None):
    """Join coincident open ends only at unambiguous degree-two junctions."""
    paths = [(list(c), closed) for c, closed in paths if c]
    check = check or (lambda: None)
    endpoints = {(i, end): curves[0][0] if end == 0 else curves[-1][3]
                 for i, (curves, closed) in enumerate(paths) if not closed for end in (0, 1)}
    buckets, near = {}, {}
    def cell(p): return tuple(math.floor(x/tolerance) for x in p)
    for key, p in endpoints.items(): buckets.setdefault(cell(p), []).append(key)
    for key, p in endpoints.items():
        check()
        x,y,z = cell(p)
        neighbours = []
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for dz in (-1,0,1):
                    for other in buckets.get((x+dx,y+dy,z+dz), ()):
                        if other != key and length(sub(p,endpoints[other])) <= tolerance:
                            neighbours.append(other)
                            if len(neighbours) > 1: break
                    if len(neighbours) > 1: break
                if len(neighbours) > 1: break
            if len(neighbours) > 1: break
        near[key] = neighbours
    links = {key: ns[0] for key, ns in near.items()
             if len(ns) == 1 and len(near[ns[0]]) == 1}
    visited = set()
    result = [p for p in paths if p[1]]
    # Open chains first, then cycles. Each span is copied at most once.
    starts = [key for key in endpoints if key not in links] + list(endpoints)
    for start in starts:
        if start[0] in visited: continue
        current, merged, closed = start, [], False
        while current[0] not in visited:
            check()
            i, end = current
            visited.add(i)
            curves = paths[i][0]
            if end == 1: curves = [tuple(reversed(c)) for c in reversed(curves)]
            else: curves = list(curves)
            if merged:
                delta = sub(merged[-1][3],curves[0][0])
                curves[0] = (merged[-1][3],add(curves[0][1],delta),curves[0][2],curves[0][3])
            merged.extend(curves)
            nxt = links.get((i,1-end))
            if nxt is None: break
            if nxt == start:
                closed = True
                delta = sub(merged[0][0],merged[-1][3])
                last = merged[-1]
                merged[-1] = (last[0],last[1],add(last[2],delta),merged[0][0])
                break
            current = nxt
        result.append((merged,closed))
    return result
