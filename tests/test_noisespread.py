import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'NoiseSpread'))
import noisespread_geometry as g

def plane(size=20.,offset=(0.,0.,0.)):
    p=[g.add(v,offset) for v in ((-size,0,-size),(-size,0,size),(size,0,size),(size,0,-size))]
    return [(p[0],p[1],p[2]),(p[0],p[2],p[3])]

class PackingTests(unittest.TestCase):
    def assert_clear(self,items):
        for i,a in enumerate(items):
            for b in items[i+1:]:
                self.assertGreaterEqual(g.length(g.sub(a[0],b[0]))+1e-8,a[1]+b[1])
    def test_equal_radius_dense_and_regular(self):
        s=g.Surface(plane()); items,status=g.pack(s,[1],None,attempts=500)
        self.assert_clear(items)
        interior=[a for a in items if max(abs(a[0][0]),abs(a[0][2]))<17]
        contacts=[sum(abs(g.length(g.sub(a[0],b[0]))-2)<.01 for b in items if b is not a) for a in interior]
        self.assertGreater(sum(contacts)/len(contacts),5.4)
        self.assertGreater(len(items)*math.pi/s.area,.85)
        self.assertLess(len(items),550)
    def test_noise_and_scale_preserved(self):
        s=g.Surface(plane(10))
        noise=lambda hit:.5+.5*math.sin(hit[0][0]*.3)
        items,_=g.pack(s,[1],noise,feather=.5,attempts=700)
        self.assert_clear(items)
        self.assertGreater(len(items),100)
        for a in items:
            self.assertAlmostEqual(a[4],.5+noise((a[0],)),places=12)
            self.assertAlmostEqual(a[1],a[4],places=12)
        self.assertGreater(max(a[4] for a in items)-min(a[4] for a in items),.9)
    def test_black_white_endpoints(self):
        s=g.Surface(plane(5))
        for noise,expected in ((0,.5),(1,1.5)):
            items,_=g.pack(s,[2],lambda h:noise,feather=.5,attempts=100)
            self.assertTrue(items)
            self.assertTrue(all(a[4]==expected and a[1]==2*expected for a in items))
    def test_determinism_and_seed(self):
        s=g.Surface(plane(5)); a,_=g.pack(s,[1],None,attempts=50)
        b,_=g.pack(s,[1],None,attempts=50); c,_=g.pack(s,[1],None,seed=138,attempts=50)
        self.assertEqual(a,b); self.assertNotEqual(a,c)
    def test_disconnected_islands(self):
        s=g.Surface(plane(3)+plane(3,(40,0,0))); items,_=g.pack(s,[1],None,attempts=200)
        self.assertTrue(any(a[0][0]<5 for a in items)); self.assertTrue(any(a[0][0]>35 for a in items))
        self.assert_clear(items)
    def test_multiple_sources(self):
        s=g.Surface(plane(8)); items,_=g.pack(s,[.6,1.2],None,attempts=200)
        self.assertEqual(set(a[3] for a in items),{0,1}); self.assert_clear(items)
        self.assertTrue(all(a[1]==[.6,1.2][a[3]] for a in items))
    def test_curved_surface(self):
        t=[]
        for i in range(12):
            for j in range(24):
                def p(u,v): return (8*math.sin(u)*math.cos(v),8*math.cos(u),8*math.sin(u)*math.sin(v))
                a,b,c,d=[p(u,v) for u,v in ((i*math.pi/12,j*math.tau/24),((i+1)*math.pi/12,j*math.tau/24),((i+1)*math.pi/12,(j+1)*math.tau/24),(i*math.pi/12,(j+1)*math.tau/24))]
                t.extend(((a,b,c),(a,c,d)))
        s=g.Surface(t); items,_=g.pack(s,[1],lambda h:(h[0][1]+8)/16,feather=.4,attempts=200)
        self.assertGreater(len(items),120); self.assert_clear(items)
        for a in items:
            self.assertLess(g.length(g.sub(a[0],s.project(a[0])[0])),1e-8)
            self.assertAlmostEqual(g.length(a[2]),1.)
    def test_limit_and_cancel(self):
        s=g.Surface(plane()); items,status=g.pack(s,[1],None,max_count=10)
        self.assertEqual(len(items),10); self.assertIn('limit',status)
        def stop(): raise InterruptedError()
        items,status=g.pack(s,[1],None,check=stop)
        self.assertIn('Cancelled',status); self.assert_clear(items)
    def test_project_barycentrics_and_degenerate(self):
        s=g.Surface(plane()); p,n,i,b=s.project((2,5,3))
        self.assertAlmostEqual(p[1],0); self.assertAlmostEqual(sum(b),1.)
        self.assertEqual(s.project((2,5,3),max_distance=1),None)
        with self.assertRaises(ValueError): g.Surface([((0,0,0),)*3])
    def test_frame_right_handed(self):
        for n in ((0,1,0),(0,-1,0),(.6,.8,0),(0,0,1)):
            x,z=g.frame(n); self.assertAlmostEqual(g.dot(g.cross(x,n),z),1.)
    def test_size_zero_and_source_validation(self):
        s=g.Surface(plane())
        self.assertEqual(g.pack(s,[1],None,size=0)[0],[])
        with self.assertRaises(ValueError): g.pack(s,[0],None)

if __name__=='__main__': unittest.main()
