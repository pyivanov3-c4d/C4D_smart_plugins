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
    def test_viscosity_controls_neck_growth_and_reuses_attraction(self):
        import metaspline_vector as vector
        from unittest.mock import patch
        groups=[[circle(r=200)],[circle(370.5,r=132.4)]]
        cache={};widths=[]
        for viscosity in (0.,.25,1.):
            paths,_=g.process(groups,50,100,.15,g.WorkBudget(30),cache=cache,viscosity=viscosity)
            self.assertEqual(len(paths),1)
            ring=[g.cubic(c,j/80) for c in paths[0][0] for j in range(80)]
            x=(200+370.5-132.4)*.5;hits=[]
            for a,b in zip(ring,ring[1:]+ring[:1]):
                if (a[0]>x)!=(b[0]>x):hits.append(a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0]))
            self.assertTrue(hits)
            widths.append(max(hits)-min(hits))
        self.assertGreater(widths[0],widths[1]*1.5)
        self.assertGreater(widths[1],widths[2]*1.5)
        with patch.object(vector,'attract',side_effect=AssertionError('Attraction rebuilt')):
            g.process(groups,50,100,.15,g.WorkBudget(30),cache=cache,viscosity=.6)
    def test_viscosity_preserves_contact_threshold(self):
        for viscosity in (0.,.25,1.):
            paths,_=g.process([[circle()],[circle(120.1)]],20,60,0,g.WorkBudget(30),viscosity=viscosity)
            self.assertEqual(len(paths),2)
    def test_neck_starts_tiny_at_default_smooth(self):
        for gap in (19.99,19.9,19.5):
            paths=run([[circle(r=45)],[circle(65+gap,r=20)]],c=20,f=60,s=.15)
            self.assertEqual(len(paths),1)
            self.assertLess(len(paths[0][0]),80)
            ring=[g.cubic(c,j/40) for c in paths[0][0] for j in range(40)]
            x=45+gap*.5;hits=[]
            for a,b in zip(ring,ring[1:]+ring[:1]):
                if (a[0]>x)!=(b[0]>x):hits.append(a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0]))
            self.assertTrue(hits)
            self.assertLess(max(hits)-min(hits),.7)
    def test_tiny_smooth_does_not_shift_nonuniform_contour(self):
        angles=[math.pi*i/100 for i in range(100)]+[math.pi+math.pi*i/10 for i in range(10)]
        ring=[(50*math.cos(t),50*math.sin(t)) for t in angles]
        result=g.round_drop(ring,1e-8)
        for axis in (0,1):
            self.assertLess(abs(min(p[axis] for p in result)-min(p[axis] for p in ring)),.1)
            self.assertLess(abs(max(p[axis] for p in result)-max(p[axis] for p in ring)),.1)
    def test_bulge_thin_neck_thick_neck_sequence(self):
        widths=[];areas=[]
        for gap in (20.1,19.9,15.,8.,2.):
            paths=run([[circle(r=45)],[circle(65+gap,r=20)]],c=20,f=60,s=0)
            self.assertEqual(len(paths),2 if gap>20 else 1)
            hits=[];area=0.;x=45+gap*.5
            for curves,_ in paths:
                ring=[g.cubic(c,j/40) for c in curves for j in range(40)]
                area+=abs(g.area([p[:2] for p in ring]))
                for a,b in zip(ring,ring[1:]+ring[:1]):
                    if (a[0]>x)!=(b[0]>x):hits.append(a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0]))
            widths.append(max(hits)-min(hits) if hits else 0.);areas.append(area)
        self.assertEqual(widths[0],0.)
        self.assertLess(widths[1],3.)
        self.assertTrue(all(a<b for a,b in zip(widths[1:],widths[2:])))
        self.assertLess(abs(areas[1]-areas[0])/areas[0],.01)
    def test_vector_stages_and_cache(self):
        import metaspline_vector as vector
        from unittest.mock import patch
        cache={};stages=[];groups=[[circle()],[circle(115)],[circle(245)]]
        result,status=g.process(groups,20,60,0,g.WorkBudget(30),cache=cache,progress=lambda s,p:stages.append(s))
        self.assertEqual(len(result),2)
        union=next(i for i,s in enumerate(stages) if 'combining overlapping' in s)
        bridge=next(i for i,s in enumerate(stages) if s.startswith('Collapse'))
        fallow=next(i for i,s in enumerate(stages) if s.startswith('Fallow'))
        self.assertLess(union,fallow);self.assertLess(fallow,bridge)
        stages.clear()
        g.process(groups,20,60,0,g.WorkBudget(30),cache=cache,progress=lambda *s:stages.append(s))
        self.assertEqual(stages,[])
        with patch.object(vector.Clip,'union',side_effect=AssertionError('Union rebuilt')),patch.object(vector,'attract',side_effect=AssertionError('Fallow rebuilt')):
            smoothed,_=g.process(groups,20,60,.5,g.WorkBudget(30),cache=cache)
        self.assertEqual(len(smoothed),2)
    def test_zero_collapse_attraction_and_no_weld(self):
        result=run([[circle()],[circle(120)]],c=0,f=100)
        self.assertEqual(len(result),2)
        left=min(result,key=lambda path:min(p[0] for p in points([path])))
        samples=[g.cubic(c,j/20) for c in left[0] for j in range(21)]
        self.assertGreater(max(p[0] for p in samples),54.)
    def test_union_then_bridge_three_children(self):
        result,status=g.process([[circle()],[circle(80)],[circle(195)]],20,0,0,g.WorkBudget(30))
        self.assertEqual(len(result),1)
        self.assertIn('1 bridges',status)
    def test_work_budget_interrupts(self):
        with self.assertRaises(g.EvaluationStopped):
            g.process([[circle()],[circle(110)]],20,40,0,g.WorkBudget(-1))
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
    def test_large_fallow_unequal_outlines_remain_visible(self):
        groups=[[circle(0,30,35)],[circle(185,-25,90)]]
        result=run(groups,c=20,f=300,s=0)
        self.assertEqual(len(result),2)
        small=min(result,key=lambda path:max(p[0] for p in points([path])))
        sampled=[g.cubic(c,j/20) for c in small[0] for j in range(21)]
        self.assertGreater(max(p[0] for p in sampled),50.)
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

if __name__=='__main__': unittest.main()
