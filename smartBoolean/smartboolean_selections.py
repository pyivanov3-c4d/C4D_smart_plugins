"""Preserve selection membership through planar reconstruction."""
from collections import defaultdict
import smartboolean_cleanup as g
import smartboolean_retopology as r
from smartboolean_spatial import BoxIndex, bounds

def polygons(points, faces, new_points, new_faces, selected, tolerance):
    def key(p): return tuple(round(v/tolerance) for v in p)
    def plane(p,f):
        n=r.normal(p,f)
        return tuple(round(v,6) for v in n)+(round(g.dot(n,p[f[0]]),6),)
    exact={tuple(sorted(key(points[v]) for v in f)):i for i,f in enumerate(faces)}
    groups=defaultdict(set)
    for i,f in enumerate(faces):groups[plane(points,f)].add(i in selected)
    result=[]
    for i,f in enumerate(new_faces):
        old=exact.get(tuple(sorted(key(new_points[v]) for v in f)))
        if old is not None: member=old in selected
        else:
            states=groups.get(plane(new_points,f),{False})
            if len(states)>1:raise ValueError('Rebuild crosses a polygon selection boundary')
            member=next(iter(states))
        if member:result.append(i)
    return result

def edges(points, faces, new_points, new_faces, selected, tolerance):
    def slots(f):
        return [(0,f[0],f[1]),(1,f[1],f[2]),(3,f[2],f[0])] if len(f)==3 else [(j,f[j],f[(j+1)%4]) for j in range(4)]
    segments={tuple(sorted((points[a],points[b]))) for i,f in enumerate(faces)
              for j,a,b in slots(f) if 4*i+j in selected}
    segment_list=list(segments)
    index=BoxIndex([bounds(a,b,tolerance) for a,b in segment_list])
    result=[];cache={}
    for i,f in enumerate(new_faces):
        for j,a,b in slots(f):
            A,B=new_points[a],new_points[b];key=tuple(sorted((A,B)))
            if key in segments and g.length(g.sub(B,A))>tolerance:
                result.append(4*i+j);continue
            if key not in cache:
                d=g.sub(B,A);length=g.length(d);intervals=[]
                if length>tolerance:
                    unit=tuple(v/length for v in d)
                    for candidate in index.query(bounds(A,B,tolerance)):
                        C,D=segment_list[candidate]
                        c,e=g.sub(C,A),g.sub(D,A)
                        if g.length(g.cross(c,unit))>tolerance or g.length(g.cross(e,unit))>tolerance:continue
                        lo,hi=sorted((g.dot(c,unit),g.dot(e,unit)))
                        if hi>=0 and lo<=length:intervals.append((max(0,lo),min(length,hi)))
                    end=0.0
                    for lo,hi in sorted(intervals):
                        if lo>end+tolerance:break
                        end=max(end,hi)
                    cache[key]=end>=length-tolerance
                else:cache[key]=False
            if cache[key]:result.append(4*i+j)
    return result
