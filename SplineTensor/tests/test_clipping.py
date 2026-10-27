"""Regression checks for projected base-boundary clipping."""
import math
import json
import os
import sys
import unittest
from collections import Counter
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from st_clip import build_clipped
from st_geometry import area, on_segment, inside, cross, sub, dot
from st_union import unite_contours
BASE=[(-10,-10,0),(10,-10,0),(10,10,0),(-10,10,0)]
def circle(cx=9,cy=0,r=3,z=3):
    return [(cx+r*math.cos(i*math.tau/24),cy+r*math.sin(i*math.tau/24),z) for i in range(24)]

class ClippingTests(unittest.TestCase):
    def test_closed_off_short_concave_edges(self):
        with open(os.path.join(os.path.dirname(__file__),'current-scene-input.json')) as stream:
            data=json.load(stream)
        base=data[0]['loops'][0]
        contours=unite_contours(base,data[1]['loops'],(0,2.6580593082401265,0))
        v,f,e=build_clipped(base,contours,2,6,closed=False,quad_bands=True,return_edges=True,quality=True)
        quads=[face for face in f if len(face)==4]
        self.assertEqual(len(quads),97*7*2)
        self.assertEqual(len(e),97)
        self.assertTrue(all(abs(v[i][1]-2.6580593082401265)<1e-6 for edge in e for i in edge))
        # Matching inner/outer rings: equal counts at every profile height.
        levels=Counter(round(v[face[0]][1],6) for face in quads)
        self.assertTrue(all(n in (97,194) for n in levels.values()))
        counts=Counter(tuple(sorted((face[i-1],j))) for face in f for i,j in enumerate(face))
        directed=Counter((face[i-1],j) for face in f for i,j in enumerate(face))
        boundary=[(p[0],p[2]) for p in base]
        for (a,b),n in counts.items():
            self.assertLessEqual(n,2)
            if n==2:self.assertEqual(directed[a,b],directed[b,a])
            else:
                for t in (0.,.5,1.):
                    q=tuple(v[a][k]*(1-t)+v[b][k]*t for k in (0,2))
                    self.assertTrue(any(on_segment(boundary[i-1],p,q,1e-5) for i,p in enumerate(boundary)))
        self.assertAlmostEqual(abs(sum(area([(v[i][0],v[i][2]) for i in face]) for face in f)),abs(area(boundary)),places=6)

    def test_sampled_collinear_scene_boundary(self):
        with open(os.path.join(os.path.dirname(__file__),'current-scene-input.json')) as stream:
            data=json.load(stream)
        base=data[0]['loops'][0]
        contours=unite_contours(base,data[1]['loops'],(0,10.681203944857316,0))
        v,f,e=build_clipped(base,contours,3,closed=True,quad_bands=True,return_edges=True,quality=True)
        self.assertGreater(len(f),100)
        counts=Counter(tuple(sorted((face[i-1],j))) for face in f for i,j in enumerate(face))
        self.assertTrue(all(n<=2 for n in counts.values()))
        boundary=[(p[0],p[2]) for p in base]
        for (a,b),n in counts.items():
            if n==1:
                for t in (0.,.5,1.):
                    q=tuple(v[a][k]*(1-t)+v[b][k]*t for k in (0,2))
                    self.assertTrue(any(on_segment(boundary[i-1],p,q,1e-5) for i,p in enumerate(boundary)))
        projected=sum(area([(v[i][0],v[i][2]) for i in face]) for face in f)
        self.assertAlmostEqual(abs(projected),abs(area(boundary)),places=6)

    def test_reported_small_circle_closed_off(self):
        with open(os.path.join(os.path.dirname(__file__),'closed-off-input.json')) as stream:
            data=json.load(stream)
        united=unite_contours(data['base'],data['contours'],data['delta'])
        v,f,e=build_clipped(data['base'],united,data['width'],data['subdivisions'],closed=False,
                            quad_bands=True,return_edges=True,quality=True)
        self.assertGreater(len(f),100)
        counts=Counter(tuple(sorted((face[i-1],j))) for face in f for i,j in enumerate(face))
        self.assertTrue(all(n<=2 for n in counts.values()))
        # Base lies in XZ. All exposed edges must remain on its boundary.
        base=[(p[0],p[2]) for p in data['base']]
        for (a,b),n in counts.items():
            if n==1:
                for t in (0.,.5,1.):
                    q=tuple(v[a][k]*(1-t)+v[b][k]*t for k in (0,2))
                    self.assertTrue(any(on_segment(base[i-1],p,q,1e-5) for i,p in enumerate(base)))

    def check(self,base,contours,width=1,closed=True):
        v,f,e=build_clipped(base,contours,width,closed=closed,quad_bands=True,return_edges=True,quality=True)
        counts=Counter(tuple(sorted((face[i-1],j))) for face in f for i,j in enumerate(face))
        directed=Counter((face[i-1],j) for face in f for i,j in enumerate(face))
        self.assertTrue(all(n<=2 for n in counts.values()))
        for (a,b),n in counts.items():
            if n==2:self.assertEqual(directed[a,b],directed[b,a])
            else:self.assertTrue(any(on_segment(base[i-1],p,v[a],1e-6) and on_segment(base[i-1],p,v[b],1e-6) for i,p in enumerate(base)))
        for p in v:
            self.assertTrue(inside(p,base) or any(on_segment(base[i-1],b,p,1e-6) for i,b in enumerate(base)))
        self.assertAlmostEqual(sum(area([v[i] for i in face]) for face in f),abs(area(base)),places=6)
        for face in f:
            for j in range(1,len(face)-1):
                n=cross(sub(v[face[j]],v[face[0]]),sub(v[face[j+1]],v[face[0]]))
                self.assertGreater(dot(n,n),1e-18)
        self.assertTrue(all(tuple(sorted(edge)) in counts for edge in e))
        return v,f,e
    def test_crossing_circle_both_modes(self):
        for closed in (True,False):self.check(BASE,[circle()],closed=closed)
    def test_zero_width_and_negative_height(self):
        for h in (-3,3):self.check(BASE,[circle(z=h)],width=0)
    def test_only_band_reaches_base(self):
        v,f,e=self.check(BASE,[circle(cx=13.5)],width=1)
        self.assertTrue(any(p[2]>0 for p in v))
        self.assertEqual(e,[])
    def test_outside_does_not_refine_base(self):
        v,f,e=self.check(BASE,[circle(cx=30)])
        self.assertEqual((len(v),len(f),len(e)),(4,2,0))
    def test_enclosing_relief(self):
        c=[(-20,-20,3),(20,-20,3),(20,20,3),(-20,20,3)]
        v,f,e=self.check(BASE,[c])
        self.assertTrue(all(abs(p[2]-3)<1e-7 for p in v))
    def test_concave_base(self):
        base=[(-10,-10,0),(10,-10,0),(10,0,0),(0,0,0),(0,10,0),(-10,10,0)]
        for closed in (True,False):self.check(base,[circle(cx=0,cy=0,r=5)],closed=closed)
    def test_united_children_crossing(self):
        united=unite_contours(BASE,[circle(cx=9,cy=-1),circle(cx=9,cy=1)],(0,0,3))
        self.check(BASE,united,width=.2)
    def test_zero_height(self):
        v,f,e=self.check(BASE,[circle(z=0)])
        self.assertEqual((len(v),len(f),len(e)),(4,2,0))
    def test_rotated_plane(self):
        transform=lambda p:(p[2]+7,p[0]-2,p[1]+4)
        v,f,e=build_clipped(list(map(transform,BASE)),[list(map(transform,circle()))],1,return_edges=True)
        self.assertTrue(all(-12-1e-7<=p[1]<=8+1e-7 and -6-1e-7<=p[2]<=14+1e-7 for p in v))
        self.assertTrue(any(p[0]>7 for p in v))
    def test_coincident_base_and_relief(self):
        self.check(BASE,[[(x,y,3) for x,y,z in BASE]],width=1)

if __name__=='__main__':unittest.main(verbosity=2)
