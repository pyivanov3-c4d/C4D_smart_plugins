"""Read direct splines and evaluated spline-generator output without scene edits."""
import c4d
from c4d import utils
from st_geometry import GeometryError


def hierarchy_key(node):
    m=node.GetMl()
    children=[]
    child=node.GetDown()
    while child:
        children.append(hierarchy_key(child)); child=child.GetNext()
    return (node.GetGUID(),node.GetDirty(c4d.DIRTYFLAGS_DATA),
            tuple((v.x,v.y,v.z) for v in (m.off,m.v1,m.v2,m.v3)),tuple(children))


def spline_loops(node,matrix,density=1):
    spline=node.GetRealSpline()
    if spline is None:return None
    helper=utils.SplineHelp()
    if not helper.InitSplineWith(node,c4d.SPLINEHELPFLAGS_RETAINLINEOBJECT):
        raise GeometryError('Could not sample spline: '+node.GetName())
    line=helper.GetLineObject()
    if line is None:raise GeometryError('Spline has no sampled line: '+node.GetName())
    points=line.GetAllPoints(); loops=[]; start=0
    line_data=line.GetTag(c4d.Tline).GetAllHighlevelData() if density>1 else None
    for segment in range(helper.GetSegmentCount()):
        closed=spline.GetSegment(segment)['closed'] if spline.GetSegmentCount() else spline.IsClosed()
        if not closed:raise GeometryError('All generated spline segments must be closed: '+node.GetName())
        count=helper.GetVertexCount(segment)
        loop=[]
        samples=points[start:start+count]
        refined=samples
        if density>1:
            # The line tag stores the exact natural parameter of each sample.
            # Inferring it from chord lengths drifts on non-uniform curves and
            # can put inserted samples behind their original endpoints.
            offsets=[entry['t'] for entry in line_data[start:start+count]]
            offsets.append(1.)
            refined=[]
            for i,p in enumerate(samples):
                refined.append(p)
                for j in range(1,density):
                    t=offsets[i]+(offsets[i+1]-offsets[i])*j/density
                    if spline[c4d.SPLINEOBJECT_TYPE]==c4d.SPLINETYPE_LINEAR:
                        refined.append(p+(samples[(i+1)%count]-p)*(j/density))
                    else:
                        refined.append(spline.GetSplinePoint(t,segment))
        for p in refined:
            q=matrix*p; loop.append((q.x,q.y,q.z))
        if len(loop)<3:raise GeometryError('Generated spline segment has fewer than three samples.')
        loops.append(loop); start+=count
    if start!=len(points):raise GeometryError('Generated spline segment sampling mismatch.')
    return loops


def sample_loops(child,generator,density=1):
    matrix=~generator.GetMg()*child.GetMg()
    direct=spline_loops(child,matrix,density)
    if direct is not None:return direct
    # Current State to Object evaluates the generator, rather than consuming
    # its unmodified input splines. Work only on a private document and clone.
    temporary=c4d.documents.BaseDocument()
    source_doc=generator.GetDocument()
    if source_doc:
        temporary.SetFps(source_doc.GetFps()); temporary.SetTime(source_doc.GetTime())
    clone=child.GetClone()
    clone.SetMl(matrix)
    temporary.InsertObject(clone)
    try:
        output=utils.SendModelingCommand(command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
                                         list=[clone],doc=temporary)
        if not isinstance(output,list) or not output:
            raise GeometryError('No evaluated spline output from '+child.GetName())
        loops=[]
        def visit(node,parent):
            transform=parent*node.GetMl()
            sampled=spline_loops(node,transform,density)
            if sampled is not None:
                loops.extend(sampled)
                return
            nested=node.GetDown()
            while nested:
                visit(nested,transform); nested=nested.GetNext()
        for root in output:visit(root,c4d.Matrix())
        if not loops:raise GeometryError('Generator must produce closed splines: '+child.GetName())
        return loops
    finally:
        c4d.documents.KillDocument(temporary)
