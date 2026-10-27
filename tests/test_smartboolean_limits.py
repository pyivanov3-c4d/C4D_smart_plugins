import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'smartBoolean'))
import smartboolean_limits as limits
import smartboolean_cleanup as g

class SideLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mesh=json.loads((ROOT/'artifacts/smartBoolean/asymmetric-user-raw.json').read_text())
        cls.seam={tuple(e) for e in json.loads((ROOT/'artifacts/smartBoolean/asym-seam.json').read_text())}
    def test_small_width_does_not_deform(self):
        self.assertIsNone(limits.plan(self.mesh['points'],self.mesh['polygons'],self.seam,2,1e-7))
    def test_short_side_stops_while_flat_side_grows(self):
        p,f=self.mesh['points'],self.mesh['polygons']
        for width in (6,10):
            plan=limits.plan(p,f,self.seam,width,1e-7)
            self.assertIsNotNone(plan)
            origin,axis,spans=plan
            height,scale=spans[1]
            self.assertAlmostEqual(height,2.568219022742088)
            endpoint=tuple(origin[i]+axis[i]*width for i in range(3))
            final=limits.transform([endpoint],plan,True)[0]
            self.assertAlmostEqual(g.dot(g.sub(final,origin),axis),height,places=6)
            self.assertEqual(limits.planar_clearance(p,f,self.seam,1e-7,width),width)
    def test_other_surface_restores_exactly(self):
        p,f=self.mesh['points'],self.mesh['polygons']
        plan=limits.plan(p,f,self.seam,6,1e-7)
        restored=limits.transform(limits.transform(p,plan),plan,True)
        self.assertLess(max(g.length(g.sub(a,b)) for a,b in zip(p,restored)),1e-10)
    def test_flat_side_stops_at_feature_boundary(self):
        value=limits.planar_clearance(self.mesh['points'],self.mesh['polygons'],self.seam,1e-7,20)
        self.assertAlmostEqual(value,11.558232435790448,places=5)
    def test_native_result_is_closed(self):
        m=json.loads((ROOT/'artifacts/smartBoolean/asym-result.json').read_text())
        self.assertTrue(all(len(s)==2 for s in g.edge_map(m['polygons']).values()))

if __name__=='__main__':unittest.main()
