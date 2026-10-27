"""Independent spline mesh generator for Cinema 4D 2026.

Local-use plugin ID. Obtain a registered Maxon ID before redistribution.
"""
import math
import os
import sys
import traceback
from bisect import bisect_right

import c4d
from c4d import plugins, bitmaps, utils

ROOT = os.path.dirname(__file__)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from mesher_geometry import circle, rectangle, sides

PLUGIN_ID = 1069988
PROFILE, RADIUS, ROTATIONS, STEP = 1000, 1001, 1002, 1003
CIRCLE_SEGMENTS, WIDTH, HEIGHT, FILLET, FILLET_SEGMENTS = range(1004, 1009)
DIAMETER, CAPS, STATUS = 1009, 1010, 1011
WIDTH_CURVE = 1012
GAPS_GROUP, GAPS, PIECE_LENGTH, SPACE_LENGTH = 1013, 1014, 1015, 1016
PIECE_TILT_X, PIECE_TILT_Y = 1017, 1018
RESET_ALL = 1019
GAP_MODE, PIECE_COUNT = 1020, 1021
CIRCLE, RECTANGLE, ROPE, CHAIN = range(4)
MAX_POINTS = 1000000


def width_factor(curve, t):
    if curve is None or curve.GetKnotCount() == 0:
        return 1.0
    # Keep a tiny positive cross-section to avoid collapsed polygons.
    return max(0.0001, float(curve.GetPoint(max(0.0, min(1.0, t))).y))


class DistancePath:
    """Sample an evaluated polyline by cumulative distance, not point index."""
    def __init__(self, segments):
        self.segments = []
        for source, closed in segments:
            points = []
            for point in source:
                if not points or (point-points[-1]).Dot(point-points[-1]) > 1e-20:
                    points.append(point)
            if closed and len(points) > 1:
                if (points[-1]-points[0]).Dot(points[-1]-points[0]) > 1e-20:
                    points.append(points[0])
            distances = [0.0]
            for a, b in zip(points, points[1:]):
                delta = b-a
                distances.append(distances[-1] + math.sqrt(delta.Dot(delta)))
            self.segments.append((points, distances))

    def GetSegmentCount(self):
        return len(self.segments)

    def GetSegmentLength(self, segment):
        return self.segments[segment][1][-1]

    def GetPosition(self, t, segment=0, smooth=True, realoffset=True):
        points, distances = self.segments[segment]
        if len(points) < 2 or distances[-1] <= 1e-12:
            raise ValueError('Spline segment has no length.')
        distance = max(0.0, min(1.0, t))*distances[-1]
        i = min(len(points)-2, max(0, bisect_right(distances, distance)-1))
        weight = (distance-distances[i])/(distances[i+1]-distances[i])
        return points[i]*(1-weight) + points[i+1]*weight


def primitive_closed(source):
    if source is None or source.CheckType(c4d.Osplinearc):
        return False
    names = ('Osplineprimitive', 'Osplineprofile', 'Osplineflower',
             'Osplineformula', 'Osplinetext', 'Osplinenside', 'Ospline4side',
             'Osplinecircle', 'Osplinecissoid', 'Osplinecycloid', 'Osplinehelix',
             'Osplinerectangle', 'Osplinestar', 'Osplinecogwheel', 'Osplinecontour')
    return any(source.CheckType(getattr(c4d, name)) for name in names
               if hasattr(c4d, name))


def distance_path(helper, spline, source=None):
    line = helper.GetLineObject()
    if line is None:
        raise ValueError('Could not evaluate spline interpolation.')
    points = line.GetAllPoints()
    tag = line.GetTag(c4d.Tsegment)
    entries = tag.GetAllHighlevelData() if tag else []
    if not entries:
        entries = [{'cnt':len(points), 'closed':spline.IsClosed()}]
    segments, start = [], 0
    closed_flags = []
    for entry in entries:
        end = start+entry['cnt']
        closed = bool(entry['closed'] or spline.IsClosed() or primitive_closed(source))
        # Editable input owns its closure flags; conversion must not lose them.
        if source is not None and source.CheckType(c4d.Ospline):
            index = len(segments)
            closed = (bool(source.GetSegment(index)['closed'] or source.IsClosed())
                      if index < source.GetSegmentCount() else source.IsClosed())
        segments.append((points[start:end], closed))
        closed_flags.append(closed)
        start = end
    return DistancePath(segments), closed_flags


def path_frame(helper, t, segment):
    # Derive the tangent from positions, not an assumed SplineHelp matrix axis.
    p = helper.GetPosition(t, segment, True, True)
    a = helper.GetPosition(max(0.0, t-1e-5), segment, True, True)
    b = helper.GetPosition(min(1.0, t+1e-5), segment, True, True)
    z = unit(b-a)
    ref = c4d.Vector(0, 1, 0) if abs(z.y) < 0.9 else c4d.Vector(1, 0, 0)
    x = unit(ref.Cross(z))
    return c4d.Matrix(p, x, z.Cross(x), z)


def unit(v):
    length = math.sqrt(v.Dot(v))
    if length < 1e-12:
        raise ValueError('Spline contains an undefined tangent or coincident points.')
    return v / length


def turn(v, axis, angle):
    return (v*math.cos(angle) + axis.Cross(v)*math.sin(angle)
            + axis*(axis.Dot(v)*(1-math.cos(angle))))


def sweep_frames(helper, segment, intervals, closed, offsets=None, initial_x=None):
    frames = []
    for j in range(intervals+1):
        t = offsets[j] if offsets is not None else j/intervals
        frame = path_frame(helper, t, segment)
        if closed and j in (0, intervals):
            a = helper.GetPosition(1-1e-5, segment, True, True)
            b = helper.GetPosition(1e-5, segment, True, True)
            frame.v3 = unit(b-a)
        z = frame.v3
        if frames:
            previous = frames[-1]
            axis = previous.v3.Cross(z)
            sine = math.sqrt(axis.Dot(axis))
            cosine = max(-1.0, min(1.0, previous.v3.Dot(z)))
            x = (turn(previous.v1, axis/sine, math.atan2(sine, cosine))
                 if sine > 1e-10 else previous.v1)
        else:
            x = initial_x if initial_x is not None else frame.v1
        frame.v1 = unit(x-z*x.Dot(z))
        frame.v2 = z.Cross(frame.v1)
        frames.append(frame)
    if closed:
        # Distribute parallel-transport holonomy so the seam has no roll jump.
        first, last = frames[0], frames[-1]
        correction = math.atan2(last.v3.Dot(last.v1.Cross(first.v1)),
                                last.v1.Dot(first.v1))
        for j, frame in enumerate(frames):
            t = offsets[j] if offsets is not None else j/intervals
            frame.v1 = turn(frame.v1, frame.v3, correction*t)
            frame.v2 = frame.v3.Cross(frame.v1)
        frames[-1] = frames[0]
    return frames


def corner_samples(helper, segment, intervals, closed, extent, width_curve=None):
    offsets = [j/intervals for j in range(intervals+1)]
    corners = {}
    if not isinstance(helper, DistancePath):
        return offsets, corners
    points, distances = helper.segments[segment]
    length = distances[-1]
    last = len(points)-1
    for i in range(0 if closed else 1, last):
        incoming = unit(points[i]-points[i-1 if i else last-1])
        outgoing = unit(points[i+1]-points[i])
        cosine = max(-1.0, min(1.0, incoming.Dot(outgoing)))
        if cosine > math.cos(math.radians(15)):
            continue
        if cosine < -0.999:
            raise ValueError('A reversing spline corner cannot form a miter joint.')
        t = distances[i]/length
        scale = math.sqrt(2/(1+cosine))
        bend = unit(outgoing-incoming)
        clearance = extent*width_factor(width_curve,t)*math.sqrt((1-cosine)/(1+cosine))/length
        # Retain endpoints, but omit regular rings intersecting the miter plane.
        def away(u):
            distance = abs(u-t)
            if closed:
                distance = min(distance, 1-distance)
            return distance > clearance+1e-10
        offsets = [u for u in offsets if u in (0.0, 1.0) or away(u)]
        corners[t] = (bend, scale)
    offsets = sorted(set(offsets) | set(corners))
    if closed and 0.0 in corners:
        corners[1.0] = corners[0.0]
    return offsets, corners


def as_spline(node):
    # Hierarchy evaluation can return LineObjects even with ASSPLINE.
    if node.CheckType(c4d.Oline):
        count = node.GetPointCount()
        if count < 2:
            return None
        tag = node.GetTag(c4d.Tsegment)
        segments = tag.GetAllHighlevelData() if tag else []
        spline = c4d.SplineObject(count, c4d.SPLINETYPE_LINEAR)
        spline.ResizeObject(count, len(segments))
        spline.SetAllPoints(node.GetAllPoints())
        for i, segment in enumerate(segments):
            spline.SetSegment(i, segment['cnt'], segment['closed'])
        if len(segments) == 1:
            spline[c4d.SPLINEOBJECT_CLOSED] = bool(segments[0]['closed'])
        spline.Message(c4d.MSG_UPDATE)
        return spline
    return node.GetRealSpline()


def polygon_mesh(points, faces, name, uv_faces=None):
    obj = c4d.PolygonObject(len(points), len(faces))
    obj.SetAllPoints(points)
    for i, face in enumerate(faces):
        obj.SetPolygon(i, c4d.CPolygon(*face))
    obj.SetName(name)
    obj.SetPhong(True, True, math.radians(40))
    if uv_faces is not None:
        tag = c4d.UVWTag(len(faces))
        for i, uv in enumerate(uv_faces):
            values = [c4d.Vector(u,v,0) for u,v in uv]
            if len(values) == 3:
                values.append(values[-1])
            tag.SetSlow(i, *values)
        obj.InsertTag(tag)
    obj.Message(c4d.MSG_UPDATE)
    return obj


def perimeter_u(profile):
    lengths = [0.0]
    for a,b in zip(profile,profile[1:]+profile[:1]):
        lengths.append(lengths[-1]+math.dist(a,b))
    return [d/lengths[-1] for d in lengths]


def remap_v(mesh, start, end):
    tag = mesh.GetTag(c4d.Tuvw)
    if tag is None or (start == 0 and end == 1):
        return
    for i in range(tag.GetDataCount()):
        uv = tag.GetSlow(i)
        tag.SetSlow(i, *[c4d.Vector(uv[k].x,start+(end-start)*uv[k].y,0)
                        for k in ('a','b','c','d')])


def cap_uv(face, vertex_uv):
    values = [vertex_uv[i] for i in face]
    known = [u for u,v in values if u is not None]
    seam = bool(known and max(known)-min(known)>0.5)
    values = [(min(1.0,u+1) if seam and u is not None and u<0.5 else u,v) for u,v in values]
    known = [u for u,v in values if u is not None]
    center = sum(known)/len(known) if known else 0.5
    return [(center if u is None else u,v) for u,v in values]


def sweep_mesh(helper, segment, profile, intervals, closed, turns, caps,
               strand_offset=0.0, phase=0.0, cap_style=None, width_curve=None,
               initial_x=None, uv_span=None):
    extent = max(math.hypot(x+strand_offset,y) for x,y in profile)
    offsets, corners = corner_samples(helper, segment, intervals, closed, extent, width_curve)
    intervals = len(offsets)-1
    rings = intervals if closed else intervals+1
    count = len(profile)
    cap_points = 2*(int(cap_style[2])*count+1) if cap_style and caps and not closed else 2
    if rings*count + cap_points > MAX_POINTS:
        raise ValueError('Too much geometry: increase Path Step.')
    points, vertex_uv = [], []
    us = perimeter_u(profile)
    path_length = helper.GetSegmentLength(segment)
    cap_budget = (max(0.001, min(max(abs(x) for x,y in profile),
                               max(abs(y) for x,y in profile))) if caps and not closed else 0)
    if uv_span is None:
        left = cap_budget*width_factor(width_curve,0)
        right = cap_budget*width_factor(width_curve,1)
        whole = path_length+left+right
        uv_span = (0.0,left/whole,(left+path_length)/whole,1.0)
    tip0,body0,body1,tip1 = uv_span
    frames = sweep_frames(helper, segment, intervals, closed, offsets, initial_x)
    for j in range(rings):
        t = offsets[j]
        frame = frames[j]
        angle = math.tau*turns*t + phase
        cs, sn = math.cos(angle), math.sin(angle)
        for i,(x, y) in enumerate(profile):
            x += strand_offset
            radial = frame.v1*(x*cs-y*sn) + frame.v2*(x*sn+y*cs)
            if t in corners:
                bend, scale = corners[t]
                radial += bend*(radial.Dot(bend)*(scale-1))
            points.append(frame.off + radial*width_factor(width_curve,t))
            vertex_uv.append((us[i], body0+(body1-body0)*t))
    faces = sides(rings, count, closed)
    uv_faces = []
    for j in range(rings if closed else rings-1):
        va = body0+(body1-body0)*offsets[j]
        vb = body0+(body1-body0)*offsets[j+1]
        for i in range(count):
            uv_faces.append([(us[i],va),(us[i+1],va),(us[i+1],vb),(us[i],vb)])
    if caps and not closed:
        if cap_style:
            for ring, sign in ((0, -1), (rings-1, 1)):
                frame = frames[ring]
                angle = math.tau*turns*offsets[ring] + phase
                cs, sn = math.cos(angle), math.sin(angle)
                size = width_factor(width_curve, offsets[ring])
                def world(x, y, z):
                    return frame*(c4d.Vector(x*cs-y*sn, x*sn+y*cs, sign*z)*size)
                previous = list(range(ring*count, (ring+1)*count))
                kind, radius, steps = cap_style
                steps = max(1, int(steps))
                hx = max(abs(p[0]) for p in profile)
                hy = max(abs(p[1]) for p in profile)
                base_v, tip_v = (body0,tip0) if sign<0 else (body1,tip1)
                cap_fraction = 0.75 if kind=='rectangle' and min(hx,hy)>radius+1e-9 else 1.0
                for k in range(1, steps+1):
                    theta = math.pi/2*k/steps
                    factor = 0.0 if k == steps else math.cos(theta)
                    layer, unique = [], {}
                    for pi,(x, y) in enumerate(profile):
                        if kind == 'circle':
                            q = world(x*factor, y*factor, radius*math.sin(theta))
                        else:
                            cx = max(-hx+radius, min(hx-radius, x))
                            cy = max(-hy+radius, min(hy-radius, y))
                            q = world(cx+(x-cx)*factor, cy+(y-cy)*factor,
                                      radius*math.sin(theta))
                        key = tuple(round(v, 10) for v in (q.x, q.y, q.z))
                        if key not in unique:
                            unique[key] = len(points)
                            points.append(q)
                            vertex_uv.append((None if kind=='circle' and k==steps else us[pi],
                                              base_v+(tip_v-base_v)*cap_fraction*k/steps))
                        layer.append(unique[key])
                    for i in range(count):
                        n = (i+1) % count
                        face = list(dict.fromkeys((previous[i], previous[n], layer[n], layer[i])))
                        if len(face) >= 3:
                            faces.append(tuple(face if sign > 0 else reversed(face)))
                            uv_faces.append(cap_uv(faces[-1],vertex_uv))
                    previous = layer
                rim = list(dict.fromkeys(previous))
                if len(rim) >= 3:
                    center = c4d.Vector()
                    for i in rim:
                        center += points[i]
                    ci = len(points)
                    points.append(center/len(rim))
                    vertex_uv.append((None,tip_v))
                    for i, a in enumerate(rim):
                        b = rim[(i+1) % len(rim)]
                        faces.append((ci, a, b) if sign > 0 else (ci, b, a))
                        uv_faces.append(cap_uv(faces[-1],vertex_uv))
            return polygon_mesh(points, faces, 'Profile mesh',uv_faces)
        # Flat cap fallback (including a zero-radius rectangular fillet).
        for ring, reverse in ((0, True), (rings-1, False)):
            base = ring*count
            center = c4d.Vector()
            for p in points[base:base+count]:
                center += p
            center /= count
            ci = len(points)
            points.append(center)
            vertex_uv.append((None,tip0 if reverse else tip1))
            for i in range(count):
                a, b = base+i, base+(i+1) % count
                faces.append((ci, b, a) if reverse else (ci, a, b))
                uv_faces.append(cap_uv(faces[-1],vertex_uv))
    return polygon_mesh(points, faces, 'Profile mesh',uv_faces)


class PieceCurve:
    def __init__(self, curve, start, end):
        self.curve, self.start, self.end = curve, start, end

    def GetKnotCount(self):
        return 2

    def GetPoint(self, t):
        return c4d.Vector(t, width_factor(self.curve, self.start+(self.end-self.start)*t), 0)


def piece_ranges(length, piece, space, closed, count=None):
    piece, space = max(0.001, float(piece)), float(space)
    if count is not None:
        count = max(1,min(10000,int(count)))
        if piece > length:
            raise ValueError('Segment Length must not exceed spline length in Count mode.')
        if count == 1:
            start = (length-piece)/2
            return [(start,start+piece)]
        # Closed loops use equal cyclic pitch; center each piece in its cell.
        if closed and piece <= length/count:
            pitch = length/count
            return [(i*pitch+(pitch-piece)/2,i*pitch+(pitch+piece)/2) for i in range(count)]
        pitch = (length-piece)/(count-1)
        return [(i*pitch,i*pitch+piece) for i in range(count)]
    pitch = piece+space
    if pitch <= 1e-7:
        raise ValueError('Space Length must be greater than minus Segment Length.')
    # Closed paths reserve a gap after the last piece, including at the seam.
    full_count = max(0, int(math.floor((length-piece+1e-9)/pitch))+1)
    count = min(full_count, max(0, int(math.floor((length+1e-9)/pitch)))) if closed else full_count
    if count > 10000:
        raise ValueError('Too many pieces: increase Segment Length or Space Length.')
    return [(i*(piece+space), i*(piece+space)+piece) for i in range(count)]


def gap_meshes(helper, segment, profile, length, closed, piece, space,
               step, turns, caps, cap_style, curve, tilt_x=0.0, tilt_y=0.0,
               count=None):
    slots = piece_ranges(length, piece, space, closed,count)
    points, distances = helper.segments[segment]
    bodies = []
    depth = cap_style[1] if caps and cap_style else 0.0
    extent = max(math.hypot(x,y) for x,y in profile)
    start_planes, end_planes = {}, {}
    pairs = [(i,i+1,0.0) for i in range(len(slots)-1)]
    if closed and len(slots)>1:
        pairs.append((len(slots)-1,0,length))
    for i,j,wrap in pairs:
        gap = slots[j][0]+wrap-slots[i][1]
        if gap < 0:
            continue  # Retain intentionally overlapping intervals.
        middle = (slots[i][1]+slots[j][0]+wrap)/2
        frame = path_frame(helper,(middle % length)/length,segment)
        # Both neighboring ends use parallel clearance planes at the gap.
        end_planes[i] = (frame.off-frame.v3*gap/2,frame.v3)
        start_planes[j] = (frame.off+frame.v3*gap/2,frame.v3)
    for index,(start, end) in enumerate(slots):
        # Solve cap base positions so their tips fit inside the requested span.
        def base(at_start):
            lo, hi = start, end
            for _ in range(48):
                mid = (lo+hi)/2
                d = depth*width_factor(curve, mid/length)
                plane = (start_planes if at_start else end_planes).get(index)
                if plane is None:
                    value = mid-d-start if at_start else mid+d-end
                else:
                    boundary,normal = plane
                    frame = path_frame(helper,mid/length,segment)
                    cosine = min(1.0,abs(frame.v3.Dot(normal)))
                    support = (extent*math.sqrt(max(0,1-cosine*cosine))
                               + depth*cosine)*width_factor(curve,mid/length)
                    value = (frame.off-boundary).Dot(normal) + (-support if at_start else support)
                if value < 0:
                    lo = mid
                else:
                    hi = mid
            return (lo+hi)/2
        a = base(True) if depth or index in start_planes else start
        b = base(False) if depth or index in end_planes else end
        if b-a <= 1e-7:
            raise ValueError('Segment Length is too short for the current rounded caps.')
        bodies.append((a,b))
    if not bodies:
        raise ValueError('Segment Length and Space Length do not fit this spline segment.')
    # Transport orientation across gaps instead of restarting each rectangle.
    n = max(3 if closed else 1, int(math.ceil(length/step)))
    if n > MAX_POINTS:
        raise ValueError('Too many path samples: increase Path Step.')
    offsets = sorted(set([j/n for j in range(n+1)] + [a/length for a,b in bodies]
                         + [(a+b)/(2*length) for a,b in bodies]))
    frames = sweep_frames(helper,segment,len(offsets)-1,closed,offsets)
    seeds = {t:frame.v1 for t,frame in zip(offsets,frames)}
    frame_at = dict(zip(offsets,frames))
    for index,(a,b) in enumerate(bodies):
        cropped = [helper.GetPosition(a/length,segment)]
        cropped.extend(p for p,d in zip(points,distances) if a < d < b)
        cropped.append(helper.GetPosition(b/length,segment))
        path = DistancePath([(cropped,False)])
        va,vb = a/length,b/length
        if caps and cap_style is None:
            # Reserve V space for a planar cap's radial fan as well.
            reserve = min((b-a)/4, min(max(abs(x) for x,y in profile),
                                       max(abs(y) for x,y in profile))) / length
            va,vb = va+reserve,vb-reserve
        result = sweep_mesh(path,0,profile,max(1,int(math.ceil((b-a)/step))),
                            False,turns*(b-a)/length,caps,
                            phase=math.tau*turns*a/length,cap_style=cap_style,
                            width_curve=PieceCurve(curve,a/length,b/length),
                            initial_x=seeds[a/length],
                            uv_span=(slots[index][0]/length,va,vb,slots[index][1]/length))
        result.SetName('Gap segment')
        if tilt_x or tilt_y:
            frame = frame_at[(a+b)/(2*length)]
            # Rigid piece rotation about its midpoint, in the transported frame.
            rotated = []
            for point in result.GetAllPoints():
                delta = turn(point-frame.off, frame.v1, tilt_x)
                delta = turn(delta, frame.v2, tilt_y)
                rotated.append(frame.off+delta)
            result.SetAllPoints(rotated)
            result.Message(c4d.MSG_UPDATE)
        yield result


def chain_mesh(helper, segment, length, closed, radius, diameter, step, turns, width_curve=None):
    # Oval links have centerline half-width r and half-length 1.6r.
    # Alternating link planes interlock along the path tangent.
    tube = max(0.0005, diameter/2)
    radius = max(0.001, radius)
    if tube >= radius:
        raise ValueError('Chain diameter must be smaller than twice Radius.')
    spacing = max(radius, 2.1*radius - tube)
    links = max(1, int(length/spacing))
    if closed:
        links = max(2, links + links % 2)
    major = max(16, min(200, int(math.ceil(math.tau*radius*1.3 / step))))
    major = min(200,4*int(math.ceil(major/4)))
    minor = 12
    if links*major*minor > MAX_POINTS:
        raise ValueError('Too many chain links: increase Radius or Path Step.')
    points, faces, uv_faces = [], [], []
    frames = sweep_frames(helper, segment, links*2, closed)
    for link in range(links):
        t = link/links if closed else (link+0.5)/links
        size = width_factor(width_curve,t)
        frame = frames[link*2 if closed else link*2+1]
        angle = (link % 2)*math.pi/2 + math.tau*turns*t
        across = frame.v1*math.cos(angle) + frame.v2*math.sin(angle)
        normal = frame.v2*math.cos(angle) - frame.v1*math.sin(angle)
        tangent = frame.v3
        base = len(points)
        for j in range(major):
            a = math.tau*j/major
            center = frame.off + across*(radius*math.cos(a)) + tangent*(1.6*radius*math.sin(a))
            outward = (across*(1.6*math.cos(a)) + tangent*math.sin(a)).GetNormalized()
            for k in range(minor):
                b = math.tau*k/minor
                point = center + tube*(outward*math.cos(b) + normal*math.sin(b))
                points.append(frame.off + (point-frame.off)*size)
        faces.extend(sides(major, minor, True, base))
        for j in range(major):
            va = (link+0.5+0.5*math.sin(math.tau*j/major))/links
            vb = (link+0.5+0.5*math.sin(math.tau*(j+1)/major))/links
            for k in range(minor):
                uv_faces.append([(k/minor,va),((k+1)/minor,va),
                                 ((k+1)/minor,vb),(k/minor,vb)])
    return polygon_mesh(points, faces, 'Chain',uv_faces)


class SplineMesherBlue(plugins.ObjectData):
    def Init(self, op, isCloneInit=False):
        return self._defaults(op, isCloneInit)

    def _defaults(self, op, isCloneInit=False, reset_curve=False):
        if reset_curve or op[WIDTH_CURVE] is None:
            curve = c4d.SplineData()
            curve.MakeLinearSplineLinear(2)
            for i, knot in enumerate(curve.GetKnots()):
                curve.SetKnot(i, c4d.Vector(float(i), 1, 0), knot['lFlagsSettings'],
                              interpol=c4d.CustomSplineKnotInterpolationLinear)
            curve.SetRange(0, 1, 0.1, 0, 2, 0.1)
            op[WIDTH_CURVE] = curve
        if not isCloneInit:
            for key, value in {PROFILE:CIRCLE, RADIUS:5.0, ROTATIONS:0,
                    STEP:5.0, CIRCLE_SEGMENTS:24, WIDTH:10.0, HEIGHT:10.0,
                    FILLET:0.0, FILLET_SEGMENTS:4, DIAMETER:2.0, CAPS:True,
                    GAPS:False, PIECE_LENGTH:50.0, SPACE_LENGTH:10.0,
                    PIECE_TILT_X:0.0, PIECE_TILT_Y:0.0,
                    GAP_MODE:0, PIECE_COUNT:10}.items():
                op[key] = value
        self.status = 'Place a spline under this generator.'
        return True

    def Message(self, op, message, data):
        if (message == c4d.MSG_DESCRIPTION_COMMAND and data
                and data['id'][0].id == RESET_ALL):
            doc = op.GetDocument()
            if doc:
                doc.StartUndo()
            try:
                if doc:
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE, op)
                self._defaults(op, reset_curve=True)
                op.SetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_DESCRIPTION)
                op.Message(c4d.MSG_UPDATE)
            finally:
                if doc:
                    doc.EndUndo()
            c4d.EventAdd()
        return True

    def GetDDescription(self, op, description, flags):
        if not description.LoadDescription(op.GetType()):
            return False
        mode = op[PROFILE]
        visible = {
            RADIUS:mode != RECTANGLE, CIRCLE_SEGMENTS:mode == CIRCLE,
            WIDTH:mode == RECTANGLE, HEIGHT:mode == RECTANGLE,
            FILLET:mode == RECTANGLE, FILLET_SEGMENTS:mode == RECTANGLE,
            DIAMETER:mode == CHAIN, CAPS:mode in (CIRCLE, RECTANGLE),
            GAPS_GROUP:mode in (CIRCLE, RECTANGLE),
        }
        for key, shown in visible.items():
            bc = description.GetParameterI(c4d.DescID(key))
            if bc is not None:
                bc[c4d.DESC_HIDE] = not shown
        bc = description.GetParameterI(c4d.DescID(STATUS))
        if bc is not None:
            bc[c4d.DESC_NAME] = getattr(self, 'status', '')
        return True, flags | c4d.DESCFLAGS_DESC_LOADED

    def GetDEnabling(self, op, id, t_data, flags, itemdesc):
        if id[0].id == SPACE_LENGTH:
            return bool(op[GAPS]) and not op[GAP_MODE]
        if id[0].id == PIECE_COUNT:
            return bool(op[GAPS]) and op[GAP_MODE] == 1
        if id[0].id == GAP_MODE:
            return bool(op[GAPS])
        if id[0].id in (PIECE_LENGTH, SPACE_LENGTH, PIECE_TILT_X, PIECE_TILT_Y):
            return bool(op[GAPS])
        if id[0].id == FILLET_SEGMENTS:
            return op[FILLET] > 0
        return True

    def GetVirtualObjects(self, op, hh):
        child = op.GetDown()
        if child is None:
            self.status = 'Place a spline under this generator.'
            return c4d.BaseObject(c4d.Onull)
        # This API owns the hierarchy's dirty check and cache lifetime.
        # Do not feed CheckCache/IsDirty back into its `dirty` argument:
        # a viewport evaluation is not necessarily a geometry change.
        result = op.GetAndCheckHierarchyClone(hh, child,
                    c4d.HIERARCHYCLONEFLAGS_ASSPLINE, True)
        if not result:
            return c4d.BaseObject(c4d.Onull)
        if not result['dirty']:
            return result['clone']
        root = c4d.BaseObject(c4d.Onull)
        root.SetName('Mesher Pro result')
        self.status = ''
        try:
            mode = int(op[PROFILE])
            radius = max(0.001, float(op[RADIUS]))
            step = max(0.1, float(op[STEP]))
            turns = int(op[ROTATIONS])
            width_curve = op[WIDTH_CURVE]
            if mode == RECTANGLE:
                profile = rectangle(op[WIDTH], op[HEIGHT], op[FILLET], op[FILLET_SEGMENTS])
            else:
                profile = circle(radius if mode == CIRCLE else radius*0.46,
                                 op[CIRCLE_SEGMENTS] if mode == CIRCLE else 12)
            built = 0
            total = 0

            def visit(node, parent_matrix, source=None):
                nonlocal built, total
                while node:
                    matrix = parent_matrix * node.GetMl()
                    spline = as_spline(node)
                    if spline is not None:
                        helper = utils.SplineHelp()
                        if helper.InitSplineWith(spline, c4d.SPLINEHELPFLAGS_RETAINLINEOBJECT):
                            helper, closed_segments = distance_path(helper, spline, source)
                            lengths = [helper.GetSegmentLength(i) for i in range(helper.GetSegmentCount())]
                            full_length = sum(lengths)
                            accumulated = 0.0
                            for segment in range(helper.GetSegmentCount()):
                                length = helper.GetSegmentLength(segment)
                                uv_start = accumulated/full_length if full_length else 0
                                accumulated += length
                                uv_end = accumulated/full_length if full_length else 1
                                if length <= 1e-7:
                                    continue
                                closed = closed_segments[segment]
                                intervals = max(3 if closed else 1, int(math.ceil(length/step)))
                                if mode == CHAIN:
                                    meshes = [chain_mesh(helper, segment, length, closed,
                                              radius, op[DIAMETER], step, turns, width_curve)]
                                elif mode == ROPE:
                                    meshes = [sweep_mesh(helper, segment, profile, intervals,
                                              closed, turns, False, radius*0.54,
                                              math.tau*i/3, width_curve=width_curve) for i in range(3)]
                                else:
                                    fillet = max(0.0, min(op[FILLET], op[WIDTH]/2, op[HEIGHT]/2))
                                    cap_style = (('circle', radius, max(4, int(math.ceil(len(profile)/4))))
                                                 if mode == CIRCLE else
                                                 ('rectangle', fillet, op[FILLET_SEGMENTS]) if fillet > 0 else None)
                                    if op[GAPS]:
                                        meshes = gap_meshes(helper,segment,profile,length,closed,
                                                   op[PIECE_LENGTH] or 50.0,
                                                   op[SPACE_LENGTH] or 0.0, step,turns,
                                                   op[CAPS],cap_style,width_curve,
                                                   op[PIECE_TILT_X] or 0.0, op[PIECE_TILT_Y] or 0.0,
                                                   count=(op[PIECE_COUNT] or 10) if op[GAP_MODE]==1 else None)
                                    else:
                                        meshes = [sweep_mesh(helper, segment, profile, intervals,
                                                  closed, turns, op[CAPS], cap_style=cap_style,
                                                  width_curve=width_curve)]
                                for mesh in meshes:
                                    remap_v(mesh,uv_start,uv_end)
                                    total += mesh.GetPointCount()
                                    if total > MAX_POINTS:
                                        raise ValueError('Too much geometry: increase Path Step.')
                                    mesh.SetMl(matrix)
                                    mesh.InsertUnderLast(root)
                                    built += 1
                    elif node.GetDown():
                        visit(node.GetDown(), matrix, source.GetDown() if source else None)
                    node = node.GetNext()
                    source = source.GetNext() if source else None

            visit(result['clone'], c4d.Matrix(), child)
            self.status = ('Ready' if built else 'No usable spline found in the child hierarchy.')
            return root
        except ValueError as error:
            self.status = str(error)
        except Exception:
            self.status = 'Generation failed; see the Python Console.'
            traceback.print_exc()
        return c4d.BaseObject(c4d.Onull)


if __name__ == '__main__':
    icon = bitmaps.BaseBitmap()
    if icon.InitWith(os.path.join(ROOT, 'res', 'icon.png'))[0] != c4d.IMAGERESULT_OK:
        icon = None
    if not plugins.RegisterObjectPlugin(PLUGIN_ID, 'Mesher Pro',
            SplineMesherBlue, 'Osplinemesherblue',
            c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT, icon):
        raise RuntimeError('Mesher Pro registration failed: plugin ID conflict.')
