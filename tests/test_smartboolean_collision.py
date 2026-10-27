import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'smartBoolean'))
sys.path.insert(0,str(ROOT/'artifacts/smartBoolean'))
import smartboolean_collision as c
import smartboolean_cleanup as g
from check_crossings import count
BASE=ROOT/'artifacts/smartBoolean'
def read(name):return json.loads((BASE/(name+'.json')).read_text())

class CollisionTests(unittest.TestCase):
    def test_wrapped_seam_stays_within_front_face_boundary(self):
        raw,reference=read('outward-source'),read('outward-reference')
        seam={tuple(e) for e in raw['seam']}
        setup=c.plan(raw['points'],raw['polygons'],seam,raw['width'],raw['tolerance'])
        self.assertTrue(setup['spatial'])
        self.assertAlmostEqual(setup['reference'],reference['reference'])
        result=c.expand(reference['first'],reference['second'],setup,reference['polygons'])
        self.assertIsNotNone(result)
        baseline=read('outward-baseline')['points']
        self.assertGreater(sum(abs(p[2]-100)<1e-5 and p[0]<-100-1e-6 for p in baseline),0)
        front=[p for p in result if abs(p[2]-100)<1e-5]
        self.assertGreater(len(front),100)
        self.assertGreaterEqual(min(p[0] for p in front),-100-1e-6)
        self.assertTrue(all(len(v)==2 for v in g.edge_map(reference['polygons']).values()))
        full=limited=0
        for p,q,r in zip(reference['first'],reference['second'],result):
            delta=g.sub(q,p)
            if g.length(delta)<setup['tolerance']:
                self.assertEqual(tuple(p),tuple(r));continue
            expected=tuple(2*p[k]-q[k]+delta[k]*setup['width']/setup['reference'] for k in range(3))
            if g.length(g.sub(expected,r))<1e-6:full+=1
            else:limited+=1
        self.assertGreater(full,20);self.assertGreater(limited,0)

    def test_flower_inner_rows_follow_extrude_contour(self):
        raw,a,b=read('flower-raw'),read('flower-small'),read('flower-second')
        seam={tuple(e) for e in read('flower-seam')};points=raw['points']
        setup=c.plan(points,raw['polygons'],seam,10,1e-7)
        setup['reference']=.2
        result=c.expand(a['points'],b['points'],setup,a['polygons'])
        self.assertIsNotNone(result)
        # Match actual native flat endpoints to their original seam stations.
        endpoints={}
        for i,(p,q) in enumerate(zip(a['points'],b['points'])):
            if abs(p[1]-6.854367057369597)>1e-6 or g.length(g.sub(q,p))<1e-7:continue
            anchor=tuple(2*p[k]-q[k] for k in range(3))
            v=min(setup['velocity'],key=lambda v:g.length(g.sub(anchor,points[v])))
            if g.length(g.sub(anchor,points[v]))<1e-6:endpoints[v]=i
        checked=0
        for u,v in seam:
            edge=g.sub(points[v],points[u]);length=g.length(edge)
            speed=g.dot(g.sub(setup['velocity'][v],setup['velocity'][u]),edge)/length
            if speed>=-1e-10 or u not in endpoints or v not in endpoints:continue
            offset=g.sub(result[endpoints[v]],result[endpoints[u]])
            # A rounded offset must stay parallel to its source segment,
            # not become a diagonal along the pointwise curvature envelope.
            self.assertLess(g.length(g.cross(edge,offset))/(length*g.length(offset)),1e-6)
            self.assertGreater(g.dot(edge,offset),0)
            checked+=1
        self.assertGreater(checked,20)

    def test_flower_keeps_a_curved_contour_before_collapse(self):
        raw,a,b=read('flower-raw'),read('flower-small'),read('flower-second')
        seam={tuple(e) for e in read('flower-seam')};points=raw['points']
        setup=c.plan(points,raw['polygons'],seam,10,1e-7)
        self.assertEqual(max(setup['caps'].values()),10)
        for i,j in seam:
            edge=g.sub(points[j],points[i]);v=setup['velocity'];w=setup['caps']
            offset=tuple(edge[k]+v[j][k]*w[j]-v[i][k]*w[i] for k in range(3))
            self.assertGreaterEqual(g.dot(offset,edge)/g.dot(edge,edge),.14999)
        result=c.expand(a['points'],b['points'],setup,a['polygons'])
        self.assertIsNotNone(result)
        projected=dict(a,points=[(x,y-6.854367057369597+1,z) for x,y,z in result])
        self.assertEqual(count(projected),[])
        self.assertTrue(all(len(s)==2 for s in g.edge_map(a['polygons']).values()))

    def test_letter_e_local_limits_keep_other_sections_full_width(self):
        raw,a,b=read('E-raw'),read('E-small'),read('E-second')
        seam={tuple(e) for e in read('E-seam')}
        setup=c.plan(raw['points'],raw['polygons'],seam,10,1e-7)
        setup['reference']=.1
        result=c.expand(a['points'],b['points'],setup,a['polygons'])
        self.assertIsNotNone(result)
        for z in (0,20):
            projected=dict(a,points=[(x,Z-z+1,y) for x,y,Z in result])
            self.assertEqual(count(projected),[])
        self.assertTrue(all(len(sides)==2 for sides in g.edge_map(a['polygons']).values()))
        full=limited=0
        for p,q,r in zip(a['points'],b['points'],result):
            delta=g.sub(q,p)
            if g.length(delta)<1e-7:
                self.assertLess(g.length(g.sub(p,r)),1e-8)
                continue
            expected=tuple(2*p[k]-q[k]+delta[k]*100 for k in range(3))
            if g.length(g.sub(expected,r))<1e-5:full+=1
            else:limited+=1
        self.assertGreater(full,10)
        self.assertGreater(limited,10)
        # The e's terminal touches a slope/vertical-wall junction after only
        # 0.48 units. It must slide up that wall, not pinch the whole bevel.
        terminal=[]
        for p,q,r in zip(a['points'],b['points'],result):
            anchor=tuple(2*p[k]-q[k] for k in range(3))
            if abs(anchor[0]-45.79076840111678)<1e-6 and abs(anchor[1]-6.854367057369597)<1e-6:
                terminal.append(r)
        self.assertTrue(terminal)
        self.assertGreater(max(r[0]-45.79076840111678 for r in terminal if abs(r[1]-6.854367057369597)<1e-6),9)
        wall=max(terminal,key=lambda p:p[1])
        self.assertAlmostEqual(wall[0],46.3573038436443,places=5)
        self.assertGreater(wall[1],13)

    def test_curved_scene_local_cap_does_not_cap_whole_seam(self):
        raw=read('live-raw');seam={tuple(e) for e in read('asym-seam')}
        setup=c.plan(raw['points'],raw['polygons'],seam,8,1e-7)
        self.assertLess(min(setup['caps'].values()),2.064)
        self.assertEqual(max(setup['caps'].values()),8)

    def test_invalid_reference_correspondence_is_rejected(self):
        raw=read('E-raw');seam={tuple(e) for e in read('E-seam')}
        setup=c.plan(raw['points'],raw['polygons'],seam,10,1e-7)
        self.assertIsNone(c.expand([(0,0,0)],[],setup))

if __name__=='__main__':unittest.main()
