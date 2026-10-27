"""Offline geometry regressions; no Cinema 4D runtime is used."""
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Metaspline'))
import metaspline_geometry as g

def polygon(points,closed=True):
    return ([g.line(a,b) for a,b in zip(points,points[1:]+points[:1])],closed)

def circle(x=0.,y=0.,r=50.):
    # Original conventional Bezier controls, not a sampled input fixture.
    k=.5522847498307936*r
    p=[(x+r,y,0.),(x,y+r,0.),(x-r,y,0.),(x,y-r,0.)]
    tangents=[(0,k,0),(-k,0,0),(0,-k,0),(k,0,0)]
    curves=[]
    for i in range(4):
        j=(i+1)%4
        curves.append((p[i],tuple(a+b for a,b in zip(p[i],tangents[i])),tuple(a-b for a,b in zip(p[j],tangents[j])),p[j]))
    return curves,True

def run(groups,c=20,f=40,s=0): return g.process(groups,c,f,s,g.WorkBudget(30),resolution=256)[0]
def points(paths): return [c[0] for curves,_ in paths for c in curves]

class GeometryTests(unittest.TestCase):
    def test_bezier_reconstruction_accuracy_and_sparse_knots(self):
        ring=[(50*math.cos(i*math.tau/600),50*math.sin(i*math.tau/600),0.) for i in range(600)]
        curves=g.fit_closed(ring,.1)
        self.assertLessEqual(len(curves),16)
        for i,c in enumerate(curves):
            previous=curves[i-1]
            incoming=g.sub(c[0],previous[2]); outgoing=g.sub(c[1],c[0])
            cosine=sum(a*b for a,b in zip(incoming,outgoing))/(g.length(incoming)*g.length(outgoing))
            self.assertGreater(cosine,.99999)
            for j in range(101): self.assertLess(abs(g.length(g.cubic(c,j/100))-50),.15)
    def test_liquid_output_has_sparse_curved_spans(self):
        result=run([[circle()],[circle(115)]])
        self.assertLess(sum(len(c) for c,_ in result),50)
        self.assertTrue(any(g.length(g.sub(c[1],g.line(c[0],c[3])[1]))>.1 for curves,_ in result for c in curves))
    def test_open_ignored(self):
        c=circle(); self.assertEqual(run([[(c[0],False)]]),[])
        self.assertEqual(run([[c],[(c[0],False)]]),[c])
    def test_single_exact_and_smooth(self):
        c=circle(); self.assertEqual(run([[c]],1000,1000),[c])
        result=run([[c]],s=.5)
        self.assertEqual(len(result),1); self.assertNotEqual(result,[c])
    def test_overlap_union_zero_collapse(self):
        self.assertEqual(len(run([[circle()],[circle(80)]],0,0)),1)
    def test_collapse_threshold(self):
        self.assertEqual(len(run([[circle()],[circle(115)]])),1)
        self.assertEqual(len(run([[circle()],[circle(125)]])),2)
    def test_fallow_attraction_without_welding(self):
        result=run([[circle()],[circle(125)]])
        left=min(result,key=lambda p:min(c[0][0] for c in p[0]))
        self.assertEqual(len(result),2)
        self.assertGreater(max(c[0][0] for c in left[0]),51.)
    def test_drop_rounding_preserves_area_and_reaches_circle(self):
        ring=[(100*math.cos(i*math.tau/200),25*math.sin(i*math.tau/200)) for i in range(200)]
        out=g.round_drop(ring,1.)
        self.assertAlmostEqual(abs(g.area(out))/abs(g.area(ring)),1.,places=7)
        radii=[g.length(p) for p in out]
        self.assertLess(max(radii)-min(radii),1e-6)
    def test_inverse_square_fallow_is_concentrated_near_collapse(self):
        near=-g.liquid(0,22,20,40)
        far=-g.liquid(0,50,20,40)
        self.assertGreater(near,far)
        self.assertGreater(g.liquid(11,11,20,40),0)
    def test_large_fallow_approaches_collapse_without_crossing(self):
        gap=40.
        previous=float('inf')
        for fallow in (25.,100.,1000.,100000.):
            midpoint=g.liquid(gap/2,gap/2,20.,fallow)
            self.assertGreater(midpoint,0.)
            self.assertLess(midpoint,previous)
            previous=midpoint
        self.assertLess(previous,.01)
    def test_fallow_100_has_visible_boundary_travel(self):
        gap=60.; collapse=20.; fallow=100.
        t=(gap-collapse)/fallow
        t=t*t*(3.-2.*t)
        weight=(1/(1+t)**2-.25)/.75
        weight=1.-(1.-weight)**2
        travel=gap*weight/2
        self.assertGreater(travel,10.)
        self.assertAlmostEqual(g.liquid(travel,gap-travel,collapse,fallow),0.,places=9)
    def test_large_fallow_unequal_outlines_remain_visible(self):
        groups=[[circle(0,30,35)],[circle(185,-25,90)]]
        result=run(groups,c=20,f=300,s=0)
        self.assertEqual(len(result),2)
        small=min(result,key=lambda path:max(p[0] for p in points([path])))
        sampled=[g.cubic(c,j/20) for c in small[0] for j in range(21)]
        self.assertGreater(max(p[0] for p in sampled),50.)
    def test_smooth_reuses_field_and_contours(self):
        from unittest.mock import patch
        cache={}; groups=[[circle()],[circle(115)]]
        g.process(groups,20,40,0,g.WorkBudget(30),cache=cache)
        with patch.object(g,'signed_field',side_effect=AssertionError('field rebuilt')),patch.object(g,'contours',side_effect=AssertionError('contours rebuilt')):
            result,status=g.process(groups,20,40,.5,g.WorkBudget(30),cache=cache)
        self.assertTrue(result)
    def test_outside_preserved(self):
        a,b=circle(),circle(180)
        self.assertEqual(run([[a],[b]]),[a,b])
    def test_hole_preserved(self):
        result=run([[circle(r=70),circle(r=25)],[circle(105)]],10,15)
        self.assertEqual(len(result),2)
        rings=[[(p[0],p[1]) for p in points([path])] for path in result]
        self.assertEqual(sum(g.inside((0,0),r) for r in rings),2)
    def test_closed_finite(self):
        result=run([[circle()],[circle(110,20)],[circle(45,90)]])
        for curves,closed in result:
            self.assertTrue(closed); self.assertEqual(curves[0][0],curves[-1][3])
        self.assertTrue(all(math.isfinite(v) for p in points(result) for v in p))
    def test_plane_xz(self):
        groups=[[( [tuple((p[0],p[2],p[1]) for p in c) for c in circle(x)[0]],True)] for x in (0,110)]
        result=run(groups)
        self.assertEqual(len(result),1)
        self.assertTrue(all(p[1]==0 for p in points(result)))
    def test_rotated_common_plane(self):
        def rotate(p): return (p[0],p[1]*.8,p[1]*.6)
        groups=[[([tuple(rotate(p) for p in c) for c in circle(x)[0]],True)] for x in (0,110)]
        result=run(groups)
        self.assertEqual(len(result),1)
        self.assertTrue(all(abs(p[1]*.6-p[2]*.8)<1e-8 for p in points(result)))
    def test_zero_collapse_still_attracts(self):
        self.assertLess(g.liquid(0,20,0,40),0)
        self.assertGreater(g.liquid(10,10,0,40),0)
    def test_nonplanar_retained(self):
        a=circle(); b=([tuple((p[0],p[1],10) for p in c) for c in circle(110)[0]],True)
        self.assertEqual(run([[a],[b]]),[a,b])
    def test_font_original_beziers(self):
        fixture=json.loads((ROOT/'tests/chamfer_text_outlines.json').read_text())['chamferPro']
        # All original font controls retained exactly with one child and Smooth=0.
        self.assertEqual(run([fixture]),[(c,True) for c,closed in fixture if closed])
        result=run([fixture],s=.15)
        self.assertEqual(len(result),len(fixture))
        # Multiple child letters exercise liquid joining of original font cubics.
        result=run([[fixture[0]],[fixture[1]]],5,10)
        self.assertTrue(result)
    def test_field_transition_continuous(self):
        for threshold in (20.,60.):
            a=g.liquid(threshold/2-1e-6,threshold/2-1e-6,20,40)
            b=g.liquid(threshold/2+1e-6,threshold/2+1e-6,20,40)
            self.assertLess(abs(a-b),1e-4)
    def test_work_limit_retains_closed_geometry(self):
        paths,status=g.process([[circle()],[circle(110)]],20,40,0,g.WorkBudget(-1))
        self.assertEqual(len(paths),2)

if __name__=='__main__': unittest.main()
