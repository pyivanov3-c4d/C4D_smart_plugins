"""Run in Cinema 4D Script Manager after installing SplineTensor.

Creates a NEW document, leaving existing scenes intact.
"""
import c4d

PLUGIN_ID = 1069998


def create_document():
    doc = c4d.documents.BaseDocument()
    doc.SetDocumentName('SplineTensor - Rectangle and Circle')
    generator = c4d.BaseObject(PLUGIN_ID)
    if generator is None:
        raise RuntimeError('Install SplineTensor and restart Cinema 4D first.')
    generator.SetName('SplineTensor - continuous relief surface')
    generator[1000] = 35.0
    generator[1001] = 12
    doc.InsertObject(generator)
    rectangle = c4d.BaseObject(c4d.Osplinerectangle)
    rectangle.SetName('1 - Rectangle - outer boundary')
    rectangle[c4d.PRIM_RECTANGLE_WIDTH] = 400.0
    rectangle[c4d.PRIM_RECTANGLE_HEIGHT] = 500.0
    rectangle[c4d.PRIM_PLANE] = c4d.PRIM_PLANE_XY
    rectangle.InsertUnderLast(generator)
    circle = c4d.BaseObject(c4d.Osplinecircle)
    circle.SetName('2 - Circle - move Z to change relief')
    circle[c4d.PRIM_CIRCLE_RADIUS] = 115.0
    circle[c4d.PRIM_PLANE] = c4d.PRIM_PLANE_XY
    circle.SetRelScale(c4d.Vector(1, 1.5, 1))
    circle.SetRelPos(c4d.Vector(0, 0, 45))
    circle.SetRelRot(c4d.Vector(0, .10, 0))
    circle.InsertUnderLast(generator)
    doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    return doc


def main():
    doc = create_document()
    c4d.documents.InsertBaseDocument(doc)
    c4d.documents.SetActiveDocument(doc)
    c4d.EventAdd()


def create_multi_document():
    doc = create_document()
    doc.SetDocumentName('SplineTensor - Multiple Reliefs')
    gen = doc.GetFirstObject()
    gen[1000] = 20.
    gen[1003] = False
    first = gen.GetDown().GetNext()
    first[c4d.PRIM_CIRCLE_RADIUS] = 55.
    first.SetRelScale(c4d.Vector(1,1,1))
    first.SetRelPos(c4d.Vector(-95,0,45))
    second = first.GetClone()
    second.SetName('3 - Additional circle - union footprint')
    second.SetRelPos(c4d.Vector(95,0,70))
    second.InsertUnderLast(gen)
    doc.ExecutePasses(None,True,True,True,c4d.BUILDFLAGS_NONE)
    return doc


if __name__ == '__main__':
    main()
