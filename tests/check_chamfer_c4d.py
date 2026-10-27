"""Run in Cinema 4D Script Manager after restarting to load chamferPro.

Uses a private document; does not touch the current scene. Raises on failure.
"""
import math
import c4d

PLUGIN_ID = 1069990
ANGLE, RADIUS = 11000, 11001


def main():
    doc = c4d.documents.BaseDocument()
    try:
        generator = c4d.BaseObject(PLUGIN_ID)
        if generator is None: raise RuntimeError('Restart Cinema 4D to load chamferPro.')
        doc.InsertObject(generator)
        generator[ANGLE], generator[RADIUS] = math.radians(30), 20.
        source = c4d.SplineObject(5, c4d.SPLINETYPE_LINEAR)
        points = [c4d.Vector(-100,0,0),c4d.Vector(-2,0,0),c4d.Vector(),
                  c4d.Vector(0,3,0),c4d.Vector(0,100,0)]
        source.SetAllPoints(points)
        source.Message(c4d.MSG_UPDATE)
        source.InsertUnder(generator)
        doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        spline = generator.GetRealSpline()
        assert spline is not None, 'No generated spline'
        assert spline.GetPointCount() == 5, ('Unexpected point count', spline.GetPointCount())
        assert (spline.GetPoint(1)-c4d.Vector(-20,0,0)).GetLength() < 1e-4
        assert (spline.GetPoint(3)-c4d.Vector(0,20,0)).GetLength() < 1e-4
        assert source.GetAllPoints() == points, 'Input was modified'
        generator[RADIUS] = 30.
        generator.Message(c4d.MSG_UPDATE)
        doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        spline = generator.GetRealSpline()
        assert (spline.GetPoint(1)-c4d.Vector(-30,0,0)).GetLength() < 1e-4, 'Radius update stale'
        source.SetPoint(4, c4d.Vector(0,150,0))
        source.Message(c4d.MSG_UPDATE)
        doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        spline = generator.GetRealSpline()
        assert abs(spline.GetAllPoints()[-1].y-150) < 1e-4, 'Child update stale'
        generator[RADIUS] = 0.
        generator.Message(c4d.MSG_UPDATE)
        doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        spline = generator.GetRealSpline()
        assert spline.GetPointCount() == source.GetPointCount(), 'Zero radius bypass failed'
        print('chamferPro C4D smoke checks passed.')
    finally:
        c4d.documents.KillDocument(doc)


if __name__ == '__main__': main()
