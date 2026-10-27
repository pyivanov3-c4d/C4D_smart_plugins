import unittest,sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_density import current_density,density_scope
from st_quality import surface_spacing,improve
from st_clip import build_clipped
class DensityTests(unittest.TestCase):
 def test_scope_restores_after_exception(self):
  try:
   with density_scope(3):
    self.assertEqual(current_density(),3);raise RuntimeError()
  except RuntimeError:pass
  self.assertEqual(current_density(),1)
 def test_flat_area_density_increases(self):
  counts=[]
  for density in (1,2):
   with density_scope(density):
    p=[(0,0,3),(100,0,3),(100,100,3),(0,100,3)]
    faces=improve(p,[(0,1,2),(0,2,3)],[0,1,2,3],[],surface_spacing(p),1e-7)
    counts.append(len(p))
    self.assertTrue(all(abs(q[2]-3)<1e-8 for q in p))
  self.assertGreater(counts[1],counts[0]*1.7)
 def test_symmetric_grid_shared_edges_remain_welded(self):
  import json
  with open(os.path.join(os.path.dirname(__file__),'density-failure.json')) as stream:data=json.load(stream)
  p,f=build_clipped(data['base'],data['contours'],2,3,quality=True,quad_bands=True)
  self.assertTrue(f)
 def test_default_density_preserves_mesh(self):
  b=[(-20,-20,0),(20,-20,0),(20,20,0),(-20,20,0)]
  c=[[(-5,-5,3),(5,-5,3),(5,5,3),(-5,5,3)]]
  self.assertEqual(build_clipped(b,c,2,3,quality=True),build_clipped(b,c,2,3,quality=True,density=1))
if __name__=='__main__':unittest.main()
