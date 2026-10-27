import unittest,sys,os,json
from collections import Counter
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_weld import connect_band_vertices
from st_geometry import dot,sub,cross,unit
from st_clip import build_clipped

class BandConnectionTests(unittest.TestCase):
 def test_flat_ear_connects_to_opposite_layer(self):
  p=[(0,0,1),(2,0,1),(2,2,1),(0,2,0)]
  f=[(0,1,2),(0,2,3)];b={(0,1),(1,2),(2,3),(0,3)}
  result=connect_band_vertices(p,f,b,1e-7)
  edges={tuple(sorted((face[i-1],v))) for face in result for i,v in enumerate(face)}
  self.assertIn((1,3),edges);self.assertNotIn((0,2),edges)
  self.assertTrue(b<=edges)
 def test_constraint_is_never_flipped(self):
  p=[(0,0,1),(2,0,1),(2,2,1),(0,2,0)]
  f=[(0,1,2),(0,2,3)]
  self.assertEqual(connect_band_vertices(p,f,{(0,2)},1e-7),f)
 def test_reported_scene_has_no_flat_band_ears(self):
  with open(os.path.join(os.path.dirname(__file__),'join-input.json')) as stream:d=json.load(stream)
  values=d['profile'];base=d['base'];o=base[0]
  n=unit(tuple(sum(cross(sub(base[i-1],o),sub(q,o))[k] for i,q in enumerate(base)) for k in range(3)))
  def profile(t):
   x=t*1000;i=min(int(x),999);return values[i]+(values[i+1]-values[i])*(x-i)
  for closed in (True,False):
   p,f=build_clipped(base,d['contours'],20,3,profile,closed=closed,quality=True,quad_bands=True)
   z=[dot(sub(q,o),n) for q in p];lo,hi=min(z),max(z)
   for face in f:
    if len(face)==3 and max(z[i] for i in face)-min(z[i] for i in face)<1e-6:
     self.assertFalse(min(z[i] for i in face)>lo+1e-5 and max(z[i] for i in face)<hi-1e-5)
   edges=Counter(tuple(sorted((face[i-1],a))) for face in f for i,a in enumerate(face))
   self.assertTrue(all(count in (1,2) for count in edges.values()))
if __name__=='__main__':unittest.main()
