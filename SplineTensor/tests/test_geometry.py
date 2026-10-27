import math
import os
import sys
import unittest
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from st_geometry import build, build_many, GeometryError, cross, sub, dot
from st_union import union_loops, unite_contours

BASE = [(-10,-10,0), (10,-10,0), (10,10,0), (-10,10,0)]
INNER = [(-2,-2,3), (2,-2,3), (2,2,3), (-2,2,3)]


class GeometryTests(unittest.TestCase):
    def check_mesh(self, vertices, faces, boundary_count=4):
        edges = Counter(tuple(sorted((f[i-1], f[i]))) for f in faces for i in range(3))
        self.assertEqual(sum(n == 1 for n in edges.values()), boundary_count)
        self.assertTrue(all(n in (1, 2) for n in edges.values()))
        directed = Counter((f[i-1], f[i]) for f in faces for i in range(3))
        for (a,b), n in edges.items():
            if n == 2:
                self.assertEqual(directed[(a,b)], 1)
                self.assertEqual(directed[(b,a)], 1)
        # Disk Euler characteristic, no zero-area spatial faces.
        self.assertEqual(len(vertices)-len(edges)+len(faces), 1)
        for a,b,c in faces:
            normal = cross(sub(vertices[b],vertices[a]), sub(vertices[c],vertices[a]))
            self.assertGreater(dot(normal,normal), 1e-16)

    def test_zero_width_step(self):
        v,f = build(BASE, INNER)
        self.check_mesh(v,f)
        self.assertEqual(len(v), 12)
        self.assertEqual(len(f), 18)

    def test_flat(self):
        v,f = build(BASE, [(x,y,0) for x,y,z in INNER])
        self.check_mesh(v,f)
        self.assertEqual(len(v), 4)

    def test_band_and_subdivision(self):
        v,f = build(BASE, INNER, 2, 3)
        self.check_mesh(v,f)
        self.assertEqual(len(v), 24)
        self.assertTrue(any(abs(z-3*math.sin(math.pi/8)) < 1e-8 for x,y,z in v))

    def test_height_updates(self):
        a,fa = build(BASE, INNER, 2)
        b,fb = build(BASE, [(x,y,z*2) for x,y,z in INNER], 2)
        self.assertEqual(fa,fb)
        for p,q in zip(a,b):
            self.assertEqual(p[:2],q[:2])
            self.assertAlmostEqual(p[2]*2,q[2])

    def test_negative_height(self):
        self.check_mesh(*build(BASE, [(x,y,-z) for x,y,z in INNER]))

    def test_tilted_and_nonplanar_second(self):
        tilted = [(x,y,3+x/4+y/5) for x,y,z in INNER]
        self.check_mesh(*build(BASE, tilted, 2))
        warped = [(x,y,3+i/4) for i,(x,y,z) in enumerate(INNER)]
        self.check_mesh(*build(BASE, warped, 2))

    def test_rotated_plane(self):
        rotate = lambda p: (p[2]+12,p[0]-7,p[1]+4)
        self.check_mesh(*build(list(map(rotate,BASE)), list(map(rotate,INNER)), 2))

    def test_reversed_winding(self):
        self.check_mesh(*build(BASE[::-1], INNER[::-1], 2))

    def test_concave(self):
        star = [(r*math.cos(i*math.pi/5),r*math.sin(i*math.pi/5),3)
                for i in range(10) for r in [3 if i%2 == 0 else 1.5]]
        self.check_mesh(*build(BASE,star,.3))

    def test_profile(self):
        v,f = build(BASE,INNER,2,3,lambda t:t*t)
        self.check_mesh(v,f)
        self.assertTrue(any(abs(z-3*.25**2)<1e-8 for x,y,z in v))

    def test_invalid_inputs(self):
        cases = [
            (BASE,INNER,20),
            (BASE,[(x+20,y,z) for x,y,z in INNER],0),
            (BASE,[INNER[i] for i in (0,2,1,3)],0),
            ([(*p[:2],i*.1) for i,p in enumerate(BASE)],INNER,0),
            (BASE,[(x,y,z if i else -z) for i,(x,y,z) in enumerate(INNER)],0),
            (BASE,INNER,-1),
            (BASE,[(0,0,0),(0,0,1),(1,1,1)],0),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(GeometryError):
                build(*args)

    def test_many_circle_samples(self):
        circle = [(3*math.cos(i*math.tau/80),3*math.sin(i*math.tau/80),2) for i in range(80)]
        self.check_mesh(*build(BASE,circle,1,3))

    def test_collinear_samples_preserved(self):
        inner = [(-2,-2,3),(0,-2,3),(2,-2,3),(2,2,3),(-2,2,3)]
        self.check_mesh(*build(BASE, inner, 1))

    def test_duplicate_closing_point(self):
        self.check_mesh(*build(BASE+[BASE[0]],INNER+[INNER[0]],1))

    def test_closed_default_unchanged(self):
        self.assertEqual(build(BASE,INNER,1),build(BASE,INNER,1,closed=True))

    def test_two_sided_band(self):
        v,f=build(BASE,INNER,1,3,closed=False)
        self.check_mesh(v,f)
        self.assertEqual(len(v),40)
        inner=[p for p in v if abs(p[0]) <= 1.00001 and abs(p[1]) <= 1.00001]
        self.assertEqual(len(inner),4)
        self.assertTrue(all(abs(p[2])<1e-8 for p in inner))
        self.assertEqual(max(p[2] for p in v),3)

    def test_two_sided_negative_and_tilted(self):
        for contour in [[(x,y,-z) for x,y,z in INNER],[(x,y,z+x*.2) for x,y,z in INNER]]:
            self.check_mesh(*build(BASE,contour,.5,closed=False))

    def test_two_sided_invalid_width(self):
        for width in [0]:
            with self.subTest(width=width),self.assertRaises(GeometryError):
                build(BASE,INNER,width,closed=False)

    def test_two_sided_bands_meet_at_center(self):
        for width in (2,3):
            v,f=build(BASE,INNER,width,closed=False)
            self.check_mesh(v,f)
            center=[p for p in v if abs(p[0])+abs(p[1])<1e-8]
            self.assertEqual(len(center),1)
            self.assertAlmostEqual(center[0][2],3*math.sin((1-2/width)*math.pi/2))

    def test_two_sided_flat_zero_width(self):
        self.check_mesh(*build(BASE,[(x,y,0) for x,y,z in INNER],closed=False))

    def test_multiple_reliefs_both_modes(self):
        contours = [[(x+dx,y+dy,z*h) for x,y,z in INNER] for dx,dy,h in [(-5,-4,1),(5,-4,2),(0,4,-1)]]
        for closed in (True,False):
            with self.subTest(closed=closed):
                v,f=build_many(BASE,contours,.5,closed=closed)
                self.check_mesh(v,f)
                self.assertEqual(max(p[2] for p in v),6)
                self.assertEqual(min(p[2] for p in v),-3)

    def test_multiple_zero_width(self):
        contours=[[(x-4,y,z) for x,y,z in INNER],[(x+4,y,-z) for x,y,z in INNER]]
        self.check_mesh(*build_many(BASE,contours))

    def test_multiple_overlap_rejected(self):
        for shift in (0,2,5):
            with self.subTest(shift=shift),self.assertRaises(GeometryError):
                build_many(BASE,[INNER,[(x+shift,y,z) for x,y,z in INNER]],1)

    def test_multiple_nested_rejected(self):
        with self.assertRaises(GeometryError):
            build_many(BASE,[INNER,[(x*.4,y*.4,z) for x,y,z in INNER]])

    def test_multiple_independent_heights(self):
        a=[(x-4,y,z) for x,y,z in INNER]
        b=[(x+4,y,z) for x,y,z in INNER]
        old,fo=build_many(BASE,[a,b],.5,closed=False)
        new,fn=build_many(BASE,[a,[(x,y,z+4) for x,y,z in b]],.5,closed=False)
        self.assertEqual(fo,fn)
        for p,q in zip(old,new):
            self.assertEqual(p[:2],q[:2])
            if p[0]<0:
                self.assertEqual(p,q)
        self.assertEqual(max(p[2] for p in new),7)

    def test_multiple_empty_rejected(self):
        with self.assertRaises(GeometryError):
            build_many(BASE,[])

    def test_quad_bands(self):
        for closed,expected in ((True,16),(False,32)):
            vertices,polygons=build_many(BASE,[INNER],1,3,closed=closed,quad_bands=True)
            self.assertEqual(sum(len(p)==4 for p in polygons),expected)
            triangles=[]
            for p in polygons:
                triangles.extend([p] if len(p)==3 else [(p[0],p[1],p[2]),(p[0],p[2],p[3])])
            self.check_mesh(vertices,triangles)
            old_v,old_f=build_many(BASE,[INNER],1,3,closed=closed)
            self.assertEqual(vertices,old_v)
            self.assertEqual({frozenset(f) for f in triangles},{frozenset(f) for f in old_f})

    def test_zero_height_no_edges_any_mode(self):
        flat=[(x,y,0) for x,y,z in INNER]
        for closed in (True,False):
            v,f=build_many(BASE,[flat],50,closed=closed,quad_bands=True)
            self.assertEqual(len(v),4)
            self.assertEqual(len(f),2)
            self.check_mesh(v,f)

    def test_zero_height_child_ignored_with_active_child(self):
        flat=[(x,y,0) for x,y,z in INNER]
        for closed in (True,False):
            self.assertEqual(build_many(BASE,[INNER],.5,closed=closed),
                             build_many(BASE,[flat,INNER,flat],.5,closed=closed))

    def test_union_overlap(self):
        a=[p[:2] for p in INNER]
        b=[(x+1,y) for x,y in a]
        loops=union_loops([a,b],1e-7)
        self.assertEqual(len(loops),1)
        from st_geometry import area
        self.assertAlmostEqual(area(loops[0]),20)

    def test_union_identical_nested_touching(self):
        a=[p[:2] for p in INNER]
        from st_geometry import area
        for b,expected in [(a,16),([(x*.5,y*.5) for x,y in a],16),([(x+4,y) for x,y in a],32)]:
            loops=union_loops([a,b],1e-7)
            self.assertEqual(len(loops),1)
            self.assertAlmostEqual(area(loops[0]),expected)

    def test_union_disjoint_common_height(self):
        contours=[INNER,[(x+6,y,z+100) for x,y,z in INNER]]
        united=unite_contours(BASE,contours,(0,0,3))
        self.assertEqual(len(united),2)
        self.assertTrue(all(abs(p[2]-3)<1e-8 for loop in united for p in loop))
        self.check_mesh(*build_many(BASE,united,.5))

    def test_union_bevel_both_modes(self):
        contours=[INNER,[(x+1,y+1,z+20) for x,y,z in INNER]]
        united=unite_contours(BASE,contours,(0,0,3))
        for closed in (True,False):
            self.check_mesh(*build_many(BASE,united,.2,closed=closed))

    def test_union_zero_distance_ignores_all(self):
        united=unite_contours(BASE,[INNER,[(x+1,y,z+10) for x,y,z in INNER]],(0,0,0))
        v,f=build_many(BASE,united,50,closed=False)
        self.assertEqual(len(v),4)

    def test_union_circle_overlap(self):
        circles=[[(cx+3*math.cos(i*math.tau/40),3*math.sin(i*math.tau/40),8) for i in range(40)] for cx in (-1,1)]
        united=unite_contours(BASE,circles,(0,0,2))
        self.assertEqual(len(united),1)
        self.check_mesh(*build_many(BASE,united,.2))

    def test_quality_replaces_thin_fans(self):
        circle=[(4+3*math.cos(i*math.tau/40),3*math.sin(i*math.tau/40),3) for i in range(40)]
        v,f=build_many(BASE,[circle],1,quality=True)
        edges=Counter(tuple(sorted((tri[i-1],tri[i]))) for tri in f for i in range(3))
        self.check_mesh(v,f,sum(n==1 for n in edges.values()))
        angles=[]
        for tri in f:
            if any(abs(v[i][2])>1e-8 for i in tri):continue
            lengths=[math.dist(v[tri[i]],v[tri[(i+1)%3]]) for i in range(3)]
            angles.append(min(math.degrees(math.acos(max(-1,min(1,(lengths[i]**2+lengths[(i+1)%3]**2-lengths[(i+2)%3]**2)/(2*lengths[i]*lengths[(i+1)%3]))))) for i in range(3)))
        self.assertGreater(min(angles),10)
        self.assertGreater(sum(n==1 for n in edges.values()),4)

    def test_quality_multiple_holes_and_concave_union(self):
        cases=[[[ (x-4,y,z) for x,y,z in INNER],[(x+4,y,z) for x,y,z in INNER]],
               unite_contours(BASE,[INNER,[(x+1,y+1,z) for x,y,z in INNER]],(0,0,3))]
        for contours in cases:
            v,f=build_many(BASE,contours,.2,closed=False,quality=True)
            edges=Counter(tuple(sorted((tri[i-1],tri[i]))) for tri in f for i in range(3))
            self.check_mesh(v,f,sum(n==1 for n in edges.values()))

    def test_quality_zero_height_stays_plain(self):
        v,f=build_many(BASE,[[(x,y,0) for x,y,z in INNER]],1,quality=True)
        self.assertEqual((len(v),len(f)),(4,2))


class InnerFillQualityTests(unittest.TestCase):
    def test_inner_flat_fill_gets_interior_samples(self):
        vertices,faces,edges=build_many(BASE,[INNER],.5,closed=False,quad_bands=True,return_edges=True,quality=True)
        interior=[p for p in vertices if abs(p[2])<1e-8 and abs(p[0])<1.5-1e-8 and abs(p[1])<1.5-1e-8]
        self.assertGreater(len(interior),0)
        self.assertEqual(sum(len(face)==4 for face in faces),32)
        counts=Counter(tuple(sorted((face[i-1],j))) for face in faces for i,j in enumerate(face))
        self.assertTrue(all(n<=2 for n in counts.values()))
        self.assertEqual(len(edges),4)

if __name__ == '__main__':
    unittest.main(verbosity=2)
