"""Weld self-intersecting bevel row loops at their actual contact points."""
from collections import defaultdict
import smartboolean_cleanup as g
from smartboolean_spatial import BoxIndex, bounds


def row_loops(first, second, faces, setup):
    source=setup['points'];seam=setup['seam'];tol=setup['tolerance']
    vertices=sorted({v for edge in seam for v in edge})
    index=BoxIndex([bounds(source[v],source[v]) for v in vertices])
    anchors={}
    for i,(a,b) in enumerate(zip(first,second)):
        if g.length(g.sub(b,a))<=tol:continue
        anchor=tuple(2*a[k]-b[k] for k in range(3))
        candidates=index.query(bounds(anchor,anchor,tol*128))
        if not candidates:continue
        v=min((vertices[j] for j in candidates),key=lambda v:g.length(g.sub(source[v],anchor)))
        if g.length(g.sub(source[v],anchor))<=tol*128:anchors[i]=v
    links=defaultdict(set)
    for a,b in g.edge_map(faces):
        if a not in anchors or b not in anchors:continue
        u,v=anchors[a],anchors[b]
        if u==v or tuple(sorted((u,v))) not in seam:continue
        links[a].add(b);links[b].add(a)
    remaining=set(links);loops=[]
    while remaining:
        start=min(remaining);component={start};todo=[start];remaining.remove(start)
        while todo:
            for v in links[todo.pop()]:
                if v in remaining:remaining.remove(v);component.add(v);todo.append(v)
        if any(len(links[v])!=2 for v in component):continue
        loop=[start];previous=None
        while len(loop)<len(component):
            following=min(links[loop[-1]]-{previous})
            previous=loop[-1];loop.append(following)
        loops.append(loop)
    return loops


def first_contact(points, loop, tol, progress=None):
    edges=list(zip(loop,loop[1:]+loop[:1]))
    index=BoxIndex([bounds(points[a],points[b],tol) for a,b in edges])
    for i,(a,b) in enumerate(edges):
        if progress and i%64==0:progress(i,len(edges),'Checking bevel contact points')
        A,B=points[a],points[b];direction=g.sub(B,A)
        for j in index.query(bounds(A,B,tol)):
            if j<=i:continue
            c,d=edges[j]
            if len({a,b,c,d})<4:continue
            C,D=points[c],points[d];edge=g.sub(D,C)
            cross=g.cross(direction,edge);denom=g.dot(cross,cross)
            if denom<1e-20:continue
            rel=g.sub(C,A)
            t=g.dot(g.cross(rel,edge),cross)/denom
            u=g.dot(g.cross(rel,direction),cross)/denom
            if not (1e-8<t<1-1e-8 and 1e-8<u<1-1e-8):continue
            p=tuple(A[k]+t*direction[k] for k in range(3))
            q=tuple(C[k]+u*edge[k] for k in range(3))
            if g.length(g.sub(p,q))<=tol:return i,j,tuple((p[k]+q[k])*.5 for k in range(3))
    return None


def resolve(points, first, second, faces, setup, progress=None):
    if len(points)!=len(first) or len(first)!=len(second):return points,{},faces
    loops=row_loops(first,second,faces,setup)
    output=list(points);parent=list(range(len(points)));changed=set()
    def root(v):
        while parent[v]!=v:
            parent[v]=parent[parent[v]];v=parent[v]
        return v
    def length(ids,contact):
        ring=[contact]+[output[v] for v in ids]+[contact]
        return sum(g.length(g.sub(a,b)) for a,b in zip(ring,ring[1:]))
    for loop in loops:
        for iteration in range(len(loop)):
            ring=[]
            for v in loop:
                v=root(v)
                if not ring or ring[-1]!=v:ring.append(v)
            if len(ring)>1 and ring[0]==ring[-1]:ring.pop()
            if len(set(ring))!=len(ring) or len(ring)<4:break
            hit=first_contact(output,ring,setup['tolerance']*128,progress)
            if hit is None:break
            i,j,contact=hit
            paths=(ring[i+1:j+1],ring[j+1:]+ring[:i+1])
            cut=min(paths,key=lambda ids:length(ids,contact))
            # Remove only the enclosed collision lobe. Its surrounding row
            # stays intact and both sides terminate at one shared vertex.
            representative=min(cut)
            for v in cut:parent[v]=representative;changed.add(v)
            output[representative]=contact
        else:
            raise ValueError('Bevel collision weld did not converge.')
    if not changed:return points,{},faces
    mapping={i:root(i) for i in range(len(points))}
    output=[output[mapping[i]] for i in range(len(points))]
    rebuilt=[]
    for face in faces:
        ring=[]
        for v in face:
            v=mapping[v]
            if not ring or ring[-1]!=v:ring.append(v)
        if len(ring)>1 and ring[0]==ring[-1]:ring.pop()
        if len(set(ring))<3:continue
        if len(set(ring))!=len(ring):raise ValueError('Welding would create a self-touching polygon.')
        rebuilt.append(ring)
    before=g.edge_map(faces);after=g.edge_map(rebuilt)
    closed=all(len(v)==2 for v in before.values())
    if any(len(v)>2 or closed and len(v)!=2 for v in after.values()):
        raise ValueError('Welding would open the surface or create a non-manifold edge.')
    # Edge counts alone miss bow-tie vertices. Every welded vertex must retain
    # one connected fan of incident faces (a cycle for a closed surface).
    touched={root(v) for v in changed};fans=defaultdict(lambda:defaultdict(set))
    for face in rebuilt:
        for i,v in enumerate(face):
            if v not in touched:continue
            a,b=face[i-1],face[(i+1)%len(face)]
            fans[v][a].add(b);fans[v][b].add(a)
    for fan in fans.values():
        if any(len(v)>2 or closed and len(v)!=2 for v in fan.values()):
            raise ValueError('Welding would create a non-manifold vertex.')
        unseen=set(fan);todo=[unseen.pop()]
        while todo:
            for v in fan[todo.pop()]:
                if v in unseen:unseen.remove(v);todo.append(v)
        if unseen:raise ValueError('Welding would join disconnected surface fans.')
    return output,{i:v for i,v in mapping.items() if i!=v},rebuilt
