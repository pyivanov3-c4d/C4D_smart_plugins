import unittest,sys,os
from collections import Counter
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_geometry import triangulate

class FlatConnectionTests(unittest.TestCase):
 def check_region(self,points,outer,holes,z):
  boundary=set(outer)|{i for h in holes for i in h}
  constraints={tuple(sorted((loop[i-1],v))) for loop in [outer]+holes for i,v in enumerate(loop)}
  faces=triangulate(points,outer,holes,1e-7,quality_spacing=2)
  edges=Counter(tuple(sorted((f[i-1],v))) for f in faces for i,v in enumerate(f))
  for (a,b),count in edges.items():
   if a in boundary and b in boundary:self.assertIn((a,b),constraints)
   self.assertEqual(count,1 if (a,b) in constraints else 2)
  self.assertTrue(all(abs(p[2]-z)<1e-9 for p in points))
 def test_inner_cap_positive_and_negative_height(self):
  for z in (3,-3):
   self.check_region([(0,0,z),(10,0,z),(10,10,z),(0,10,z)],[0,1,2,3],[],z)
 def test_outer_flat_with_bevel_hole(self):
  p=[(0,0,0),(20,0,0),(20,20,0),(0,20,0),(5,5,0),(15,5,0),(15,15,0),(5,15,0)]
  self.check_region(p,[0,1,2,3],[[4,5,6,7]],0)
if __name__=='__main__':unittest.main()
