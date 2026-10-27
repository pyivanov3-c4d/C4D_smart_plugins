import json,sys
from pathlib import Path
base=Path(__file__).parent;sys.path.insert(0,str(base.parents[1]/'smartBoolean'))
import smartboolean_cleanup as g
def count(m):
    p=m['points'];edges=[e for e,sides in g.edge_map(m['polygons']).items() if all(abs(p[v][1]-1)<1e-5 for v in e) and any(any(abs(p[v][1]-1)>1e-5 for v in m['polygons'][i]) for i,j in sides)]
    def cross(a,b,c):return (b[0]-a[0])*(c[2]-a[2])-(b[2]-a[2])*(c[0]-a[0])
    boxes=[(min(p[a][0],p[b][0]),max(p[a][0],p[b][0]),min(p[a][2],p[b][2]),max(p[a][2],p[b][2])) for a,b in edges]
    hits=[]
    for i,(a,b) in enumerate(edges):
        A,B=p[a],p[b];bb=boxes[i]
        for j in range(i):
            c,d=edges[j];cc=boxes[j]
            if a in (c,d) or b in (c,d) or bb[1]<cc[0] or cc[1]<bb[0] or bb[3]<cc[2] or cc[3]<bb[2]:continue
            C,D=p[c],p[d]
            if cross(A,B,C)*cross(A,B,D)<-1e-12 and cross(C,D,A)*cross(C,D,B)<-1e-12:hits.append((a,b,c,d))
    return hits
if __name__=='__main__':
    for name in ['small-reference','asym-native-warped','local-expanded']:
        m=json.loads((base/(name+'.json')).read_text());hits=count(m)
        print(name,'crossings',len(hits),'examples',hits[:2])
