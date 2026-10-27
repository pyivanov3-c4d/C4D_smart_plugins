"""Dense native fixture: constrained boundaries, point reduction, explicit edges."""
import json,sys,unittest
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'smartBoolean'))
import smartboolean_cleanup as g
import smartboolean_retopology as r

class RetopologyTests(unittest.TestCase):
    def test_corner_footprint_does_not_fold_floor(self):
        m=json.loads((ROOT/'artifacts/smartBoolean/hook-native-v108.json').read_text())
        p,f=m['points'],m['polygons']
        floor=[face for face in f if all(abs(p[v][2]+22.29772424237036)<1e-6 for v in face)]
        self.assertTrue(floor)
        self.assertTrue(all(r.normal(p,face)[2]<-0.99 for face in floor))
        self.assertTrue(all(len(s)==2 for s in g.edge_map(f).values()))
    def test_dense_strip_has_local_cross_connections(self):
        count=100
        p=[(i,0,0) for i in range(count+1)]+[(i,.2,0) for i in reversed(range(count+1))]
        f=r.triangulate(p,[list(range(len(p)))],(0,0,1),1e-8)
        edges=g.edge_map(f)
        inside=[e for e,s in edges.items() if len(s)==2]
        self.assertLessEqual(max(abs(p[a][0]-p[b][0]) for a,b in inside),1)
        self.assertEqual(sum(abs(p[a][0]-p[b][0])<1e-8 for a,b in inside),count-1)
        self.assertEqual({v for face in f for v in face},set(range(len(p))))
    def test_corner_stations_removed_before_native_bevel(self):
        m=json.loads((ROOT/'artifacts/smartBoolean/corner-rebuilt.json').read_text())
        p,f=m['points'],m['polygons']
        self.assertTrue(all(len(s)==2 for s in g.edge_map(f).values()))
        stations=[v for v in p if abs(abs(v[0])-72.3)<1e-6 and
                  abs(abs(v[1])-72.3)<1e-6 and 1e-6<v[2]-22.29772424237036<10]
        self.assertEqual(stations,[])
    def test_native_corner_has_no_collapsed_faces(self):
        m=json.loads((ROOT/'artifacts/smartBoolean/corner-native-fixed.json').read_text())
        p,f=m['points'],m['polygons']
        self.assertEqual(len(r.remove_collapsed_faces(p,f,2e-7)),len(f))
        self.assertTrue(all(len(s)==2 for s in g.edge_map(f).values()))
    def test_full_width_native_corner_cleanup(self):
        m=json.loads((ROOT/'artifacts/smartBoolean/full-width-native.json').read_text())
        p,f=m['points'],m['polygons']
        cleaned=r.remove_collapsed_faces(p,f,2e-7)
        self.assertEqual(len(f)-len(cleaned),16)
        self.assertTrue(all(len(s)==2 for s in g.edge_map(cleaned).values()))
        # Both offsets stay at the requested 10 units on the straight side.
        used={v for face in cleaned for v in face}
        wall=[-p[v][2]-22.29772424237036 for v in used
              if abs(p[v][0]-72.3)<1e-6 and abs(p[v][1])<50 and p[v][2]<-22.297725]
        floor=[p[v][0]-72.3 for v in used
               if abs(p[v][2]+22.29772424237036)<1e-6 and abs(p[v][1])<50 and p[v][0]>72.30001]
        self.assertAlmostEqual(min(wall),10)
        self.assertAlmostEqual(min(floor),10)
    def test_folded_quad_is_not_removed_as_collinear(self):
        p=[(0,0,0),(1,1,0),(0,1,0),(1,0,0)]
        self.assertEqual(r.remove_collapsed_faces(p,[(0,1,2,3)],1e-8),[(0,1,2,3)])
    def test_uv_interpolation_and_unchanged_corners(self):
        p=[(0,0,0),(1,0,0),(1,1,0),(0,1,0),(2,0,0),(2,1,0)]
        f=[(0,1,2,3),(1,4,5,2)]
        uv=[[tuple(p[v]) for v in face] for face in f]
        q=p+[(.5,.5,0)]
        out=r.transfer_uv(p,f,uv,q,[f[1],(0,1,6)],1e-8)
        self.assertEqual(out[0],uv[1])
        self.assertEqual(out[1],[(0,0,0),(1,0,0),(.5,.5,0)])
    def test_uv_seam_not_silently_removed(self):
        p=[(0,0,0),(1,0,0),(1,1,0),(0,1,0)]
        f=[(0,1,2),(0,2,3)]
        uv=[[p[v] for v in f[0]],[(p[v][0]+1,p[v][1],0) for v in f[1]]]
        with self.assertRaisesRegex(ValueError,'Discontinuous'):
            r.transfer_uv(p,f,uv,p,[(0,1,3),(1,2,3)],1e-8)
        result=r.transfer_uv(p,f,uv,p,[f[1],(0,1,3)],1e-8,strict=False)
        self.assertEqual(result[0],uv[1])
        self.assertEqual(result[1],[p[v] for v in (0,1,3)])
    def test_collinear_boundary_vertices_survive(self):
        p=[(0,0,0),(1,0,0),(2,0,0),(2,1,0),(1,1,0),(0,1,0)]
        f=r.triangulate(p,[list(range(6))],(0,0,1),1e-8)
        self.assertEqual({v for t in f for v in t},set(range(6)))
        e=g.edge_map(f)
        self.assertEqual({k for k,s in e.items() if len(s)==1}, {(0,1),(1,2),(2,3),(3,4),(4,5),(0,5)})
    def test_hole_stays_open(self):
        p=[(0,0,0),(5,0,0),(5,5,0),(0,5,0),(1,1,0),(1,4,0),(4,4,0),(4,1,0)]
        f=r.triangulate(p,[[0,1,2,3],[4,5,6,7]],(0,0,1),1e-8)
        area=sum(g.length(g.cross(g.sub(p[b],p[a]),g.sub(p[c],p[a])))*.5 for a,b,c in f)
        self.assertAlmostEqual(area,16)
    def test_dense_native_fixture(self):
        m=json.loads((ROOT/'tests/smartboolean_dense_fixture.json').read_text())
        p,f=m['points'],m['polygons']; seam=set()
        for a,b in g.edge_map(f):
            A,B=p[a],p[b]
            if all(abs(q[2]+100)<1e-6 and abs(q[0])<=52.70001 and abs(q[1])<=52.70001 for q in (A,B)):
                if abs(A[0]-B[0])<1e-6 and abs(abs(A[0])-52.7)<1e-6 or abs(A[1]-B[1])<1e-6 and abs(abs(A[1])-52.7)<1e-6: seam.add((a,b))
        p2,f2,origins,spans=r.rebuild(p,f,seam,10,1e-7)
        self.assertFalse(any(abs(abs(v[0])-52.7)<1e-6 and
                             abs(abs(v[1])-52.7)<1e-6 and -110<v[2]<-100-1e-6
                             for v in p2))
        lookup=g.Segments(spans,1e-7)
        seam2=[(a,b) for a,b in g.edge_map(f2) if lookup.contains_edge(p2[a],p2[b],1e-7)]
        self.assertEqual(len(seam2),44)
        self.assertTrue(all(len(s)==2 for s in g.edge_map(f2).values()))
        # Identical spacing along all four straight sides, no paired stations.
        lengths=[g.length(g.sub(p2[a],p2[b])) for a,b in seam2]
        self.assertLess(max(lengths)-min(lengths),1e-6)
        self.assertAlmostEqual(min(lengths),105.4/11)
        # Every retained face has exactly the same ordered geometric vertices.
        for face,origin in zip(f2,origins):
            if origin>=0: self.assertEqual([p2[v] for v in face],[tuple(p[v]) for v in f[origin]])
            if origin>=0:
                self.assertFalse(any(abs(p2[v][2]+100)<1e-6 and
                    52.7+1e-6<abs(p2[v][0])<62.7 and 52.7+1e-6<abs(p2[v][1])<62.7
                    for v in face))
        # Removed faces touch the 1.02-width footprint, not the old 2.5-width band.
        near=g.Segments(spans,10.2); retained=set(origins)
        for i,face in enumerate(f):
            if i not in retained: self.assertTrue(any(near.near(p[v],10.2) or any(g.length(g.sub(p[v],c))<=10.2*2**.5 for span in spans for c in span) for v in face))
        print('Dense fixture: 304 -> 44 uniform seam edges; intact outside faces; watertight.')

if __name__=='__main__': unittest.main()
