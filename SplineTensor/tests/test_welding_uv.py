import unittest, sys, os, math, json
from collections import Counter
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_clip import build_clipped
from st_uv import planar_uvs
from st_union import unite_contours

BASE=[(-20,-20,0),(20,-20,0),(20,20,0),(-20,20,0)]


class WeldingUVTests(unittest.TestCase):
    def check_surface(self,base,contours,width,closed):
        p,f=build_clipped(base,contours,width,3,closed=closed,
                          quad_bands=True,quality=True)
        self.assertTrue(f)
        edges=Counter(tuple(sorted((face[i-1],idx))) for face in f for i,idx in enumerate(face))
        self.assertTrue(all(n in (1,2) for n in edges.values()))
        uv=planar_uvs(base,p)
        self.assertTrue(all(0<=v<=1 for q in uv for v in q[:2]))
        self.assertTrue(any(len(face)==4 for face in f))
        return p,f

    def test_growing_islands_and_collapsing_centers(self):
        circles=[[(cx+3*math.cos(i*math.tau/24),3*math.sin(i*math.tau/24),3)
                  for i in range(24)] for cx in (-4,4)]
        for closed in (True,False):
            for width in (1,2,4):
                with self.subTest(closed=closed,width=width):
                    self.check_surface(BASE,circles,width,closed)

    def test_exact_diagonal_contact(self):
        shapes=[[(-5,-5,3),(-1,-5,3),(-1,-1,3),(-5,-1,3)],
                [(1,1,3),(5,1,3),(5,5,3),(1,5,3)]]
        for closed in (True,False):
            self.check_surface(BASE,shapes,1,closed)

    def test_scene_width_ten(self):
        with open(os.path.join(os.path.dirname(__file__),'scene-20261020-input.json')) as stream:
            data=json.load(stream)
        base=data[0]['loops'][0]
        loops=unite_contours(base,data[1]['loops'])
        for closed in (True,False):
            self.check_surface(base,loops,10,closed)

    def test_uv_bounds_and_height_independence(self):
        # Rotated and translated rectangular base; normal is world X.
        base=[(7,2,3),(7,12,3),(7,12,23),(7,2,23)]
        self.assertEqual(planar_uvs(base,base),
                         [(0,0,0),(1,0,0),(1,1,0),(0,1,0)])
        self.assertEqual(planar_uvs(base,[(7,7,13),(40,7,13),(-8,7,13)]),
                         [(.5,.5,0)]*3)


if __name__=='__main__':unittest.main()
