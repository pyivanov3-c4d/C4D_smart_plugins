"""Topology planning independent of C4D. All point coordinates are tuples."""
import math
from collections import defaultdict

def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def length(v): return math.sqrt(dot(v,v))

def edge_map(faces):
    edges=defaultdict(list)
    for i,p in enumerate(faces):
        q=list(p) if len(p)==4 else list(p)+[p[-1]]
        for j,(a,b) in enumerate(zip(q,q[1:]+q[:1])):
            if a!=b: edges[tuple(sorted((a,b)))].append((i,j))
    return edges

def straight_segments(points, edges, tolerance):
    """Merge only straight degree-two chains; preserve corners and branches."""
    links=defaultdict(set)
    for a,b in edges:
        links[a].add(b); links[b].add(a)
    corners=set()
    for v,neighbors in links.items():
        if len(neighbors)!=2:
            corners.add(v); continue
        a,b=neighbors
        u,w=sub(points[a],points[v]),sub(points[b],points[v])
        if dot(u,w)>=0 or length(cross(u,w))>tolerance*max(length(u),length(w)):
            corners.add(v)
    visited=set(); result=[]
    for start in list(corners)+list(links):
        for neighbor in links[start]:
            key=tuple(sorted((start,neighbor)))
            if key in visited: continue
            visited.add(key); previous,current=start,neighbor
            while current not in corners and current!=start:
                following=next((v for v in links[current] if v!=previous),None)
                if following is None: break
                key=tuple(sorted((current,following)))
                if key in visited: break
                visited.add(key); previous,current=current,following
            if start!=current: result.append((points[start],points[current]))
    return result

def segment_distance2(p,a,b):
    v=sub(b,a); vv=dot(v,v)
    t=max(0.,min(1.,dot(sub(p,a),v)/vv)) if vv else 0.
    return sum((p[i]-a[i]-t*v[i])**2 for i in range(3))

class Segments:
    def __init__(self, segments, radius):
        self.segments=segments
        pts=[p for s in segments for p in s]
        extent=max((max(p[i] for p in pts)-min(p[i] for p in pts) for i in range(3)),default=1.)
        self.cell=max(radius,extent/64.,1e-9)
        self.bins=defaultdict(list); self.wide=[]
        for index,(a,b) in enumerate(segments):
            lo=[math.floor((min(a[i],b[i])-radius)/self.cell) for i in range(3)]
            hi=[math.floor((max(a[i],b[i])+radius)/self.cell) for i in range(3)]
            if math.prod(hi[i]-lo[i]+1 for i in range(3))>4096:
                self.wide.append(index); continue
            for x in range(lo[0],hi[0]+1):
                for y in range(lo[1],hi[1]+1):
                    for z in range(lo[2],hi[2]+1): self.bins[x,y,z].append(index)
    def candidates(self,p):
        return self.bins.get(tuple(math.floor(v/self.cell) for v in p),[])+self.wide
    def near(self,p,radius):
        return any(segment_distance2(p,*self.segments[i])<=radius*radius for i in self.candidates(p))
    def contains_edge(self,a,b,tolerance):
        # Both endpoints must lie on the SAME seam span, never just near two spans.
        return any(segment_distance2(a,*self.segments[i])<=tolerance*tolerance and
                   segment_distance2(b,*self.segments[i])<=tolerance*tolerance
                   for i in self.candidates(a))

def dissolve_band(points, faces, seam_edges, width, tolerance):
    """Coplanar edges inside a local corridor; protect its outer connection ring."""
    segments=straight_segments(points,seam_edges,tolerance)
    radius=width*1.25
    index=Segments(segments,radius)
    near=[index.near(p,radius) for p in points]
    # Requiring every vertex protects edges connecting to untouched polygons.
    band=[all(near[v] for v in p) for p in faces]
    normals=[]
    for p in faces:
        n=cross(sub(points[p[1]],points[p[0]]),sub(points[p[2]],points[p[0]]))
        size=length(n)
        normals.append(tuple(v/size for v in n) if size else (0.,0.,0.))
    selected=[]
    for (a,b),sides in edge_map(faces).items():
        if len(sides)!=2 or (a,b) in seam_edges: continue
        (i,j),(k,l)=sides
        if not (band[i] and band[k]): continue
        # Also verify all quad vertices are planar, not just the first triangle.
        n=normals[i]
        if dot(n,normals[k])<1.-1e-10: continue
        origin=points[faces[i][0]]
        if any(abs(dot(sub(points[v],origin),n))>tolerance for v in faces[i]+faces[k]): continue
        selected.extend((4*i+j,4*k+l))
    return selected, segments
