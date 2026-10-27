import sys,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'smartBoolean'))
import smartboolean_selections as s
import smartboolean_retopology as r
import smartboolean_cleanup as g

class SelectionTransferTests(unittest.TestCase):
    def test_split_nonplanar_quad_preserves_boundary_uv(self):
        p=[(0,0,0),(2,0,0),(2,2,1),(0,2,0),(1,0,0)]
        uv=[[(0,0,0),(1,0,0),(1,1,0),(0,1,0)]]
        result=r.transfer_uv(p,[(0,1,2,3)],uv,p,[(0,4,3),(4,1,2),(4,2,3)],1e-8)
        self.assertEqual(result[0],[(0,0,0),(.5,0,0),(0,1,0)])

    def test_collapsed_transition_reconnects_middle_point(self):
        path=Path(__file__).resolve().parents[1]/'artifacts/smartBoolean/creases-finish-input.json'
        d=json.loads(path.read_text());p=d['points']
        faces=r.finish_patches(p,d['polygons'],d['groups'],2e-7)
        clean=r.remove_collapsed_faces(p,faces,2e-7)
        self.assertNotIn((1652,1806,2472),clean)
        self.assertFalse(any(set(face)=={1652,1806,2472} for face in clean))
        self.assertTrue(all(len(v)==2 for v in g.edge_map(clean).values()))

    def test_joined_edge_keeps_selection_across_source_stations(self):
        p=[(0,0,0),(1,0,0),(2,0,0),(2,1,0),(0,1,0)]
        f=[(0,1,4),(1,2,3,4)]
        self.assertEqual(s.edges(p,f,p,[(0,2,3,4)],{0,4},1e-8),[0])
        self.assertEqual(s.edges(p,f,p,[(0,2,3,4)],{0},1e-8),[])

    def test_planar_cap_membership_survives_retriangulation(self):
        p=[(0,0,0),(1,0,0),(1,1,0),(0,1,0)]
        self.assertEqual(s.polygons(p,[(0,1,2),(0,2,3)],p,[(0,1,2,3)],{0,1},1e-8),[0])
        with self.assertRaises(ValueError):
            s.polygons(p,[(0,1,2),(0,2,3)],p,[(0,1,2,3)],{0},1e-8)

if __name__=='__main__':unittest.main()
