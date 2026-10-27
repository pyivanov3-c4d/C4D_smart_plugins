"""smartBoolean 1.0.21 — local bevel collision limits."""
import math
import os
import sys
import traceback
import c4d
from c4d import plugins, bitmaps, documents, utils

PLUGIN_ID = 1069992  # Local installation ID; obtain an official ID before distribution.
MODE, WIDTH, SUBDIVISION, ROUNDNESS = 1000, 1001, 1002, 1003
POINTS_REMOVE = 1004
CONVERT_HIDE = 1005
BOOLEAN_ID = 1060679
SEAM = 'smartBoolean intersections'
STATUS = 1099001
ROOT = os.path.dirname(__file__)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import smartboolean_cleanup as cleanup
import smartboolean_retopology as retopology
import smartboolean_limits as side_limits
import smartboolean_collision as collision
import smartboolean_progress as progress_ui
import smartboolean_weld as collision_weld
import smartboolean_selections as selection_transfer


def command(doc, mesh, cmd, settings=None, mode=None):
    job=progress_ui.current()
    if job:job.check()
    result=utils.SendModelingCommand(
        command=cmd, list=[mesh], doc=doc,
        mode=c4d.MODELINGCOMMANDMODE_ALL if mode is None else mode,
        bc=settings if settings is not None else c4d.BaseContainer())
    if job:job.check()
    return result


def chamfer_command(doc, mesh, settings):
    # Native bevel can propagate source Phong breaks onto newly created rows,
    # even with both break-generation options disabled. Keep only untouched
    # source edges; clear both polygon-side representations on the chamfer.
    def edge_keys(obj):
        points=[(p.x,p.y,p.z) for p in obj.GetAllPoints()]
        return {4*i+j:tuple(sorted((points[a],points[b])))
                for i,p in enumerate(obj.GetAllPolygons())
                for j,(a,b) in enumerate(edge_vertices(p)) if a!=b}
    old_breaks=mesh.GetPhongBreak()
    retained={key for index,key in edge_keys(mesh).items()
              if old_breaks.IsSelected(index)}
    result=command(doc,mesh,c4d.ID_XBEVELTOOL,settings,c4d.MODELINGCOMMANDMODE_EDGESELECTION)
    if result is not False:
        breaks=mesh.GetPhongBreak()
        for index,key in edge_keys(mesh).items():
            if key not in retained:breaks.Deselect(index)
    return result


def polygons(root):
    """Yield polygon leaves, preserving accumulated local transforms."""
    def visit(node, matrix):
        while node:
            local = matrix * node.GetMl()
            if node.CheckType(c4d.Opolygon):
                yield node, local
            yield from visit(node.GetDown(), local)
            node = node.GetNext()
    # A modeling command may return siblings both as a chain and in its list.
    # Visit only this root's subtree to avoid duplicating those siblings.
    matrix = root.GetMl()
    if root.CheckType(c4d.Opolygon):
        yield root, matrix
    yield from visit(root.GetDown(), matrix)


def one_mesh(doc, roots):
    leaves = []
    for root in roots:
        for node, matrix in polygons(root):
            clone = node.GetClone(c4d.COPYFLAGS_NO_HIERARCHY)
            clone.SetMl(matrix)
            doc.InsertObject(clone)
            leaves.append(clone)
    if not leaves:
        return c4d.PolygonObject(0, 0)
    if len(leaves) == 1:
        mesh = leaves[0]
    else:
        joined = utils.SendModelingCommand(command=c4d.MCOMMAND_JOIN,
            list=leaves, doc=doc, mode=c4d.MODELINGCOMMANDMODE_ALL,
            bc=c4d.BaseContainer())
        if not isinstance(joined, list) or len(joined) != 1:
            raise RuntimeError('Could not combine Boolean result into one mesh.')
        mesh = joined[0]
        if mesh.GetDocument() is None:
            doc.InsertObject(mesh)
    # Generator output is expressed in generator-local coordinates.
    matrix = mesh.GetMl()
    mesh.SetAllPoints([matrix * p for p in mesh.GetAllPoints()])
    mesh.SetMl(c4d.Matrix())
    mesh.Message(c4d.MSG_UPDATE)
    return mesh


def edge_vertices(poly):
    return ((poly.a, poly.b), (poly.b, poly.c),
            (poly.c, poly.d), (poly.d, poly.a))


def seam_selection(mesh):
    selection = mesh.GetEdgeS()
    selection.DeselectAll()
    for tag in mesh.GetTags():
        if tag.CheckType(c4d.Tedgeselection) and tag.GetName() == SEAM:
            selection.Merge(tag.GetBaseSelect())
    # Synchronize the two polygon-side representations of each selected edge.
    edges = set()
    polys = mesh.GetAllPolygons()
    for i, poly in enumerate(polys):
        for j, (a, b) in enumerate(edge_vertices(poly)):
            if a != b and selection.IsSelected(4*i+j):
                edges.add(tuple(sorted((a, b))))
    for i, poly in enumerate(polys):
        for j, (a, b) in enumerate(edge_vertices(poly)):
            if a != b and tuple(sorted((a, b))) in edges:
                selection.Select(4*i+j)
    return len(edges)


def sound_mesh(mesh, require_closed=False):
    """Reject NaNs, collapsed faces and newly opened/nonmanifold results."""
    points = mesh.GetAllPoints()
    if not points or not mesh.GetPolygonCount():
        return False
    if any(not math.isfinite(v) for p in points for v in (p.x, p.y, p.z)):
        return False
    incidence = {}
    for poly in mesh.GetAllPolygons():
        ids = [poly.a, poly.b, poly.c] if poly.c == poly.d else [poly.a, poly.b, poly.c, poly.d]
        if len(set(ids)) != len(ids) or any(i < 0 or i >= len(points) for i in ids):
            return False
        for a, b in zip(ids, ids[1:]+ids[:1]):
            key = tuple(sorted((a, b)))
            incidence[key] = incidence.get(key, 0) + 1
    if any(n > 2 for n in incidence.values()):
        return False
    return not require_closed or all(n == 2 for n in incidence.values())


def mesh_arrays(mesh):
    points = [(p.x, p.y, p.z) for p in mesh.GetAllPoints()]
    faces = [(p.a,p.b,p.c) if p.c == p.d else (p.a,p.b,p.c,p.d)
             for p in mesh.GetAllPolygons()]
    return points, faces


def selected_keys(mesh):
    selection = mesh.GetEdgeS()
    return {tuple(sorted((a,b))) for i,p in enumerate(mesh.GetAllPolygons())
            for j,(a,b) in enumerate(edge_vertices(p))
            if a != b and selection.IsSelected(4*i+j)}


def restore_seam(mesh, spans, tolerance):
    """Rebuild selection from geometry, not indices invalidated by welding/melting."""
    points, faces = mesh_arrays(mesh)
    lookup = cleanup.Segments(spans, tolerance)
    selection = mesh.GetEdgeS()
    selection.DeselectAll()
    count = 0
    for (a,b), sides in cleanup.edge_map(faces).items():
        if len(sides) != 2 or not lookup.contains_edge(points[a],points[b],tolerance):
            continue
        for i,j in sides: selection.Select(4*i+j)
        count += 1
    # Internal n-gon diagonals must not become bevel edges.
    mesh.ValidateEdgeSelection(selection)
    for tag in mesh.GetTags():
        if tag.CheckType(c4d.Tedgeselection) and tag.GetName() == SEAM:
            tag.Remove()
    tag = mesh.MakeTag(c4d.Tedgeselection)
    tag.SetName(SEAM)
    selection.CopyTo(tag.GetBaseSelect())
    return count


def prepare_bevel_legacy(doc, mesh, width):
    points, faces = mesh_arrays(mesh)
    tolerance = max(1e-8, mesh.GetRad().GetLength()*1e-9)
    keys = selected_keys(mesh)
    indices, spans = cleanup.dissolve_band(points, faces, keys, width, tolerance)
    if not indices:
        return mesh
    candidate = mesh.GetClone()
    doc.InsertObject(candidate)
    selection = candidate.GetEdgeS()
    selection.DeselectAll()
    for index in indices: selection.Select(index)
    # Native Melt joins each coplanar patch into an n-gon while retaining its
    # full outer boundary. Those shared vertices reconnect to the untouched grid.
    result = command(doc, candidate, c4d.MCOMMAND_MELT,
                     mode=c4d.MODELINGCOMMANDMODE_EDGESELECTION)
    if result is False or not sound_mesh(candidate, sound_mesh(mesh, True)):
        candidate.Remove()
        return mesh
    optimize(doc, candidate)
    restore_seam(candidate, spans, tolerance)
    if not selected_keys(candidate):
        candidate.Remove()
        return mesh
    return candidate


def topology_tags_supported(mesh):
    # Preserve arbitrary vertex/polygon attributes rather than silently dropping
    # them during a rebuild. Such meshes keep the native conservative path.
    # GetTags includes the intrinsic point/polygon storage tags. array_mesh
    # recreates them through PolygonObject/SetAllPoints/SetPolygon; they are
    # not custom attributes and must never force the legacy cleanup path.
    allowed={c4d.Tpoint,c4d.Tpolygon,c4d.Tphong,c4d.Tnormal,
             c4d.Tedgeselection,5673,c4d.Ttexture,c4d.Tuvw}
    return all(tag.GetType() in allowed and
               (not tag.CheckType(c4d.Ttexture) or not tag[c4d.TEXTURETAG_RESTRICTION])
               for tag in mesh.GetTags())


def array_mesh(doc, source, points, faces):
    source_points,source_faces=mesh_arrays(source)
    textured=any(t.CheckType(c4d.Ttexture) for t in source.GetTags())
    uv_tags=[]
    selection_tags=[]
    selection_cache={}
    for tag in source.GetTags():
        kind=tag.GetType()
        if kind not in (c4d.Tedgeselection,5673):continue
        if kind==c4d.Tedgeselection and tag.GetName()==SEAM:continue
        limit=len(source_faces)*(4 if kind==c4d.Tedgeselection else 1)
        selected={i for i in range(limit) if tag.GetBaseSelect().IsSelected(i)}
        transfer=selection_transfer.edges if kind==c4d.Tedgeselection else selection_transfer.polygons
        job=progress_ui.current()
        if job:job.stage('Preserving Extrude selections')
        cache_key=(kind,frozenset(selected))
        if cache_key not in selection_cache:
            selection_cache[cache_key]=transfer(source_points,source_faces,points,faces,selected,max(1e-8,source.GetRad().GetLength()*1e-9)) if selected else []
        mapped=selection_cache[cache_key]
        clone=tag.GetClone();clone.GetBaseSelect().DeselectAll()
        for i in mapped:clone.GetBaseSelect().Select(i)
        selection_tags.append(clone)
    for tag in source.GetTags():
        if not tag.CheckType(c4d.Tuvw): continue
        uv=[]
        for i,face in enumerate(source_faces):
            values=tag.GetSlow(i)
            uv.append([(values[k].x,values[k].y,values[k].z) for k in 'abcd'[:len(face)]])
        tolerance=max(1e-8,source.GetRad().GetLength()*1e-9)
        try:
            mapped=retopology.transfer_uv(source_points,source_faces,uv,points,faces,tolerance)
        except ValueError:
            if textured: raise
            # No material consumes this UV tag. Preserve unchanged faces and
            # extend a planar source chart over only the rebuilt faces.
            mapped=retopology.transfer_uv(source_points,source_faces,uv,points,faces,tolerance,strict=False)
        uv_tags.append((tag,mapped))
    out=c4d.PolygonObject(len(points),len(faces))
    out.SetAllPoints([c4d.Vector(*p) for p in points])
    for tag in selection_tags:out.InsertTag(tag)
    for i,face in enumerate(faces): out.SetPolygon(i,c4d.CPolygon(*face))
    for tag in source.GetTags():
        if tag.CheckType(c4d.Tphong) or tag.CheckType(c4d.Ttexture):
            out.InsertTag(tag.GetClone())
        elif tag.CheckType(c4d.Tuvw):
            mapped=next(data for original,data in uv_tags if original==tag)
            new_tag=c4d.UVWTag(len(faces))
            new_tag.SetName(tag.GetName())
            for i,values in enumerate(mapped):
                corners=[c4d.Vector(*v) for v in values]
                if len(corners)==3: corners.append(corners[-1])
                new_tag.SetSlow(i,*corners)
            out.InsertTag(new_tag)
    out.SetMl(source.GetMl())
    if source[STATUS] is not None: out[STATUS]=source[STATUS]
    out.Message(c4d.MSG_UPDATE)
    doc.InsertObject(out)
    return out


def prepare_bevel(doc, mesh, width):
    def fallback(reason):
        result=prepare_bevel_legacy(doc,mesh,width)
        result[STATUS]='1.0.21 / legacy: '+reason
        return result
    if not topology_tags_supported(mesh):
        print('smartBoolean: attribute-bearing input uses conservative native cleanup.')
        return fallback('unsupported attribute tag')
    points,faces=mesh_arrays(mesh)
    tolerance=max(1e-8,mesh.GetRad().GetLength()*1e-9)
    try:
        points,faces,origins,spans=retopology.rebuild(points,faces,selected_keys(mesh),width,tolerance)
        candidate=array_mesh(doc,mesh,points,faces)
    except ValueError as error:
        print('smartBoolean: local rebuild unavailable:',error)
        return fallback(str(error))
    selection=candidate.GetEdgeS()
    normals=[retopology.normal(points,f) for f in faces]
    for edge,sides in cleanup.edge_map(faces).items():
        if len(sides)!=2 or any(origins[i]!=-1 for i,j in sides): continue
        if cleanup.dot(normals[sides[0][0]],normals[sides[1][0]])<1.-1e-10: continue
        for i,j in sides: selection.Select(i*4+j)
    # These temporary planar patches allow the bevel offset to cross the old
    # small cells. Their boundaries now have uniform, reduced seam stations.
    if command(doc,candidate,c4d.MCOMMAND_MELT,mode=c4d.MODELINGCOMMANDMODE_EDGESELECTION) is False:
        candidate.Remove(); return fallback('native Melt failed')
    restore_seam(candidate,spans,tolerance)
    if not sound_mesh(candidate,sound_mesh(mesh,True)) or not selected_keys(candidate):
        candidate.Remove(); return fallback('post-Melt topology or seam validation failed')
    candidate[STATUS]='1.0.21 / rebuilt seam: %d edges'%len(selected_keys(candidate))
    return candidate


def finish_bevel(doc, mesh, require_closed=False):
    if not topology_tags_supported(mesh): return mesh
    groups={}
    if mesh.GetNgonCount():
        count,mapping=mesh.GetPolygonTranslationMap()
        if len(mapping)!=mesh.GetPolygonCount(): return mesh
        for i,group in enumerate(mapping): groups.setdefault(group,[]).append(i)
    points,faces=mesh_arrays(mesh)
    tolerance=max(1e-8,mesh.GetRad().GetLength()*1e-9)
    rebuilt=retopology.finish_patches(points,faces,groups.values(),tolerance)
    try: rebuilt=retopology.remove_collapsed_faces(points,rebuilt,tolerance)
    except ValueError as error:
        mesh[STATUS]=str(mesh[STATUS])+' / collapsed transition repair rejected: '+str(error)
        return mesh
    try: result=array_mesh(doc,mesh,points,rebuilt)
    except ValueError as error:
        print('smartBoolean: preserving native UV transition:',error)
        mesh[STATUS]=str(mesh[STATUS])+' / transition UV fallback: '+str(error)
        return mesh
    if not sound_mesh(result,require_closed):
        mesh[STATUS]=str(mesh[STATUS])+' / transition topology rejected'
        result.Remove(); return mesh
    result[STATUS]=str(result[STATUS])+' / explicit transitions'
    optimize(doc,result)
    return result


def optimize(doc, mesh):
    # Relative, deliberately tiny tolerance: don't weld nearby intentional features.
    radius = mesh.GetRad().GetLength()
    bc = c4d.BaseContainer()
    bc[c4d.MDATA_OPTIMIZE_TOLERANCE] = max(1e-9, radius * 1e-10)
    bc[c4d.MDATA_OPTIMIZE_POINTS] = True
    bc[c4d.MDATA_OPTIMIZE_POLYGONS] = True
    bc[c4d.MDATA_OPTIMIZE_UNUSEDPOINTS] = True
    if command(doc, mesh, c4d.MCOMMAND_OPTIMIZE, bc) is False:
        raise RuntimeError('Optimize failed.')


def weld_bevel_contacts(doc, mesh, first, second, setup):
    job=progress_ui.current()
    if job:job.stage('Welding bevel contact points')
    points,faces=mesh_arrays(mesh)
    try:
        welded,mapping,rebuilt=collision_weld.resolve(points,first,second,faces,setup,
                                                     job.count if job else None)
    except ValueError as error:
        mesh[STATUS]=str(mesh[STATUS])+' / contact weld rejected: '+str(error)
        return mesh
    if not mapping:return mesh
    candidate=mesh.GetClone();doc.InsertObject(candidate)
    candidate.SetAllPoints([c4d.Vector(*p) for p in welded])
    candidate.Message(c4d.MSG_UPDATE)
    try:
        # Snap only identified contact groups, then let C4D weld coincident
        # points and discard collapsed faces while maintaining native tags.
        optimize(doc,candidate)
        if not sound_mesh(candidate,sound_mesh(mesh,True)):
            candidate.Remove()
            mesh[STATUS]=str(mesh[STATUS])+' / native contact weld rejected'
            return mesh
    except Exception:
        candidate.Remove()
        raise
    candidate[STATUS]=str(mesh[STATUS])+' / welded %d contact points'%len(mapping)
    mesh.Remove()
    return candidate


def bevel(doc, mesh, width, strips, roundness, points_remove=False):
    job=progress_ui.current()
    if width <= 0 or not seam_selection(mesh):
        return mesh
    original=mesh
    limiter=None
    collision_setup=None
    requested_width=width
    if points_remove:
        if job:job.stage('Cleaning points and rebuilding connections')
        mesh = prepare_bevel(doc, mesh, width)
    else:
        if job:job.stage('Measuring bevel clearance')
        points,faces=mesh_arrays(mesh)
        tolerance=max(1e-8,mesh.GetRad().GetLength()*1e-9)
        keys=selected_keys(mesh)
        width=side_limits.planar_clearance(points,faces,keys,tolerance,width)
        limiter=side_limits.plan(points,faces,keys,width,tolerance)
        if limiter:
            mesh=mesh.GetClone();doc.InsertObject(mesh)
            mesh.SetAllPoints([c4d.Vector(*p) for p in side_limits.transform(points,limiter)])
            mesh.Message(c4d.MSG_UPDATE)
        mesh[STATUS]='1.0.21 / Points Remove off / independent extrusion limit' if limiter else '1.0.21 / Points Remove off'
        source_points,source_faces=mesh_arrays(mesh)
        collision_setup=collision.plan(source_points,source_faces,keys,width,tolerance,
                                       progress=job.count if job else None)
    closed = sound_mesh(mesh, True)
    candidate = mesh.GetClone()
    doc.InsertObject(candidate)
    # Explicit normals refer to pre-bevel topology. Rebuild with Phong instead.
    for tag in candidate.GetTags():
        if tag.CheckType(c4d.Tnormal):
            tag.Remove()
    bc = c4d.BaseContainer()
    bc[c4d.MDATA_BEVEL_MASTER_MODE] = c4d.MDATA_BEVEL_MASTER_MODE_CHAMFER
    bc[c4d.MDATA_BEVEL_OFFSET_MODE] = c4d.MDATA_BEVEL_OFFSET_MODE_FIXED
    bc[c4d.MDATA_BEVEL_RADIUS] = collision_setup['reference'] if collision_setup else width
    bc[c4d.MDATA_BEVEL_SUB] = float(strips - 1)
    bc[c4d.MDATA_BEVEL_DEPTH] = roundness
    bc[c4d.MDATA_BEVEL_LIMIT] = False
    bc[c4d.MDATA_BEVEL_EXTRUSION] = 0.0
    bc[c4d.MDATA_BEVEL_SHAPING_MODE] = c4d.MDATA_BEVEL_SHAPING_MODE_ROUND
    bc[c4d.MDATA_BEVEL_SHAPING_TENSION] = 1.0
    bc[c4d.MDATA_BEVEL_MITERING] = c4d.MDATA_BEVEL_MITERING_UNIFORM
    bc[c4d.MDATA_BEVEL_CORNER_ENDING] = c4d.MDATA_BEVEL_CORNER_ENDING_DEFAULT
    bc[c4d.MDATA_BEVEL_PROUNDING_TYPE] = c4d.MDATA_BEVEL_PROUNDING_TYPE_FLAT
    bc[c4d.MDATA_BEVEL_CORNER_NGON] = False
    bc[c4d.MDATA_BEVEL_ROUNDING_NGON] = False
    # Do not inherit tool defaults which break the new chamfer borders/miters.
    bc[c4d.MDATA_BEVEL_SELECTION_PHONG_BREAK] = False
    bc[c4d.MDATA_BEVEL_SELECTION_PHONG_BREAK_M] = False
    if job:job.stage('Calculating native bevel')
    success = chamfer_command(doc, candidate, bc)
    if success is not False and collision_setup:
        second=mesh.GetClone();doc.InsertObject(second)
        for tag in second.GetTags():
            if tag.CheckType(c4d.Tnormal):tag.Remove()
        bc[c4d.MDATA_BEVEL_RADIUS]=collision_setup['reference']*2
        if job:job.stage('Calculating reference bevel')
        second_ok=chamfer_command(doc,second,bc)
        expanded=None
        if second_ok is not False:
            first_points,first_faces=mesh_arrays(candidate)
            second_points,_=mesh_arrays(second)
            expanded=collision.expand(first_points,second_points,collision_setup,first_faces,
                                       progress=job.count if job else None)
        second.Remove()
        if expanded is not None:
            candidate.SetAllPoints([c4d.Vector(*p) for p in expanded])
            candidate.Message(c4d.MSG_UPDATE)
            candidate[STATUS]=str(mesh[STATUS])+(' / spatial boundary limits' if collision_setup.get('spatial') else ' / local corner collision limits')
            candidate=weld_bevel_contacts(doc,candidate,first_points,second_points,collision_setup)
        else:
            # Unsupported native correspondence: retain the established path,
            # never substitute the small reference bevel for the requested width.
            candidate.Remove();candidate=mesh.GetClone();doc.InsertObject(candidate)
            for tag in candidate.GetTags():
                if tag.CheckType(c4d.Tnormal):tag.Remove()
            bc[c4d.MDATA_BEVEL_RADIUS]=width
            if job:job.stage('Calculating native bevel fallback')
            success=chamfer_command(doc,candidate,bc)
            candidate[STATUS]=str(mesh[STATUS])+' / local collision mapping unavailable'
    if success is not False:
        if job:job.stage('Finishing bevel topology')
        result=finish_bevel(doc,candidate,closed) if points_remove else candidate
        if sound_mesh(result,closed):
            if limiter:
                points,_=mesh_arrays(result)
                result.SetAllPoints([c4d.Vector(*p) for p in side_limits.transform(points,limiter,True)])
                result.Message(c4d.MSG_UPDATE)
            result[STATUS]=str(result[STATUS])+' / requested width: %g / flat side: %g'%(requested_width,width)
            return result
    candidate.Remove()
    mesh[STATUS]=str(mesh[STATUS])+' / requested width failed; no smaller bevel substituted'
    print('smartBoolean: requested bevel width failed; returning the unchamfered Boolean mesh.')
    return mesh if points_remove else original


def object_tree(root):
    """Visit only this object and its descendants, never its siblings."""
    yield root
    child = root.GetDown()
    while child:
        yield from object_tree(child)
        child = child.GetNext()


def convert_and_hide(op):
    job=progress_ui.Progress()
    try:
        job.stage('Converting current state')
        return _convert_and_hide(op)
    finally:
        job.close()


def _convert_and_hide(op):
    doc = op.GetDocument()
    if doc is None:
        raise RuntimeError('The generator must be in a scene.')
    if not c4d.threading.GeIsMainThread():
        raise RuntimeError('Convert and hide must run from the Attributes panel.')
    c4d.StopAllThreads()
    # Evaluate before touching the source's enabled or visibility flags.
    result = command(doc, op, c4d.MCOMMAND_CURRENTSTATETOOBJECT)
    if not isinstance(result, list) or len(result) != 1:
        raise RuntimeError('Current State to Object did not return one result. The generator was kept unchanged.')
    copy = result[0]
    if not any(node.CheckType(c4d.Opolygon) and node.GetPolygonCount() > 0
               for node in object_tree(copy)):
        raise RuntimeError('The converted result is empty. The generator was kept unchanged.')
    copy.SetName(op.GetName() + ' (converted)')
    copy.SetMl(op.GetMl())
    copy.SetEditorMode(c4d.MODE_UNDEF)
    copy.SetRenderMode(c4d.MODE_UNDEF)
    doc.StartUndo()
    try:
        doc.InsertObject(copy, parent=op.GetUp(), pred=op)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, copy)
        for node in object_tree(op):
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, node)
            node.SetDeformMode(False)
            node.SetEditorMode(c4d.MODE_OFF)
            node.SetRenderMode(c4d.MODE_OFF)
        doc.SetActiveObject(copy, c4d.SELECTION_NEW)
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return copy


class SmartBoolean(plugins.ObjectData):
    def Message(self, op, message, data):
        if (message == c4d.MSG_DESCRIPTION_COMMAND and data
                and data['id'][0].id == CONVERT_HIDE):
            try:
                convert_and_hide(op)
            except Exception as error:
                traceback.print_exc()
                c4d.gui.MessageDialog('Convert and hide: ' + str(error))
        return True

    def Init(self, op, isCloneInit=False):
        for kind, field in ((int, MODE), (float, WIDTH), (int, SUBDIVISION), (float, ROUNDNESS), (bool, POINTS_REMOVE)):
            self.InitAttr(op, kind, [field])
        if not isCloneInit:
            op[MODE], op[WIDTH], op[SUBDIVISION], op[ROUNDNESS] = 1, 0.0, 3, 1.0
            op[POINTS_REMOVE] = False
        return True

    def GetVirtualObjects(self, op, hh):
        if op.GetDown() is None:
            return c4d.PolygonObject(0, 0)
        hierarchy = op.GetAndCheckHierarchyClone(hh, op.GetDown(),
                    c4d.HIERARCHYCLONEFLAGS_ASPOLY, True)
        if not hierarchy:
            return c4d.PolygonObject(0, 0)
        if not hierarchy['dirty']:
            return hierarchy['clone']
        job=progress_ui.Progress(c4d.threading.GeGetCurrentThread())
        temp = None
        try:
            job.stage('Evaluating Boolean geometry')
            temp = documents.BaseDocument()
            source_doc = op.GetDocument()
            if source_doc:
                temp.SetFps(source_doc.GetFps())
                temp.SetTime(source_doc.GetTime())
            clone = hierarchy['clone']
            if clone is None:
                return c4d.PolygonObject(0, 0)
            # allchildren=True supplies a container for the cloned input chain.
            # With one input, flatten the entire returned subtree either way.
            if op.GetDown().GetNext() is None:
                temp.InsertObject(clone)
                mesh = one_mesh(temp, [clone])
            else:
                boolean = c4d.BaseObject(BOOLEAN_ID)
                if boolean is None:
                    raise RuntimeError('Cinema 4D 2026 Boolean is required.')
                boolean[1001] = max(1, min(3, int(op[MODE])))
                boolean[1002] = True
                boolean[1010] = True
                boolean[1006] = True
                boolean[1007] = SEAM
                temp.InsertObject(boolean)
                child = clone.GetDown()
                if child is None:
                    raise RuntimeError('The cloned input hierarchy contains no operands.')
                while child:
                    following = child.GetNext()
                    child.Remove()
                    child.InsertUnderLast(boolean)
                    child = following
                result = command(temp, boolean, c4d.MCOMMAND_CURRENTSTATETOOBJECT)
                if not isinstance(result, list):
                    raise RuntimeError('Native Boolean evaluation failed.')
                mesh = one_mesh(temp, result)
            if mesh.GetDocument() is None:
                temp.InsertObject(mesh)
            # Save geometric spans before Optimize can renumber edge selections.
            spans = []
            job.stage('Preparing intersection edges')
            tolerance = max(1e-8, mesh.GetRad().GetLength()*1e-9)
            if seam_selection(mesh):
                points, _ = mesh_arrays(mesh)
                spans = cleanup.straight_segments(points, selected_keys(mesh), tolerance)
            optimize(temp, mesh)
            if spans:
                restore_seam(mesh, spans, tolerance)
            if op.GetDown().GetNext() is not None:
                mesh = bevel(temp, mesh, max(0.0, float(op[WIDTH])),
                             max(1, min(128, int(op[SUBDIVISION]))),
                             max(-1.0, min(1.0, float(op[ROUNDNESS]))),
                             bool(op[POINTS_REMOVE]))
            job.stage('Finalizing mesh')
            mesh.GetEdgeS().DeselectAll()
            mesh.GetPolygonS().DeselectAll()
            mesh.GetPointS().DeselectAll()
            mesh.SetName('smartBoolean')
            if mesh.GetTag(c4d.Tphong) is None:
                mesh.MakeTag(c4d.Tphong)
            mesh.SetPhong(True, True, math.radians(40.0))
            mesh.Remove()
            mesh.Message(c4d.MSG_UPDATE)
            return mesh
        except progress_ui.Cancelled:
            # Never commit a cancelled calculation as a valid empty cache.
            return None
        except Exception:
            traceback.print_exc()
            return c4d.PolygonObject(0, 0)
        finally:
            try:
                if temp is not None:documents.KillDocument(temp)
            finally:
                job.close()


if __name__ == '__main__':
    if not progress_ui.register_progress():
        raise RuntimeError('smartBoolean progress registration failed: local plugin ID collision.')
    icon = bitmaps.BaseBitmap()
    if icon.InitWith(os.path.join(ROOT, 'res', 'icon.png'))[0] != c4d.IMAGERESULT_OK:
        icon = None
    if not plugins.RegisterObjectPlugin(PLUGIN_ID, 'smartBoolean', SmartBoolean,
            'Osmartboolean', c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT, icon):
        raise RuntimeError('smartBoolean registration failed: local plugin ID collision.')






