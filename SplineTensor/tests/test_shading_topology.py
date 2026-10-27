import unittest,sys,os,json,math
from collections import Counter
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_geometry import cross,sub,dot
from st_clip import build_clipped
from st_weld import quad_pairs

class ShadingTopologyTests(unittest.TestCase):
 def test_twisted_triangle_pair_stays_triangles(self):
  points=[(0,0,0),(2,0,0),(2,2,1),(0,1,1)]
  faces=[(0,1,2),(0,2,3)]
  self.assertEqual(quad_pairs(points,faces,1e-7),faces)
 def test_reported_scene_has_no_sliver_edges_or_twisted_quads(self):
  with open(os.path.join(os.path.dirname(__file__),'shading-input.json')) as stream:d=json.load(stream)
  values=d['profile']
  def profile(t):
   x=t*1000;i=min(999,int(x));return values[i]+(values[i+1]-values[i])*(x-i)
  for closed in (True,False):
   points,faces=build_clipped(d['base'],d['contours'],10,3,profile,closed=closed,quality=True,quad_bands=True)
   lengths=[]
   counts=Counter()
   for face in faces:
    v=[points[i] for i in face]
    lengths.extend(math.dist(v[i-1],p) for i,p in enumerate(v))
    for i,a in enumerate(face):counts[tuple(sorted((face[i-1],a)))]+=1
    if len(face)==4:
     normal=cross(sub(v[1],v[0]),sub(v[2],v[0]));length=math.sqrt(dot(normal,normal))
     self.assertLess(abs(dot(normal,sub(v[3],v[0])))/length,1e-6)
   self.assertGreater(min(lengths),.05)
   self.assertTrue(all(n in (1,2) for n in counts.values()))
if __name__=='__main__':unittest.main()
