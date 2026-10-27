import json,sys,unittest
from pathlib import Path
base=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(base/'smartBoolean'))
import smartboolean_weld as w
import smartboolean_cleanup as g
import smartboolean_collision as collision
def read(name):return json.loads((base/'artifacts/smartBoolean'/(name+'.json')).read_text())

class WeldTests(unittest.TestCase):
    def test_real_collision_rows_become_shared_manifold_junctions(self):
        mesh,ref,setup=read('weld-current'),read('weld-reference'),read('weld-source')
        setup['seam']={tuple(e) for e in setup['seam']}
        loops=w.row_loops(ref['first'],ref['second'],mesh['polygons'],setup)
        self.assertTrue(any(w.first_contact(mesh['points'],ring,setup['tolerance']*128) for ring in loops))
        points,mapping,faces=w.resolve(mesh['points'],ref['first'],ref['second'],mesh['polygons'],setup)
        self.assertGreater(len(mapping),50)
        self.assertLess(len(faces),len(mesh['polygons']))
        self.assertTrue(all(len(sides)==2 for sides in g.edge_map(faces).values()))
        for ring in loops:
            rebuilt=[]
            for v in ring:
                v=mapping.get(v,v)
                if not rebuilt or rebuilt[-1]!=v:rebuilt.append(v)
            if rebuilt[0]==rebuilt[-1]:rebuilt.pop()
            self.assertIsNone(w.first_contact(points,rebuilt,setup['tolerance']*128))
        for i,(a,b) in enumerate(zip(ref['first'],ref['second'])):
            if g.length(g.sub(a,b))<=setup['tolerance']:
                self.assertEqual(points[i],mesh['points'][i])
        for v,representative in mapping.items():
            self.assertEqual(points[v],points[representative])
            self.assertTrue(all(v not in face for face in faces))

    def test_separated_planar_flower_contour_is_unchanged(self):
        raw,a,b=read('flower-raw'),read('flower-small'),read('flower-second')
        seam={tuple(e) for e in read('flower-seam')}
        setup=collision.plan(raw['points'],raw['polygons'],seam,10,1e-7)
        setup['reference']=.2
        points=collision.expand(a['points'],b['points'],setup,a['polygons'])
        result,mapping,faces=w.resolve(points,a['points'],b['points'],a['polygons'],setup)
        self.assertEqual(result,points);self.assertEqual(mapping,{})
        self.assertEqual(faces,a['polygons'])

    def test_nearby_original_points_are_never_distance_welded(self):
        points=[(0,0,0),(1e-10,0,0),(0,1,0),(1,1,0)]
        faces=[(0,1,3,2)]
        setup=dict(points=points,seam={(0,1),(1,3),(2,3),(0,2)},tolerance=1e-7)
        result,mapping,rebuilt=w.resolve(points,points,points,faces,setup)
        self.assertIs(result,points);self.assertEqual(mapping,{})
        self.assertEqual(rebuilt,faces)
