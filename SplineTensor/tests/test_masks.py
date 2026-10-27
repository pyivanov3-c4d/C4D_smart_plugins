import unittest,sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_union import unite_contours
from st_geometry import area,inside
from st_clip import build_clipped
B=[(-20,-20,0),(20,-20,0),(20,20,0),(-20,20,0)]
def square(r,z=3,cx=0):return [(cx-r,-r,z),(cx+r,-r,z),(cx+r,r,z),(cx-r,r,z)]
def filled(loops,p):return sum(1 if area(loop)>0 else -1 for loop in loops if inside(p,loop))>0
class MaskTests(unittest.TestCase):
 def test_nested_holes_and_island_order_independent(self):
  for inputs in ([square(12),square(6),square(2)],[list(reversed(square(2))),square(12),square(6)]):
   r=unite_contours(B,inputs,nested_masks=True)
   self.assertTrue(filled(r,(10,0)));self.assertFalse(filled(r,(4,0)));self.assertTrue(filled(r,(0,0)))
 def test_overlap_masks_out(self):
  r=unite_contours(B,[square(5,cx=-2),square(5,cx=2)],nested_masks=True)
  self.assertFalse(filled(r,(0,0)));self.assertTrue(filled(r,(-6,0)));self.assertTrue(filled(r,(6,0)))
 def test_hole_winding_independent_and_base_height(self):
  r=unite_contours(B,[square(12),list(reversed(square(5)))],nested_masks=True)
  self.assertEqual(sum(area(loop)<0 for loop in r),1)
  for closed in (True,False):
   p,f=build_clipped(B,r,1,3,closed=closed,quality=True,quad_bands=True)
   center=[q for q in p if abs(q[0])<3 and abs(q[1])<3]
   self.assertTrue(center);self.assertTrue(all(abs(q[2])<1e-8 for q in center))
 def test_identical_shapes_cancel(self):
  self.assertEqual(unite_contours(B,[square(5),square(5)],nested_masks=True),[])
 def test_three_overlaps_fill_again(self):
  r=unite_contours(B,[square(5,cx=-2),square(5,cx=2),square(4)],nested_masks=True)
  self.assertTrue(filled(r,(0,0)))
 def test_crossing_circles_generate_both_modes(self):
  import math
  inputs=[[(cx+5*math.cos(i*math.tau/32),5*math.sin(i*math.tau/32),3) for i in range(32)] for cx in (-2,2)]
  r=unite_contours(B,inputs,nested_masks=True)
  self.assertFalse(filled(r,(0,0)))
  for closed in (True,False):
   p,f=build_clipped(B,r,2,3,closed=closed,quality=True,quad_bands=True)
   self.assertTrue(f)
 def test_zero_width_hole(self):
  r=unite_contours(B,[square(12),square(5)],nested_masks=True)
  p,f=build_clipped(B,r,0,3,quality=True,quad_bands=True)
  self.assertTrue(f)
if __name__=='__main__':unittest.main()
