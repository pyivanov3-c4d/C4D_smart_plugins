import math
from pathlib import Path
import sys
import unittest
import json
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ChamferPro'))
import chamfer_geometry as g

def lines(p, closed=False):
    return [g.line(a,b) for a,b in zip(p,p[1:]+p[:1] if closed else p[1:])]

class RadiusTests(unittest.TestCase):
    def test_dense_rectangle_is_simplified_before_rounding(self):
        corners=[(0,0,0),(400,0,0),(400,400,0),(0,400,0)]
        p=[g.mix(a,b,k/1000) for a,b in zip(corners,corners[1:]+corners[:1]) for k in range(1000)]
        curves=lines(p,True)
        for c in (curves,curves[431:]+curves[:431]):
            simple,removed=g.simplify_straight_runs(c,True)
            self.assertEqual(len(simple),4)
            self.assertEqual(removed,3996)
            output,report=g.round_paths_fixed([(c,True)],20,.5,g.WorkBudget(2),True)
            self.assertEqual(report['rounded'],4)
            self.assertEqual(report['redundant'],3996)
            self.assertContinuous(output[0][0],True)
        reverse=lines([(0,0,0),(10,0,0),(0,0,0)],False)
        self.assertEqual(g.simplify_straight_runs(reverse,False)[0],reverse)

    def test_native_font_beziers_inner_cleanup(self):
        native=json.loads(Path(__file__).with_name('chamfer_native_x.json').read_text())
        self.assertEqual(sum(not g.straight_span(c) for c in native),3)
        for curves in (native,[list(reversed(c)) for c in reversed(native)]):
            for radius in (5,20,40,1e12):
                cleaned,count=g.clean_inner_corners(curves,True,radius,.5)
                apices={tuple(c[0]) for c in cleaned}-{tuple(c[0]) for c in curves}
                self.assertEqual(len(apices),2)
                _,report=g.round_path(cleaned,True,radius,.5,local_limit=True)
                rounds={p:r for p,r in zip(report['rounded_corners'],report['radii']) if p in apices}
                self.assertEqual(len(rounds),2)
                if radius>=20: self.assertTrue(all(r>=19.9 for r in rounds.values()))
                output,report=g.round_paths_fixed([(curves,True)],radius,.5,local_limit=True)
                self.assertGreater(report['cleaned'],0)
                self.assertEqual(report['skipped']+report['conflicts'],0)
                self.assertContinuous(output[0][0],True)

    def test_huge_request_fits_all_square_corners(self):
        c=lines([(0,0,0),(100,0,0),(100,100,0),(0,100,0)],True)
        result,report=g.round_path(c,True,1e15,.5,local_limit=True)
        self.assertEqual(report['rounded'],4)
        self.assertEqual(report['skipped']+report['conflicts'],0)
        for r in report['radii']: self.assertAlmostEqual(r,50,delta=.001)
        self.assertContinuous(result,True)

    def test_x_cleanup_uses_long_flanks_at_radius_20(self):
        data=json.loads(Path(__file__).with_name('chamfer_new_font.json').read_text())
        p=data['points'][129:146]; c=lines(p,True)
        cleaned,count=g.clean_inner_corners(c,True,20,.5)
        apices={tuple(a[0]) for a in cleaned}-{tuple(a[0]) for a in c}
        self.assertEqual(len(apices),2)
        _,report=g.round_path(cleaned,True,20,.5,local_limit=True)
        for pt,r in zip(report['rounded_corners'],report['radii']):
            if pt in apices: self.assertAlmostEqual(r,20,places=5)

    def test_sampled_text_huge_request_completes(self):
        data=json.loads(Path(__file__).with_name('chamfer_new_font.json').read_text())
        paths=[]; offset=0
        for s in data['segments']:
            p=data['points'][offset:offset+s['count']]; offset+=s['count']
            paths.append((lines(p,True),True))
        for radius in (20,1e12):
            output,report=g.round_paths_fixed(paths,radius,.5,g.WorkBudget(2),True)
            self.assertEqual(report['skipped']+report['conflicts'],0)
            self.assertGreater(report['rounded'],0)
            self.assertGreater(report['cleaned'],0)
            for curves,closed in output: self.assertContinuous(curves,closed)

    def test_live_x_inner_tips_with_extra_flank_points(self):
        data=json.loads(Path(__file__).with_name('chamfer_new_font.json').read_text())
        offset=sum(s['count'] for s in data['segments'][:3])
        points=data['points'][offset:offset+data['segments'][3]['count']]
        for p in (points,list(reversed(points))):
            curves=lines(p,True)
            cleaned,count=g.clean_inner_corners(curves,True,10,math.radians(10))
            self.assertGreaterEqual(count,2)
            old={tuple(c[0]) for c in curves}
            apices={tuple(c[0]) for c in cleaned}-old
            self.assertEqual(len(apices),2)
            _,report=g.round_path(cleaned,True,10,math.radians(10),local_limit=True)
            self.assertTrue(apices.issubset(set(report['rounded_corners'])))
            result,report=g.round_paths_fixed([(curves,True)],10,math.radians(10),local_limit=True)
            self.assertEqual(report['cleaned'],count)
            self.assertEqual(report['skipped']+report['conflicts'],0)
            self.assertEqual(report['effective_radius'],10)
            self.assertContinuous(result[0][0],True)
            cleaned,count=g.clean_inner_corners(curves,True,5,math.radians(30))
            self.assertEqual(count,2)
            _,report=g.round_path(cleaned,True,5,math.radians(30),local_limit=True)
            self.assertTrue(({tuple(c[0]) for c in cleaned}-old).issubset(set(report['rounded_corners'])))

    def test_local_limits_round_crowded_rectangle(self):
        curves=lines([(0,0,0),(100,0,0),(100,20,0),(0,20,0)],True)
        result,report=g.round_path(curves,True,30,.5,local_limit=True)
        self.assertEqual(report['rounded'],4)
        self.assertEqual(report['limited'],4)
        self.assertEqual(report['skipped']+report['conflicts'],0)
        for radius in report['radii']: self.assertAlmostEqual(radius,10,delta=.002)
        self.assertContinuous(result,True)

    def test_inner_flat_cleanup_and_winding(self):
        pts=[(0,0,0),(100,0,0),(100,100,0),(70,100,0),
             (51,61,0),(49,61,0),(30,100,0),(0,100,0)]
        for p in (pts,list(reversed(pts))):
            c=lines(p,True)
            cleaned,count=g.clean_inner_corners(c,True,5,0)
            self.assertEqual(count,1)
            self.assertEqual(len(cleaned),len(c)-1)
            self.assertContinuous(cleaned,True)
            result,report=g.round_paths_fixed([(c,True)],5,0)
            self.assertEqual(report['cleaned'],1)
            self.assertEqual(report['skipped']+report['conflicts'],0)
            self.assertContinuous(result[0][0],True)
            self.assertEqual(g.clean_inner_corners(c,True,.1,0)[1],0)
            self.assertEqual(g.clean_inner_corners(c,False,5,0)[1],0)
        convex=lines([(0,0,0),(100,0,0),(100,99,0),(99,100,0),(0,100,0)],True)
        self.assertEqual(g.clean_inner_corners(convex,True,5,0)[1],0)
        # An unrelated tiny convex bevel must not cancel a successful inner cleanup.
        p=[(0,0,0),(99,0,0),(100,1,0)]+pts[2:]
        _,report=g.round_paths_fixed([(lines(p,True),True)],5,0)
        self.assertEqual(report['cleaned'],1)
        self.assertGreater(report['skipped']+report['conflicts'],0)

    def test_fixed_radius_retains_impossible_corners_without_shrinking_others(self):
        wide=lines([(0,0,0),(400,0,0),(400,400,0),(0,400,0)],True)
        tiny=lines([(500,0,0),(501,0,0),(501,1,0),(500,1,0)],True)
        output,report=g.round_paths_fixed([(wide,True),(tiny,True)],100,.5)
        expected,_=g.round_path(wide,True,100,.5)
        self.assertEqual(output,[(expected,True),(tiny,True)])
        self.assertEqual(report['effective_radius'],100)
        self.assertEqual(report['rounded'],4)
        self.assertEqual(report['skipped']+report['conflicts'],4)

    def test_smaller_corner_opening_and_reverse_direction(self):
        for opening in (30,60,90,120,150):
            for sign in (-1,1):
                turn=math.radians(180-opening)*sign
                c=lines([(-1000,0,0),(0,0,0),
                         (1000*math.cos(turn),1000*math.sin(turn),0)])
                for curves in (c,[tuple(reversed(span)) for span in reversed(c)]):
                    measured=g.corner_angle(g.tangent(curves[0],1),g.tangent(curves[1],0))
                    self.assertAlmostEqual(math.degrees(measured),opening)
                    for minimum,expected in ((1,1),(opening-1,1),(opening,1),(opening+1,0)):
                        _,report=g.round_path(curves,False,1,math.radians(minimum))
                        self.assertEqual(report['rounded'],expected)

    def assertCircle(self, curves, center, radius):
        for c in curves:
            for i in range(101):
                self.assertLess(abs(g.length(g.sub(g.point(c,i/100),center))-radius),radius*5e-6)

    def assertContinuous(self, curves, closed=False):
        for a,b in zip(curves,curves[1:]+curves[:1] if closed else curves[1:]):
            self.assertLess(g.length(g.sub(a[3],b[0])),1e-5)

    def test_snag_points(self):
        c=lines([(-100,0,0),(-2,0,0),(-.1,0,0),(0,0,0),(0,.2,0),(0,3,0),(0,100,0)])
        r,s=g.round_path(c,False,20,.5)
        self.assertEqual(s['rounded'],1)
        self.assertAlmostEqual(r[0][3][0],-20)
        self.assertAlmostEqual(r[-1][0][1],20)
        self.assertCircle(r[1:-1],(-20,20,0),20)
        self.assertContinuous(r)

    def test_angles_and_turn_directions(self):
        for degrees in (15,30,45,60,90,120,150):
            for sign in (-1,1):
                t=math.radians(degrees)*sign
                c=lines([(-1000,0,0),(0,0,0),(1000*math.cos(t),1000*math.sin(t),0)])
                r,s=g.round_path(c,False,10,.01)
                self.assertEqual(s['rounded'],1,(degrees,sign,s))
                self.assertCircle(r[1:-1],(-10*math.tan(abs(t)/2),sign*10,0),10)
                self.assertContinuous(r)

    def test_closed_seam_and_winding(self):
        p=[(0,0,0),(100,0,0),(100,100,0),(0,100,0)]
        for q in (p,list(reversed(p))):
            r,s=g.round_path(lines(q,True),True,10,.5)
            self.assertEqual(s['rounded'],4)
            self.assertContinuous(r,True)

    def test_conflicts_do_not_shrink(self):
        c=lines([(0,0,0),(100,0,0),(100,20,0),(0,20,0)],True)
        r,s=g.round_path(c,True,15,.5)
        self.assertEqual(s['rounded'],0)
        self.assertEqual(s['conflicts'],4)
        self.assertEqual(r,c)

    def test_exact_fit(self):
        c=lines([(0,0,0),(100,0,0),(100,20,0),(0,20,0)],True)
        r,s=g.round_path(c,True,10,.5)
        self.assertEqual(s['rounded'],4)
        self.assertContinuous(r,True)

    def test_threshold_and_zero(self):
        c=lines([(-100,0,0),(0,0,0),(0,100,0)])
        self.assertEqual(g.round_path(c,False,0,0)[0],c)
        self.assertEqual(g.round_path(c,False,10,math.radians(100))[0],c)
        self.assertEqual(g.round_path(c,False,10,math.pi/2)[1]['rounded'],1)

    def test_curved_sides_preserved(self):
        a=((-100,0,0),(-60,0,0),(-30,0,0),(0,0,0))
        b=((0,0,0),(0,30,0),(10,70,0),(30,100,0))
        r,s=g.round_path([a,b],False,10,.5)
        self.assertEqual(s['rounded'],1)
        self.assertContinuous(r)
        f=g.solve_fillet(g.Path([a,b],False),1,0,2,10,math.pi/2)
        self.assertCircle(f.arcs,f.center,10)
        self.assertEqual(r[0],g.trim(a,0,f.lo))
        self.assertEqual(r[-1],g.trim(b,f.hi-1,1))

    def test_smooth_curve_unchanged(self):
        c=((0,0,0),(0,50,0),(50,100,0),(100,100,0))
        a,b=g.split(c,.4)
        r,s=g.round_path([a,b],False,10,.01)
        self.assertEqual(r,[a,b])
        self.assertEqual(s['rounded'],0)

    def test_3d_corner(self):
        r,s=g.round_path(lines([(-100,0,0),(0,0,0),(0,60,80)]),False,10,.5)
        self.assertEqual(s['rounded'],1)
        self.assertCircle(r[1:-1],(-10,6,8),10)

    def test_nonplanar_curve_preserved(self):
        a=g.line((-100,0,0),(0,0,0))
        b=((0,0,0),(0,30,0),(0,70,20),(0,100,0))
        r,s=g.round_path([a,b],False,10,.5)
        self.assertEqual(s['rounded'],0)
        self.assertEqual(r,[a,b])

    def test_small_feature_preserved(self):
        c=lines([(-100,0,0),(-2,0,0),(0,2,0),(0,100,0)])
        r,s=g.round_path(c,False,20,.5)
        self.assertEqual(s['rounded'],0)
        self.assertEqual(r,c)

    def test_subdivision_invariance(self):
        a,b=lines([(-100,0,0),(0,0,0),(0,100,0)])
        r,s=g.round_path(list(g.split(a,.96))+list(g.split(b,.03)),False,20,.5)
        self.assertEqual(s['rounded'],1)
        self.assertCircle(r[1:-1],(-20,20,0),20)

    def test_join_reversed_and_close(self):
        a=lines([(0,0,0),(100,0,0)])
        b=lines([(100,100,0),(100,0,0)])
        p=g.connect_paths([(a,False),(b,False)])
        self.assertEqual(len(p),1)
        self.assertEqual(p[0][0][-1][3],(100,100,0))
        self.assertEqual(g.round_path(*p[0],10,.5)[1]['rounded'],1)
        c=lines([(100,100,0),(0,0,0)])
        p=g.connect_paths([(a,False),(b,False),(c,False)])
        self.assertEqual(len(p),1)
        self.assertTrue(p[0][1])

    def test_branch_junction(self):
        p=[(lines([(0,0,0),q]),False) for q in ((100,0,0),(0,100,0),(-100,0,0))]
        self.assertEqual(len(g.connect_paths(p)),3)

    def test_endpoints_preserved(self):
        c=lines([(-100,0,0),(0,0,0),(0,100,0)])
        r,_=g.round_path(c,False,10,.5)
        self.assertEqual(r[0][0],c[0][0])
        self.assertEqual(r[-1][3],c[-1][3])

    def test_reversal(self):
        c=lines([(-100,0,0),(0,0,0),(-100,0,0)])
        r,s=g.round_path(c,False,10,.5)
        self.assertEqual(r,c)
        self.assertEqual(s['skipped'],0)

    def test_text_outlines_complete_within_budget(self):
        fixture = Path(__file__).with_name('chamfer_text_outlines.json')
        cases = json.loads(fixture.read_text(encoding='utf-8'))
        for text, paths in cases.items():
            for radius in (1.,5.,10.):
                budget = g.WorkBudget(2.)
                start = time.monotonic()
                rounded = 0
                for curves, closed in paths:
                    result, report = g.round_path(curves,closed,radius,math.radians(30),check=budget)
                    self.assertContinuous(result,closed)
                    rounded += report['rounded']
                elapsed = time.monotonic()-start
                self.assertLess(elapsed,2.,text)
                self.assertGreater(rounded,0,text)
                print('Text {!r}: R={}, {:.3f}s, {} rounded'.format(text,radius,elapsed,rounded))

    def test_expired_budget_aborts_dense_geometry(self):
        budget = g.WorkBudget(-1.)
        curves = lines([(i,0,0) for i in range(10000)])
        with self.assertRaises(g.EvaluationStopped):
            g.round_path(curves,False,20,.5,check=budget)

    def test_user_cancellation(self):
        budget = g.WorkBudget(60.,cancelled=lambda: True)
        with self.assertRaises(g.EvaluationStopped):
            for _ in range(64): budget()

    def test_shared_radius_across_different_contours(self):
        wide=lines([(0,0,0),(100,0,0),(100,100,0),(0,100,0)],True)
        narrow=lines([(200,0,0),(300,0,0),(300,20,0),(200,20,0)],True)
        paths=[(wide,True),(narrow,True)]
        result, report=g.round_paths_uniform(paths,30,.5)
        self.assertAlmostEqual(report['effective_radius'],10,delta=.001)
        self.assertEqual(report['rounded'],8)
        self.assertEqual(report['skipped']+report['conflicts'],0)
        for (original,closed),(actual,_) in zip(paths,result):
            expected,_=g.round_path(original,closed,report['effective_radius'],.5)
            self.assertEqual(actual,expected)
            self.assertContinuous(actual,True)

    def test_shared_radius_preserves_smaller_request(self):
        p=[(lines([(0,0,0),(100,0,0),(100,20,0),(0,20,0)],True),True)]
        _, report=g.round_paths_uniform(p,4,.5)
        self.assertEqual(report['effective_radius'],4)
        self.assertEqual(report['rounded'],4)

    def test_uniform_text_has_no_missed_selected_corners(self):
        cases=json.loads(Path(__file__).with_name('chamfer_text_outlines.json').read_text())
        for text in ('chamferPro','TEXT SPLINE'):
            paths=cases[text]
            result, report=g.round_paths_uniform(paths,15.3,.5,check=g.WorkBudget(2.))
            self.assertGreater(report['effective_radius'],0)
            self.assertLess(report['effective_radius'],15.3)
            selected=0
            for curves, closed in paths:
                selected+=sum(g.corner_angle(g.tangent(curves[i-1],1),g.tangent(c,0))>.5
                              and g.angle(g.tangent(curves[i-1],1),g.tangent(c,0))>math.radians(.05)
                              for i,c in enumerate(curves))
            self.assertEqual(report['rounded'],selected)
            for curves,closed in result: self.assertContinuous(curves,closed)

if __name__=='__main__': unittest.main()
