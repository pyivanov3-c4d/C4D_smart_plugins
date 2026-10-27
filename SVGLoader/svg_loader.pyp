"""SVG Loader: one flattened, centered, adaptive Bezier spline."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import c4d
from c4d import plugins, bitmaps, gui, storage

ROOT=Path(__file__).resolve().parent
PLUGIN_ID=1069989  # Local-use ID.


def build_spline(payload, matrix=None):
    contours=payload['contours']
    count=sum(len(contour) for contour in contours)
    if count==0: raise ValueError('No outlines were generated.')
    spline=c4d.SplineObject(count,c4d.SPLINETYPE_BEZIER)
    if not spline.ResizeObject(count,len(contours)):
        raise MemoryError('Could not allocate the spline.')
    spline.SetDefaultCoeff()
    points=[]
    index=0
    for segment,contour in enumerate(contours):
        spline.SetSegment(segment,len(contour),True)
        for knot in contour:
            # Compensate the axis rotation so the artwork stays visually unchanged.
            points.append(c4d.Vector(-knot['p'][1],0,knot['p'][0]))
            # C4D evaluates stored tangents at 4/3 their length. Convert from
            # conventional SVG cubic handles, as in our other spline adapters.
            spline.SetTangent(index,c4d.Vector(-knot['left'][1],0,knot['left'][0])*.75,
                              c4d.Vector(-knot['right'][1],0,knot['right'][0])*.75)
            index+=1
    spline.SetAllPoints(points)
    spline[c4d.SPLINEOBJECT_CLOSED]=True
    spline[c4d.SPLINEOBJECT_INTERPOLATION]=c4d.SPLINEOBJECT_INTERPOLATION_ADAPTIVE
    spline.SetName(payload['name'])
    if matrix is None:
        matrix=c4d.Matrix()
    if matrix is not None:
        # Orientation and position, without inheriting the selected object's scale.
        z=matrix.v3.GetNormalized()
        x=(matrix.v1-z*matrix.v1.Dot(z)).GetNormalized()
        if z.GetLength()<1e-9 or x.GetLength()<1e-9:
            raise ValueError('Selected object has a zero-scale axis.')
        # X down, Y toward the front (-reference Z), Z right.
        spline.SetMg(c4d.Matrix(matrix.off,z.Cross(x)*-1,z*-1,x))
    spline.Message(c4d.MSG_UPDATE)
    return spline


def worker_python():
    executable=Path(storage.GeGetStartupPath())/'resource'/'modules'/'python'/'libs'/'win64'/'python.exe'
    if not executable.is_file():
        raise RuntimeError('Cinema 4D bundled Python runtime was not found.')
    return str(executable)


class SVGLoader(plugins.CommandData):
    def Execute(self,doc):
        filename=storage.LoadDialog(title='Load SVG as one spline',
                    flags=c4d.FILESELECT_LOAD,force_suffix='svg')
        if not filename: return True
        if Path(filename).suffix.lower()!='.svg':
            gui.MessageDialog('Please select an SVG file.')
            return True
        selected=doc.GetActiveObject()
        matrix=c4d.Matrix(selected.GetMg()) if selected else c4d.Matrix()
        try:
            c4d.StatusSetSpin()
            c4d.StatusSetText('SVG Loader: converting vector strokes, masks and Boolean shapes...')
            with tempfile.TemporaryDirectory(prefix='svg-loader-') as folder:
                result_file=Path(folder)/'spline.json'
                completed=subprocess.run([worker_python(),str(ROOT/'convert.py'),filename,str(result_file)],
                          capture_output=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
                if completed.returncode:
                    raise RuntimeError(completed.stderr.decode('utf-8',errors='replace')[-2500:])
                spline=build_spline(json.loads(result_file.read_text(encoding='utf-8')),matrix)
            doc.StartUndo()
            try:
                doc.InsertObject(spline)
                doc.AddUndo(c4d.UNDOTYPE_NEWOBJ,spline)
                doc.SetActiveObject(spline,c4d.SELECTION_NEW)
            finally:
                doc.EndUndo()
            c4d.EventAdd()
        except Exception as error:
            gui.MessageDialog('SVG Loader could not import this file:\n\n'+str(error))
        finally:
            c4d.StatusClear()
        return True


if __name__=='__main__':
    icon=bitmaps.BaseBitmap()
    if icon.InitWith(str(ROOT/'res'/'icon.png'))[0]!=c4d.IMAGERESULT_OK:
        icon=None
    if not plugins.RegisterCommandPlugin(PLUGIN_ID,'SVG Loader',0,icon,
               'Load visible SVG artwork into a single centered spline.',SVGLoader()):
        raise RuntimeError('SVG Loader could not register; check for plugin ID conflicts.')
