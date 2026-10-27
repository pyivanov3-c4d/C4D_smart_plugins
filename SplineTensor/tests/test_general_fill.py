import unittest,sys,os,math
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_clip import build_clipped
from st_quality import improve

class GeneralFillTests(unittest.TestCase):
 def test_same_sampling_at_zero_positive_and_negative_height(self):
  results=[]
  for z in (0,3,-3):
   points=[(-10,-10,z),(10,-10,z),(10,10,z),(-10,10,z)]
   faces=improve(points,[(0,1,2),(0,2,3)],[0,1,2,3],[],1,1e-7)
   self.assertGreater(len(points),4)
   self.assertTrue(all(abs(p[2]-z)<1e-10 for p in points))
   results.append(([p[:2] for p in points],faces))
  self.assertEqual(results[0],results[1]);self.assertEqual(results[0],results[2])
 def test_closed_cap_gets_interior_points_regular_and_welded(self):
  base=[(-20,-20,0),(20,-20,0),(20,20,0),(-20,20,0)]
  for width in (1,4):
   for height in (3,-3):
    contours=[[(cx+3*math.cos(i*math.tau/24),3*math.sin(i*math.tau/24),height) for i in range(24)] for cx in (-4,4)]
    points,faces=build_clipped(base,contours,width,3,closed=True,quad_bands=True,quality=True)
    inner=[p for p in points if min(math.hypot(p[0]-cx,p[1]) for cx in (-4,4))<2.8]
    self.assertGreater(len(inner),0)
    self.assertTrue(all(abs(p[2]-height)<1e-8 for p in inner))
if __name__=='__main__':unittest.main()
