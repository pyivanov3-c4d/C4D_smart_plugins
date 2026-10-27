"""Geometry tests with a small math adapter; no Cinema 4D runtime required."""
import math
from pathlib import Path
import runpy
import sys
import types
import unittest
from collections import Counter

ROOT = Path(__file__).resolve().parents[1] / 'MesherPro'
sys.path.insert(0, str(ROOT))
from mesher_geometry import circle, rectangle


class V:
    def __init__(self, x=0, y=0, z=0): self.x,self.y,self.z=x,y,z
    def __add__(self,o): return V(self.x+o.x,self.y+o.y,self.z+o.z)
    def __sub__(self,o): return V(self.x-o.x,self.y-o.y,self.z-o.z)
    def __mul__(self,s): return V(self.x*s,self.y*s,self.z*s)
    __rmul__=__mul__
    def __truediv__(self,s): return self*(1/s)
    def GetNormalized(self): return self/math.sqrt(self.dot(self))
    def dot(self,o): return self.x*o.x+self.y*o.y+self.z*o.z
    def cross(self,o): return V(self.y*o.z-self.z*o.y,self.z*o.x-self.x*o.z,self.x*o.y-self.y*o.x)
    Dot=dot
    Cross=cross


class M:
    def __init__(self,off,v1,v2,v3): self.off,self.v1,self.v2,self.v3=off,v1,v2,v3
    def __mul__(self,p): return self.off+self.v1*p.x+self.v2*p.y+self.v3*p.z


class Mesh:
    def __init__(self,n,f): self.faces=[None]*f
    def SetAllPoints(self,p): self.points=p
    def GetAllPoints(self): return self.points
    def SetPolygon(self,i,f): self.faces[i]=f
    def SetName(self,n): pass
    def SetPhong(self,*args): pass
    def Message(self,*args): pass
    def InsertTag(self,tag): self.uvtag=tag
    def GetTag(self,kind): return self.uvtag


class UVTag:
    def __init__(self,count): self.values=[None]*count
    def SetSlow(self,i,*values): self.values[i]=values
    def GetDataCount(self): return len(self.values)
    def GetSlow(self,i): return dict(zip(('a','b','c','d'),self.values[i]))


fake=types.ModuleType('c4d')
fake.Vector, fake.Matrix, fake.PolygonObject=V,M,Mesh
fake.UVWTag=UVTag
fake.Tuvw=5671
fake.CPolygon=lambda *args:args
fake.MSG_UPDATE=0
fake.plugins=types.SimpleNamespace(ObjectData=object)
fake.bitmaps=fake.utils=types.SimpleNamespace()
sys.modules['c4d']=fake
code=runpy.run_path(str(ROOT/'spline_mesher_blue.pyp'),run_name='geometry_test')


class Line:
    def GetSegmentLength(self,segment): return 100
    def GetPosition(self,t,*args): return V(0,0,100*t)
    def GetMatrix(self,t,*args):
        # SplineHelp tangent=v1, binormal=v2, normal=v3.
        return M(V(0,0,100*t),V(0,0,1),V(1,0,0),V(0,1,0))


def manifold(mesh):
    edges=Counter()
    for face in mesh.faces:
        assert len(set(face))==len(face)
        assert all(0<=i<len(mesh.points) for i in face)
        for a,b in zip(face,face[1:]+face[:1]):
            edges[tuple(sorted((a,b)))]+=1
    return all(n==2 for n in edges.values())


def volume(mesh):
    result=0
    for f in mesh.faces:
        a=mesh.points[f[0]]
        for j in range(1,len(f)-1):
            result+=a.dot(mesh.points[f[j]].cross(mesh.points[f[j+1]]))/6
    return result


class GeometryTests(unittest.TestCase):
    def test_multisegment_uv_remapping(self):
        mesh=code['sweep_mesh'](Line(),0,circle(5,8),20,False,0,False)
        code['remap_v'](mesh,0.25,0.75)
        values=[p.y for face in mesh.uvtag.values for p in face]
        self.assertAlmostEqual(min(values),0.25)
        self.assertAlmostEqual(max(values),0.75)

    def test_count_placement(self):
        self.assertEqual(code['piece_ranges'](100,20,999,False,3),[(0,20),(40,60),(80,100)])
        self.assertEqual(code['piece_ranges'](100,20,-999,False,1),[(40,60)])
        for closed in (False,True):
            slots=code['piece_ranges'](100,15,999,closed,4)
            self.assertEqual(len(slots),4)
            steps=[slots[i+1][0]-slots[i][0] for i in range(3)]
            self.assertAlmostEqual(min(steps),max(steps))
            self.assertTrue(all(abs(b-a-15)<1e-8 for a,b in slots))
        path=code['DistancePath']([([V(0,0,0),V(0,0,100)],False)])
        meshes=list(code['gap_meshes'](path,0,circle(2,8),100,False,20,999,2,0,True,('circle',2,4),None,count=3))
        self.assertEqual(len(meshes),3)
        loop=code['DistancePath']([([V(35*math.cos(math.tau*i/120),35*math.sin(math.tau*i/120),0)
                                     for i in range(120)],True)])
        meshes=list(code['gap_meshes'](loop,0,circle(2,8),loop.GetSegmentLength(0),True,
                                      20,999,2,0,True,('circle',2,4),None,count=5))
        self.assertEqual(len(meshes),5)
        self.assertTrue(all(manifold(mesh) for mesh in meshes))

    def test_uv_range_seams_caps_and_gap_positions(self):
        def check(mesh):
            self.assertEqual(len(mesh.faces),len(mesh.uvtag.values))
            uv=[p for face in mesh.uvtag.values for p in face]
            self.assertTrue(all(-1e-9<=p.x<=1+1e-9 and -1e-9<=p.y<=1+1e-9 for p in uv))
            self.assertAlmostEqual(min(p.x for p in uv),0)
            self.assertAlmostEqual(max(p.x for p in uv),1)
            return uv
        for profile,cap in ((circle(5,24),('circle',5,8)),
                            (rectangle(20,10,2,4),('rectangle',2,4)),
                            (rectangle(20,10,0,4),None)):
            mesh=code['sweep_mesh'](Line(),0,profile,20,False,0,True,cap_style=cap)
            uv=check(mesh)
            self.assertAlmostEqual(min(p.y for p in uv),0)
            self.assertAlmostEqual(max(p.y for p in uv),1)
        mesh=code['sweep_mesh'](Line(),0,circle(5,8),20,True,0,False)
        uv=check(mesh)
        self.assertAlmostEqual(max(p.y for p in uv),1)
        path=code['DistancePath']([([V(0,0,0),V(0,0,100)],False)])
        meshes=list(code['gap_meshes'](path,0,circle(2,8),100,False,20,20,2,0,True,('circle',2,4),None))
        for i,mesh in enumerate(meshes):
            uv=check(mesh)
            self.assertAlmostEqual(min(p.y for p in uv),i*0.4)
            self.assertAlmostEqual(max(p.y for p in uv),i*0.4+0.2)
        check(code['chain_mesh'](Line(),0,100,False,5,2,2,0))

    def test_bent_gap_clearance_planes(self):
        pts=[V(35*math.cos(math.pi*i/160),35*math.sin(math.pi*i/160),0) for i in range(81)]
        path=code['DistancePath']([(pts,False)])
        length=path.GetSegmentLength(0)
        profile=rectangle(12,6,1,4)
        meshes=list(code['gap_meshes'](path,0,profile,length,False,15,2,1,0,True,('rectangle',1,4),None))
        slots=code['piece_ranges'](length,15,2,False)
        for i in range(len(meshes)-1):
            middle=(slots[i][1]+slots[i+1][0])/2
            f=code['path_frame'](path,middle/length,0)
            left=max((p-f.off).dot(f.v3) for p in meshes[i].points)
            right=min((p-f.off).dot(f.v3) for p in meshes[i+1].points)
            self.assertGreaterEqual(right-left,2-1e-6)

    def test_reset_matches_new_object_defaults_and_undo(self):
        class Curve:
            def MakeLinearSplineLinear(self,n): self.knots=[None]*n
            def GetKnots(self): return [{'lFlagsSettings':0} for _ in self.knots]
            def SetKnot(self,i,p,flags,**kw): self.knots[i]=p
            def SetRange(self,*args): pass
        fake.SplineData=Curve
        fake.CustomSplineKnotInterpolationLinear=0
        fake.MSG_DESCRIPTION_COMMAND=18
        fake.UNDOTYPE_CHANGE=1
        fake.DIRTYFLAGS_DATA=1
        fake.DIRTYFLAGS_DESCRIPTION=2
        fake.EventAdd=lambda:None
        events=[]
        doc=types.SimpleNamespace(StartUndo=lambda:events.append('start'),
              AddUndo=lambda *args:events.append('undo'),EndUndo=lambda:events.append('end'))
        class Op(dict):
            def __missing__(self,key): return None
            def GetDocument(self): return doc
            def SetDirty(self,flags): pass
            def Message(self,msg): pass
        instance=code['SplineMesherBlue']()
        fresh,changed=Op(),Op()
        instance.Init(fresh)
        for key in fresh: changed[key]='modified'
        changed[99999]='unrelated'
        instance.Message(changed,18,{'id':[types.SimpleNamespace(id=code['RESET_ALL'])]})
        for key,value in fresh.items():
            if key!=code['WIDTH_CURVE']: self.assertEqual(changed[key],value)
        self.assertEqual([v.y for v in changed[code['WIDTH_CURVE']].knots],[1,1])
        self.assertEqual(changed[99999],'unrelated')
        self.assertEqual(events,['start','undo','end'])

    def test_overlapping_pieces_and_tilts(self):
        for closed in (False,True):
            ranges=code['piece_ranges'](100,30,-10,closed)
            self.assertEqual(ranges,[(0,30),(20,50),(40,70),(60,90)])
        for space in (-30,-40):
            with self.assertRaises(ValueError): code['piece_ranges'](100,30,space,False)
        path=code['DistancePath']([([V(0,0,0),V(0,0,100)],False)])
        args=(path,0,circle(2,8),100,False,30,-10,5,0,False,None,None)
        original=list(code['gap_meshes'](*args))
        for x,y in ((math.pi/2,0),(0,math.pi/2),(0.3,0.7)):
            rotated=list(code['gap_meshes'](*args,tilt_x=x,tilt_y=y))
            self.assertEqual(len(rotated),4)
            for i,(a,b) in enumerate(zip(original,rotated)):
                center=V(0,0,i*20+15)
                for p,q in zip(a.points,b.points):
                    self.assertAlmostEqual((p-center).dot(p-center),(q-center).dot(q-center))
                self.assertTrue(any((p-q).dot(p-q)>1e-6 for p,q in zip(a.points,b.points)))

    def test_gap_lengths_caps_and_remainder(self):
        path=code['DistancePath']([([V(0,0,0),V(0,0,137)],False)])
        self.assertEqual(code['piece_ranges'](137,30,10,False),[(0,30),(40,70),(80,110)])
        self.assertEqual(code['piece_ranges'](110,30,10,True),[(0,30),(40,70)])
        for profile,cap in ((circle(5,24),('circle',5,8)),(rectangle(10,6,2,4),('rectangle',2,4))):
            meshes=list(code['gap_meshes'](path,0,profile,137,False,30,10,3,0,True,cap,None))
            self.assertEqual(len(meshes),3)
            for i,mesh in enumerate(meshes):
                self.assertTrue(manifold(mesh))
                self.assertAlmostEqual(min(p.z for p in mesh.points),i*40,places=7)
                self.assertAlmostEqual(max(p.z for p in mesh.points),i*40+30,places=7)
        with self.assertRaises(ValueError):
            list(code['gap_meshes'](path,0,circle(5,24),137,False,5,10,3,0,True,('circle',5,8),None))

    def test_gap_width_curve_does_not_restart(self):
        class Curve:
            def GetKnotCount(self): return 2
            def GetPoint(self,t): return V(t,1+t,0)
        path=code['DistancePath']([([V(0,0,0),V(0,0,100)],False)])
        meshes=list(code['gap_meshes'](path,0,circle(2,8),100,False,30,10,5,0,False,None,Curve()))
        self.assertEqual(len(meshes),2)
        self.assertAlmostEqual(math.hypot(meshes[1].points[0].x,meshes[1].points[0].y),2.8)

    def test_primitive_closure_and_arc_exception(self):
        fake.Osplinearc, fake.Osplinecircle, fake.Osplinerectangle, fake.Ospline = 10,11,12,13
        fake.Tsegment = 14
        points=[V(0,0,0),V(10,0,0),V(10,10,0),V(0,10,0)]
        class Source:
            def __init__(self,kind,closed=False): self.kind,self.closed=kind,closed
            def CheckType(self,kind): return self.kind==kind
            def IsClosed(self): return self.closed
            def GetSegmentCount(self): return 0
        tag=types.SimpleNamespace(GetAllHighlevelData=lambda:[{'cnt':4,'closed':False}])
        line=types.SimpleNamespace(GetAllPoints=lambda:points,GetTag=lambda kind:tag)
        helper=types.SimpleNamespace(GetLineObject=lambda:line)
        spline=types.SimpleNamespace(IsClosed=lambda:False)
        for kind,closed,expected in ((11,False,True),(12,False,True),
                                    (10,False,False),(13,False,False),(13,True,True)):
            path,flags=code['distance_path'](helper,spline,Source(kind,closed))
            self.assertEqual(flags,[expected])
            self.assertEqual(path.GetSegmentLength(0),40 if expected else 30)
            if expected:
                mesh=code['sweep_mesh'](path,0,circle(1,8),40,True,0,False)
                self.assertTrue(manifold(mesh))

    def test_width_curve_profiles_and_caps(self):
        class Curve:
            def GetKnotCount(self): return 2
            def GetPoint(self,t): return V(t,0.5+1.5*t,0)
        curve=Curve()
        for profile,offset in ((circle(5,24),0),(rectangle(10,6,1,4),0),(circle(2,12),3)):
            mesh=code['sweep_mesh'](Line(),0,profile,10,False,0,False,
                                   strand_offset=offset,width_curve=curve)
            for j in (0,5,10):
                for i,(x,y) in enumerate(profile):
                    p=mesh.points[j*len(profile)+i]
                    self.assertAlmostEqual(math.hypot(p.x,p.y),math.hypot(x+offset,y)*(0.5+1.5*j/10))
        mesh=code['sweep_mesh'](Line(),0,circle(5,24),10,False,0,True,
                               cap_style=('circle',5,8),width_curve=curve)
        self.assertTrue(manifold(mesh))
        self.assertAlmostEqual(min(p.z for p in mesh.points),-2.5)
        self.assertAlmostEqual(max(p.z for p in mesh.points),110)
        self.assertEqual(code['width_factor'](None,0.5),1)

    def test_chain_width_curve(self):
        class Curve:
            def GetKnotCount(self): return 2
            def GetPoint(self,t): return V(t,2,0)
        mesh=code['chain_mesh'](Line(),0,1,False,5,2,5,0,width_curve=Curve())
        self.assertTrue(manifold(mesh))
        self.assertAlmostEqual(max(p.y for p in mesh.points)-min(p.y for p in mesh.points),4)

    def test_sharp_corner_miter_preserves_radius(self):
        path=code['DistancePath']([([V(0,0,0),V(0,0,97),V(103,0,97)],False)])
        offsets,corners=code['corner_samples'](path,0,29,False,5)
        corner=97/200
        self.assertIn(corner,offsets)
        self.assertAlmostEqual(corners[corner][1],math.sqrt(2))
        mesh=code['sweep_mesh'](path,0,circle(5,24),29,False,0,True)
        self.assertTrue(manifold(mesh))
        ring=offsets.index(corner)
        for p in mesh.points[ring*24:(ring+1)*24]:
            self.assertAlmostEqual(p.x+p.z-97,0,places=6)
            self.assertAlmostEqual(p.x*p.x+p.y*p.y,25,places=6)
            self.assertAlmostEqual((p.z-97)**2+p.y*p.y,25,places=6)
        self.assertTrue(all(abs(t-corner)>=5/200-1e-9 for t in offsets if t!=corner))

    def test_distance_sampling_uneven_source_points(self):
        path=code['DistancePath']([( [V(0,0,z) for z in (0,0,1,2,3,90,100)], False)])
        frames=code['sweep_frames'](path,0,20,False)
        for i,frame in enumerate(frames):
            self.assertAlmostEqual(frame.off.z,i*5)
        mesh=code['sweep_mesh'](path,0,circle(2,8),20,False,0,False)
        for i in range(21):
            self.assertTrue(all(abs(p.z-i*5)<1e-8 for p in mesh.points[i*8:(i+1)*8]))

    def test_distance_sampling_bend_and_closed_path(self):
        path=code['DistancePath']([([V(0,0,0),V(0,0,1),V(0,0,100),V(1,0,100),V(100,0,100)],False)])
        self.assertAlmostEqual(path.GetSegmentLength(0),200)
        for i in range(41):
            p=path.GetPosition(i/40)
            self.assertAlmostEqual(p.z+p.x,i*5)
        loop=code['DistancePath']([([V(0,0,0),V(10,0,0),V(10,10,0),V(0,10,0),V(0,0,0)],True)])
        self.assertAlmostEqual(loop.GetSegmentLength(0),40)
        mesh=code['sweep_mesh'](loop,0,circle(1,8),40,True,0,False)
        self.assertTrue(manifold(mesh))

    def test_unchanged_evaluation_reuses_native_cache(self):
        fake.HIERARCHYCLONEFLAGS_ASSPLINE = 1
        cache = object()
        child = object()
        calls = []
        class Generator:
            def GetDown(self): return child
            def GetAndCheckHierarchyClone(self, *args, **kwargs):
                calls.append((args, kwargs))
                return {'dirty':False, 'clone':cache}
            def CheckCache(self, *args):
                raise AssertionError('Do not force hierarchy regeneration')
            def GetCache(self, *args):
                raise AssertionError('Native hierarchy helper owns cache lifetime')
        instance = code['SplineMesherBlue']()
        op = Generator()
        for _ in range(20):
            self.assertIs(instance.GetVirtualObjects(op, None), cache)
        self.assertEqual(len(calls),20)
        self.assertTrue(all(not kwargs for args,kwargs in calls))

    def test_tangent_and_closed_seam(self):
        class Loop:
            def GetSegmentLength(self,segment): return 200
            def GetPosition(self,t,*args):
                a=math.tau*t
                return V(30*math.cos(a),30*math.sin(a),5*math.sin(2*a))
        frames=code['sweep_frames'](Loop(),0,80,True)
        for j,f in enumerate(frames[:-1]):
            a=math.tau*j/80
            tangent=V(-30*math.sin(a),30*math.cos(a),10*math.cos(2*a)).GetNormalized()
            self.assertAlmostEqual(f.v3.dot(tangent),1,places=7)
            self.assertAlmostEqual(f.v1.dot(tangent),0,places=7)
        self.assertIs(frames[0],frames[-1])
        mesh=code['sweep_mesh'](Loop(),0,rectangle(3,2,0,1),80,True,0,True)
        self.assertTrue(manifold(mesh))
        self.assertEqual(len(mesh.points),320)

    def test_rounded_caps(self):
        for n in (3,24,200):
            mesh=code['sweep_mesh'](Line(),0,circle(5,n),10,False,0,True,
                                   cap_style=('circle',5,8))
            self.assertTrue(manifold(mesh))
            self.assertGreater(volume(mesh),0)
            self.assertAlmostEqual(min(p.z for p in mesh.points),-5)
            self.assertAlmostEqual(max(p.z for p in mesh.points),105)
            for p in mesh.points:
                if p.z<0 or p.z>100:
                    z=p.z if p.z<0 else p.z-100
                    self.assertAlmostEqual(p.x*p.x+p.y*p.y+z*z,25,places=7)
        for width,height,r in ((20,6,2),(20,6,3),(6,6,3)):
            mesh=code['sweep_mesh'](Line(),0,rectangle(width,height,r,4),10,False,0,True,
                                   cap_style=('rectangle',r,4))
            self.assertTrue(manifold(mesh))
            self.assertGreater(volume(mesh),0)
            self.assertAlmostEqual(min(p.z for p in mesh.points),-r)
            self.assertAlmostEqual(max(p.z for p in mesh.points),100+r)

    def test_every_circle_count(self):
        for n in range(3,201):
            p=circle(5,n)
            self.assertEqual(len(p),n)
            self.assertTrue(all(abs(math.hypot(*v)-5)<1e-8 for v in p))
        self.assertEqual(len(circle(5,0)),3)
        self.assertEqual(len(circle(5,999)),200)

    def test_rectangle_dimensions_and_fillets(self):
        for radius in (0,1,3,100):
            for n in (1,4,200):
                p=rectangle(20,6,radius,n)
                self.assertAlmostEqual(max(x for x,y in p)-min(x for x,y in p),20)
                self.assertAlmostEqual(max(y for x,y in p)-min(y for x,y in p),6)
                self.assertTrue(all(math.dist(p[i],p[(i+1)%len(p)])>1e-9 for i in range(len(p))))
        self.assertEqual(len(rectangle(20,6,1,4)),20)

    def test_capped_sweeps_winding_and_volume(self):
        for p in (circle(5,3),circle(5,200),rectangle(20,6,0,4),rectangle(20,6,2,8)):
            mesh=code['sweep_mesh'](Line(),0,p,10,False,0,True)
            self.assertTrue(manifold(mesh))
            area=sum(p[i][0]*p[(i+1)%len(p)][1]-p[(i+1)%len(p)][0]*p[i][1] for i in range(len(p)))/2
            self.assertAlmostEqual(volume(mesh),area*100,places=6)
            self.assertAlmostEqual(min(v.z for v in mesh.points),0)
            self.assertAlmostEqual(max(v.z for v in mesh.points),100)

    def test_closed_topology(self):
        mesh=code['sweep_mesh'](Line(),0,circle(5,8),10,True,2,True)
        self.assertTrue(manifold(mesh))
        self.assertEqual(len(mesh.points),80)

    def test_chain_diameter_and_winding(self):
        # One link on a short path, making bounds equal to the oval plus wire.
        for diameter in (1,2,4):
            mesh=code['chain_mesh'](Line(),0,1,False,5,diameter,5,0)
            self.assertTrue(manifold(mesh))
            self.assertGreater(volume(mesh),0)
            self.assertAlmostEqual(max(p.y for p in mesh.points)-min(p.y for p in mesh.points),diameter)

    def test_allocation_guard(self):
        with self.assertRaises(ValueError):
            code['sweep_mesh'](Line(),0,circle(5,200),1000000,False,0,True)
        with self.assertRaises(ValueError):
            code['chain_mesh'](Line(),0,100,False,5,10,5,0)


if __name__=='__main__': unittest.main()
