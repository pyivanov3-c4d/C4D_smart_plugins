import unittest,random,sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_spatial import segment_pairs
class SpatialTests(unittest.TestCase):
 def test_matches_exhaustive_box_search(self):
  rng=random.Random(123)
  segments=[((rng.uniform(-10,10),rng.uniform(-10,10)),(rng.uniform(-10,10),rng.uniform(-10,10))) for _ in range(150)]
  for eps in (0,1e-8,.1):
   expected=[]
   for i,(a,b) in enumerate(segments):
    for j in range(i+1,len(segments)):
     c,d=segments[j]
     if max(a[0],b[0])+eps<min(c[0],d[0]) or max(c[0],d[0])+eps<min(a[0],b[0]) or max(a[1],b[1])+eps<min(c[1],d[1]) or max(c[1],d[1])+eps<min(a[1],b[1]):continue
     expected.append((i,j))
   self.assertEqual(segment_pairs(segments,eps),expected)
 def test_touching_vertical_and_degenerate_bounds(self):
  segments=[((0,0),(0,1)),((0,1),(1,1)),((0,0),(0,0)),((2,2),(3,3))]
  self.assertEqual(segment_pairs(segments,1e-9),[(0,1),(0,2)])
if __name__=='__main__':unittest.main()
