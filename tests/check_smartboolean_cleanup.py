"""Regression fixture: native union of two 50x50x50 segmented cubes."""
import json
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'smartBoolean'))
import smartboolean_cleanup as g
m=json.loads((root/'tests/smartboolean_dense_fixture.json').read_text())
p,f=m['points'],m['polygons']
edges=g.edge_map(f)
seam=set()
for a,b in edges:
    A,B=p[a],p[b]
    if all(abs(q[2]+100)<1e-6 and abs(q[0])<=52.70001 and abs(q[1])<=52.70001 for q in (A,B)):
        if (abs(A[0]-B[0])<1e-6 and abs(abs(A[0])-52.7)<1e-6 or
            abs(A[1]-B[1])<1e-6 and abs(abs(A[1])-52.7)<1e-6): seam.add((a,b))
selected,spans=g.dissolve_band(p,f,seam,10,1e-7)
assert len(spans)==4, len(spans)
assert len(seam)==304, len(seam)
chosen=set(selected)
assert selected
for key,sides in edges.items():
    if key in seam: assert not any(i*4+j in chosen for i,j in sides)
    if len(sides)==2: assert all(i*4+j in chosen for i,j in sides) or all(i*4+j not in chosen for i,j in sides)
lookup=g.Segments(spans,1e-7)
assert all(lookup.contains_edge(p[a],p[b],1e-7) for a,b in seam)
assert not lookup.contains_edge((-52.7,-52.7,-100),(52.7,52.7,-100),1e-7)
curved=[(0.,0.,0.),(1.,0.,0.),(1.,1.,0.)]
assert len(g.straight_segments(curved,{(0,1),(1,2)},1e-8))==2
assert len(g.straight_segments([(0.,0.,0.),(1.,0.,0.),(2.,0.,0.)],{(0,1),(1,2)},1e-8))==1
out=root/'artifacts/smartBoolean'; out.mkdir(parents=True,exist_ok=True)
(out/'cleanup-plan.json').write_text(json.dumps({'indices':selected,'spans':spans}))
print(json.dumps({'fixture_points':len(p),'fixture_polygons':len(f),'seam_edges':len(seam),
                  'straight_spans':len(spans),'coplanar_edges_to_melt':len(selected)//2}))
