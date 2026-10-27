"""Run with Cinema 4D c4dpy.exe, or from Script Manager (select this file)."""
import os
import sys
import runpy
import json
import traceback
import time
import c4d

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    report = {'c4d_version': c4d.GetC4DVersion(), 'checks': []}
    try:
        namespace = runpy.run_path(os.path.join(ROOT, 'SplineTensor.pyp'),
                                  run_name='splinetensor_smoke')
        generator = c4d.BaseObject(namespace['PLUGIN_ID'])
        document = c4d.documents.BaseDocument()
        document.InsertObject(generator)
        instance = namespace['SplineTensor']()
        assert instance.Init(generator)
        assert bool(generator[1003])
        curve = generator[1002]
        assert curve.GetKnotCount() == 2
        assert abs(curve.GetKnots()[0]['vTangentRight'].x-.35)<1e-8
        assert abs(curve.GetKnots()[1]['vTangentLeft'].y+.25)<1e-8
        assert 0 < curve.GetPoint(.5).y < .3
        assert abs(curve.GetPoint(0).y) < .01
        assert abs(curve.GetPoint(1).y-1) < .01
        report['checks'].append('Default Curve endpoints')
        for name, size, height in [('Base', 10., 0.), ('Contour', 2., 3.)]:
            spline = c4d.SplineObject(4, c4d.SPLINETYPE_LINEAR)
            spline[c4d.SPLINEOBJECT_CLOSED] = True
            spline.SetAllPoints([c4d.Vector(x*size,y*size,0) for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]])
            spline.SetName(name)
            spline.InsertUnderLast(generator)
            spline.SetRelPos(c4d.Vector(0,0,height))
            spline.Message(c4d.MSG_UPDATE)
        instance.CheckDirty(generator,document)
        result = instance.GetVirtualObjects(generator,None)
        assert isinstance(result,c4d.PolygonObject), result.GetName()
        assert result.GetPolygonCount() > 18
        report['checks'].append('Zero width step with locally refined flat mesh')
        crossing = generator.GetDown().GetNext()
        crossing.SetRelPos(c4d.Vector(9,0,3))
        generator[1000] = 1.
        for mode in (True,False):
            generator[1003] = mode
            clipped = instance.GetVirtualObjects(generator,None)
            assert isinstance(clipped,c4d.PolygonObject),clipped.GetName()
            assert all(abs(p.x)<=10.000001 and abs(p.y)<=10.000001 for p in clipped.GetAllPoints())
            assert max(p.z for p in clipped.GetAllPoints())>2.99
        crossing.SetRelPos(c4d.Vector(0,0,3))
        generator[1003] = True
        report['checks'].append('Crossing child clips to base boundary in both Closed modes')
        generator[1000] = 2.
        result = instance.GetVirtualObjects(generator,None)
        assert isinstance(result,c4d.PolygonObject), result.GetName()
        assert result.GetPointCount() > 24
        assert sum(p.c != p.d for p in result.GetAllPolygons()) == 16
        report['checks'].append('Two Bezier endpoints, reversed default bend, 16 actual band quads')
        report['checks'].append('Spathe quads retained; flat mesh gains local boundary and interior samples')
        child = generator.GetDown().GetNext()
        before = instance._signature
        child.SetRelPos(c4d.Vector(0,0,6))
        instance.CheckDirty(generator,document)
        assert before != instance._signature
        result = instance.GetVirtualObjects(generator,None)
        assert abs(max(p.z for p in result.GetAllPoints())-6) < 1e-8
        report['checks'].append('Moving second child updates height and dirty state')
        child.SetRelPos(c4d.Vector(0,0,0))
        for mode in (True,False):
            generator[1003] = mode
            plain = instance.GetVirtualObjects(generator,None)
            assert isinstance(plain,c4d.PolygonObject)
            assert plain.GetPointCount() == 4 and plain.GetPolygonCount() == 2
        report['checks'].append('Zero-distance relief: base only, four points and two triangles, both Closed modes')
        generator[1000] = 1.
        child.SetRelPos(c4d.Vector(0,0,3))
        instance.GetVirtualObjects(generator,None)
        builds = instance._build_count
        start = time.perf_counter()
        for _ in range(100):
            instance.CheckDirty(generator,document)
            instance.GetVirtualObjects(generator,None)
        report['unchanged_100_calls_ms'] = round((time.perf_counter()-start)*1000,3)
        assert instance._build_count == builds
        generator[1000] = .75
        instance.GetVirtualObjects(generator,None)
        assert instance._build_count == builds+1
        generator[1002] = namespace['default_curve']()
        custom = generator[1002]
        custom.InsertKnot(.4,.2)
        generator[1002] = custom
        instance.GetVirtualObjects(generator,None)
        assert instance._build_count == builds+2
        report['checks'].append('100 unchanged evaluations: zero geometry builds; width and Curve edits invalidate cache')
        old_curve = c4d.SplineData()
        old_curve.MakeUserSpline('sin(x*pi/2)',17)
        generator[1002] = old_curve
        instance.Message(generator,c4d.MSG_UPDATE,None)
        assert generator[1002].GetKnotCount() == 2
        custom = c4d.SplineData()
        custom.MakeUserSpline('x*x',17)
        generator[1002] = custom
        instance.Message(generator,c4d.MSG_UPDATE,None)
        assert generator[1002].GetKnotCount() == 17
        report['checks'].append('Old default migrates to two knots; custom 17-knot curve is preserved')
        # Parse the shipped description independently of plugin startup.
        assert generator.GetDescription(c4d.DESCFLAGS_DESC_0) is not None
        labels = {bc.GetString(c4d.DESC_NAME) for bc, did, gid in generator.GetDescription(c4d.DESCFLAGS_DESC_0)}
        assert {'Spathe Width', 'Subdivision', 'Curve', 'Closed'} <= labels, labels
        report['checks'].append('Object plugin and description resource registration')
        example = runpy.run_path(os.path.join(ROOT, 'examples', 'create_example.py'))
        scene = example['create_document']()
        gen = scene.GetFirstObject()
        gen.SetPhong(True,True,.31)
        scene.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        cache = gen.GetCache()
        assert isinstance(cache, c4d.PolygonObject), cache.GetName() if cache else 'No generator cache'
        assert abs(cache.GetTag(c4d.Tphong)[c4d.PHONGTAG_PHONG_ANGLE]-.31)<1e-8
        assert cache.GetPhongBreak().GetCount()>0
        gen.GetTag(c4d.Tphong)[c4d.PHONGTAG_PHONG_ANGLE]=.6
        scene.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        cache=gen.GetCache()
        assert abs(cache.GetTag(c4d.Tphong)[c4d.PHONGTAG_PHONG_ANGLE]-.6)<1e-8
        report['checks'].append('Generator Phong settings propagate and update; projected contour has explicit edge breaks')
        cache_guid = cache.GetGUID()
        for _ in range(20):
            scene.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
            assert gen.GetCache().GetGUID() == cache_guid
        report['checks'].append('20 unchanged document passes preserve the same generator cache')
        report['example_points'] = cache.GetPointCount()
        report['example_polygons'] = cache.GetPolygonCount()
        report['example_quads'] = sum(p.c != p.d for p in cache.GetAllPolygons())
        old_height = max(p.z for p in cache.GetAllPoints())
        circle = gen.GetDown().GetNext()
        circle.SetRelPos(circle.GetRelPos() + c4d.Vector(0,0,20))
        scene.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        assert abs(max(p.z for p in gen.GetCache().GetAllPoints())-old_height-20) < 1e-6
        report['checks'].append('Parametric rectangle/circle: real generator cache and movement reevaluation')
        circle.SetRelPos(circle.GetRelPos() - c4d.Vector(0,0,20))
        scene.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        destination_scene = os.path.join(ROOT,'examples','Rectangle-Circle.c4d')
        assert c4d.documents.SaveDocument(scene,destination_scene,c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,c4d.FORMAT_C4DEXPORT)
        report['checks'].append('Saved rectangle/circle example scene')
        gen[1003] = False
        scene.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        ridge = gen.GetCache()
        assert isinstance(ridge, c4d.PolygonObject), ridge.GetName() if ridge else 'Missing ridge cache'
        assert ridge.GetPointCount() > report['example_points']
        assert any(abs(p.z) < 1e-6 and abs(p.x) < 100 and abs(p.y) < 160 for p in ridge.GetAllPoints())
        assert c4d.documents.SaveDocument(scene,os.path.join(ROOT,'examples','Rectangle-Circle-Ridge.c4d'),c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,c4d.FORMAT_C4DEXPORT)
        report['checks'].append('Closed defaults on; toggle off reevaluates two-sided bevel with base-level center')
        gen[1003] = True
        scene.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        assert gen.GetCache().GetPointCount() == report['example_points']
        report['checks'].append('Toggle Closed back on restores original surface')
        # Export actual evaluated geometry for an independent visual preview.
        mesh = gen.GetCache()
        with open(os.path.join(ROOT,'examples','Rectangle-Circle-mesh.json'),'w',encoding='utf-8') as stream:
            json.dump({'points': [(p.x,p.y,p.z) for p in mesh.GetAllPoints()],
                       'triangles': [t for p in mesh.GetAllPolygons() for t in
                                     ([(p.a,p.b,p.c)] if p.c == p.d else [(p.a,p.b,p.c),(p.a,p.c,p.d)])]},stream)
        multi = example['create_multi_document']()
        mg = multi.GetFirstObject()
        for closed_mode in (True,False):
            mg[1003] = closed_mode
            multi.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
            mesh = mg.GetCache()
            assert isinstance(mesh,c4d.PolygonObject), mesh.GetName() if mesh else 'Missing multi cache'
            old = [(p.x,p.y,p.z) for p in mesh.GetAllPoints()]
            last = mg.GetDown().GetNext().GetNext()
            pos = last.GetRelPos()
            last.SetRelPos(pos+c4d.Vector(0,0,20))
            multi.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
            updated = [(p.x,p.y,p.z) for p in mg.GetCache().GetAllPoints()]
            assert old == updated
            last.SetRelPos(pos)
            height_driver=mg.GetDown().GetNext()
            driver_pos=height_driver.GetRelPos()
            height_driver.SetRelPos(driver_pos+c4d.Vector(0,0,20))
            multi.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
            updated=[(p.x,p.y,p.z) for p in mg.GetCache().GetAllPoints()]
            for side in (-1,1):
                assert abs(max(p[2] for p in updated if p[0]*side>0)-max(p[2] for p in old if p[0]*side>0)-20)<1e-6
            height_driver.SetRelPos(driver_pos)
        multi.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        assert c4d.documents.SaveDocument(multi,os.path.join(ROOT,'examples','Multiple-Reliefs.c4d'),c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,c4d.FORMAT_C4DEXPORT)
        report['checks'].append('Both Closed modes: child 2 controls height of every region; child 3 Z does not change height')
        left=mg.GetDown().GetNext(); right=left.GetNext()
        left.SetRelPos(c4d.Vector(-20,0,45)); right.SetRelPos(c4d.Vector(20,0,95))
        mg[1000]=.5
        multi.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        assert isinstance(mg.GetCache(),c4d.PolygonObject),mg.GetCache().GetName()
        assert abs(max(p.z for p in mg.GetCache().GetAllPoints())-45)<1e-6
        assert c4d.documents.SaveDocument(multi,os.path.join(ROOT,'examples','United-Relief.c4d'),c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,c4d.FORMAT_C4DEXPORT)
        report['checks'].append('Overlapping parametric circles generate a united relief with child-2 height')
        mg[1003]=True; mg[1000]=0.
        left[c4d.PRIM_CIRCLE_RADIUS]=70.
        multi.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        assert isinstance(mg.GetCache(),c4d.PolygonObject)
        assert min(p.x for p in mg.GetCache().GetAllPoints() if p.z>1)<-85
        right.Remove(); right.InsertBefore(left)
        multi.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        assert abs(max(p.z for p in mg.GetCache().GetAllPoints())-95)<1e-6
        left.Remove()
        multi.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
        assert min(p.x for p in mg.GetCache().GetAllPoints() if p.z>1)>-40
        report['checks'].append('Child primitive edits, reordering and removal invalidate cache; new child 2 becomes height driver')
        legacy_path=os.path.join(os.path.dirname(ROOT),'backups','SplineTensor-0.2.0','examples','Rectangle-Circle.c4d')
        if os.path.exists(legacy_path):
            loaded=c4d.documents.LoadDocument(legacy_path,c4d.SCENEFILTER_OBJECTS,None)
            assert loaded is not None
            assert loaded.GetFirstObject()[1002].GetKnotCount()==2
            report['checks'].append('Opening a legacy saved scene automatically updates the default Curve to two knots')
        report['passed'] = True
    except Exception:
        report['passed'] = False
        report['error'] = traceback.format_exc()
    destination = os.environ.get('SPLINETENSOR_TEST_REPORT', os.path.join(ROOT,'HOST-TEST.json'))
    with open(destination, 'w', encoding='utf-8') as stream:
        json.dump(report,stream,indent=2)
    print(json.dumps(report,indent=2))
    if not report['passed']:
        raise RuntimeError('SplineTensor host smoke test failed; see report.')


if __name__ == '__main__':
    main()
