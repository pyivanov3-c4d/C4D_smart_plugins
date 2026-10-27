import importlib.util
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]/'SVGLoader'
spec=importlib.util.spec_from_file_location('svg_convert',ROOT/'convert.py')
converter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


def render_bitmap(svg, target):
    subprocess.run([str(ROOT/'vendor'/'node.exe'),str(ROOT/'render.cjs'),str(svg),str(target),'2048'],
                   check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    return target.read_bytes()


def reconstructed(payload,width,height):
    b=payload['bounds']; cx=(b[0]+b[2])/2; cy=(b[1]+b[3])/2
    def p(k,v=None):
        v=v or [0,0]
        return '%0.9f,%0.9f'%(k['p'][0]+v[0]+cx,-k['p'][1]-v[1]-cy)
    paths=[]
    for contour in payload['contours']:
        commands=['M'+p(contour[0])]
        for i,knot in enumerate(contour):
            next_knot=contour[(i+1)%len(contour)]
            commands.append('C%s %s %s'%(p(knot,knot['right']),p(next_knot,next_knot['left']),p(next_knot)))
        paths.append(' '.join(commands)+'Z')
    return '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s"><path fill="black" d="%s"/></svg>'%(width,height,' '.join(paths))


class SvgConversionTests(unittest.TestCase):
    def test_smooth_circle_and_stroked_ring(self):
        for shape,expected in [('<circle cx="50" cy="50" r="35"/>',1),
                               ('<circle cx="50" cy="50" r="35" fill="none" stroke="black" stroke-width="6"/>',2)]:
            with tempfile.TemporaryDirectory() as folder:
                svg=Path(folder)/'circle.svg'
                svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'+shape+'</svg>')
                payload=converter.convert(svg,8192)
            self.assertEqual(len(payload['contours']),expected)
            for contour in payload['contours']:
                self.assertGreaterEqual(len(contour),4)
                self.assertLess(len(contour),40)
                radii=[math.hypot(*k['p']) for k in contour]
                # SVG circles normalize to standard four cubic arcs (max radial
                # error ~0.0273%); stroke offsets follow those original curves.
                self.assertLess(max(radii)-min(radii),max(radii)*0.00035+0.002)
                self.assertTrue(min(abs(radii[0]-r) for r in ([35] if expected==1 else [32,38]))<0.02)
                for k in contour:
                    left,right=k['left'],k['right']
                    cross=left[0]*right[1]-left[1]*right[0]
                    self.assertAlmostEqual(cross,0,delta=0.002)

    def test_polygon_is_not_replaced_with_circle(self):
        points=' '.join('%s,%s'%(50+30*math.cos(i*math.pi/4),50+30*math.sin(i*math.pi/4)) for i in range(8))
        payload=self.convert_source('<polygon points="'+points+'"/>')
        self.assertEqual(len(payload['contours'][0]),8)
        self.assertTrue(all(k['left']==[0,0] and k['right']==[0,0] for k in payload['contours'][0]))

    def convert_source(self,body):
        with tempfile.TemporaryDirectory() as folder:
            svg=Path(folder)/'vector.svg'
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'+body+'</svg>',encoding='utf-8')
            return converter.convert(svg)

    def assert_roundtrip(self,body):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);svg=folder/'source.svg';rebuilt=folder/'rebuilt.svg'
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'+body+'</svg>',encoding='utf-8')
            payload=converter.convert(svg)
            rebuilt.write_text(reconstructed(payload,100,100))
            original=render_bitmap(svg,folder/'a.bin');result=render_bitmap(rebuilt,folder/'b.bin')
            intersection=sum((a&b).bit_count() for a,b in zip(original,result))
            union=sum((a|b).bit_count() for a,b in zip(original,result))
            self.assertGreater(intersection/union,0.995)
            return payload

    def test_vector_compositing(self):
        cases={
            'overlap_white_and_black_repaint':'<circle cx="35" cy="50" r="25"/><circle cx="65" cy="50" r="25"/><g><rect x="40" y="10" width="20" height="80" fill="white"/><circle cx="50" cy="50" r="10"/></g>',
            'even_odd':'<path fill-rule="evenodd" d="M10 10H90V90H10Z M30 30H70V70H30Z"/>',
            'object_bbox_clip':'<defs><clipPath id="a" clipPathUnits="objectBoundingBox"><path clip-rule="evenodd" d="M0 0H1V1H0Z M.2 .2H.8V.8H.2Z"/></clipPath></defs><rect x="10" y="20" width="70" height="40" clip-path="url(#a)"/>',
            'object_bbox_mask':'<defs><mask id="a" maskContentUnits="objectBoundingBox"><rect width="1" height="1" fill="white"/><circle cx=".5" cy=".5" r=".25"/></mask></defs><rect x="10" y="20" width="70" height="40" mask="url(#a)"/>',
            'alpha_mask':'<defs><mask id="a" mask-type="alpha" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100"><circle cx="50" cy="50" r="30" fill="black"/></mask></defs><rect width="100" height="100" mask="url(#a)"/>',
            'transformed_stroke':'<g transform="translate(30 20) rotate(20) scale(1.2 .6)"><path d="M0 0C10 70 40 -10 50 50" fill="none" stroke="black" stroke-width="7" stroke-linecap="round"/></g>',
            'round_join':'<path d="M15 80L50 20L85 80" fill="none" stroke="black" stroke-width="12" stroke-linejoin="round" stroke-linecap="round"/>',
            'square_bevel':'<path d="M15 80L50 20L85 80" fill="none" stroke="black" stroke-width="12" stroke-linejoin="bevel" stroke-linecap="square"/>',
            'dashed':'<path d="M10 30H90M10 60H90" fill="none" stroke="black" stroke-width="4" stroke-dasharray="5 2 1 2" stroke-dashoffset="3"/>',
            'paint_order':'<path d="M10 10L80 50L10 80Z" stroke="white" stroke-width="10" paint-order="stroke"/>',
            'transformed_clip':'<defs><clipPath id="a"><circle cx="30" cy="30" r="20"/></clipPath></defs><g transform="translate(20 5) rotate(10)" clip-path="url(#a)"><rect width="60" height="60"/></g>',
            'use_and_css':'<style>.outline {fill:none;stroke:black;stroke-width:5}</style><defs><path id="p" d="M10 10L30 30L10 40Z"/></defs><use href="#p" class="outline"/><use href="#p" x="40" y="30"/>',
            'nested_island':'<circle cx="50" cy="50" r="45"/><circle cx="50" cy="50" r="32" fill="white"/><circle cx="50" cy="50" r="20"/><circle cx="50" cy="50" r="8" fill="white"/>',
            'clipped_white_group':'<defs><clipPath id="c"><circle cx="50" cy="50" r="25"/></clipPath></defs><rect x="10" y="10" width="80" height="80"/><g clip-path="url(#c)"><rect width="100" height="100" fill="white"/></g>',
            'mask_region':'<defs><mask id="m" maskUnits="userSpaceOnUse" x="30" y="20" width="40" height="60"><rect width="100" height="100" fill="white"/></mask></defs><circle cx="50" cy="50" r="40" mask="url(#m)"/>',
            'arc_ellipse':'<path d="M80 50 A30 20 0 1 0 20 50 A30 20 0 1 0 80 50 Z"/>',
            'quadratic':'<path d="M10 80Q50 -20 90 80Z"/>',
            'viewport':'<circle cx="0" cy="50" r="40"/>',
            'curved_dashes':'<path d="M10 80C20 0 80 0 90 80" fill="none" stroke="black" stroke-width="3" stroke-dasharray="9 5" stroke-linecap="round"/>',
        }
        for name,source in cases.items():
            with self.subTest(name=name): self.assert_roundtrip(source)

    def test_original_cubic_controls_and_no_raster_resolution(self):
        source='<path d="M10 70 C10 15 90 15 90 70 L10 70Z"/>'
        payload=self.convert_source(source)
        self.assertEqual(payload['engine'],'Skia PathKit 1.0.0 vector')
        self.assertNotIn('trace_edge',payload)
        curved=[k for k in payload['contours'][0] if any(k['right']) or any(k['left'])]
        self.assertEqual(len(curved),2)
        self.assertTrue(any(abs(v)==55 for k in curved for side in ['left','right'] for v in k[side]))

    def test_unsupported_soft_effects_report_errors(self):
        for body in ['<rect width="50" height="50" opacity=".5"/>',
                     '<defs><linearGradient id="a"><stop stop-color="black"/><stop offset="1" stop-color="white"/></linearGradient></defs><rect width="50" height="50" fill="url(#a)"/>',
                     '<defs><filter id="a"><feGaussianBlur stdDeviation="2"/></filter></defs><circle cx="50" cy="50" r="25" filter="url(#a)"/>']:
            with self.subTest(body=body),self.assertRaises(ValueError): self.convert_source(body)

    def test_stroke_clip_mask_and_roundtrip(self):
        fixture=Path(__file__).with_name('svg_import_fixture.svg')
        payload=converter.convert(fixture,2048)
        self.assertEqual(len(payload['contours']),5)
        bounds=converter.geometric_bounds(payload['contours'])
        self.assertAlmostEqual(bounds[0]+bounds[2],0,places=7)
        self.assertAlmostEqual(bounds[1]+bounds[3],0,places=7)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            svg=folder/'roundtrip.svg'
            svg.write_text(reconstructed(payload,200,120))
            original=render_bitmap(fixture,folder/'a.bin')
            rebuilt=render_bitmap(svg,folder/'b.bin')
            intersection=sum(bin(a&b).count('1') for a,b in zip(original,rebuilt))
            union=sum(bin(a|b).count('1') for a,b in zip(original,rebuilt))
            score=intersection/union
            print('Roundtrip silhouette IoU:',round(score,6))
            self.assertGreater(score,0.995)

    def test_white_overlay_cuts_black_and_transform(self):
        source='''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <g transform="translate(10 15)"><rect width="70" height="60" fill="black"/>
        <circle cx="35" cy="30" r="12" fill="white"/></g></svg>'''
        with tempfile.TemporaryDirectory() as folder:
            svg=Path(folder)/'белая маска.svg'; svg.write_text(source,encoding='utf-8')
            payload=converter.convert(svg,2048)
            self.assertEqual(payload['name'],'белая маска')
            self.assertEqual(len(payload['contours']),2)
            b=payload['bounds']
            for actual,expected in zip(b,(10,-75,80,-15)):
                self.assertAlmostEqual(actual,expected,delta=0.1)

    def test_white_or_hidden_artwork_is_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            svg=Path(folder)/'empty.svg'
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="white"/><circle display="none" r="5"/></svg>')
            with self.assertRaisesRegex(ValueError,'No visible black'):
                converter.convert(svg,512)

    def test_one_adaptive_spline_from_all_contours(self):
        class Vector:
            def __init__(self,x=0,y=0,z=0): self.x,self.y,self.z=x,y,z
            def __mul__(self,s): return Vector(self.x*s,self.y*s,self.z*s)
            def __sub__(self,b): return Vector(self.x-b.x,self.y-b.y,self.z-b.z)
            def Dot(self,b): return self.x*b.x+self.y*b.y+self.z*b.z
            def Cross(self,b): return Vector(self.y*b.z-self.z*b.y,self.z*b.x-self.x*b.z,self.x*b.y-self.y*b.x)
            def GetLength(self): return math.sqrt(self.Dot(self))
            def GetNormalized(self): return self*(1/self.GetLength())
        class Matrix:
            def __init__(self,off=None,x=None,y=None,z=None):
                self.off=off or Vector(); self.v1=x or Vector(1,0,0)
                self.v2=y or Vector(0,1,0); self.v3=z or Vector(0,0,1)
        class Spline(dict):
            def __init__(self,n,kind): self.n=n; self.kind=kind; self.segments=[]; self.tangents=[]
            def ResizeObject(self,n,s): return True
            def SetDefaultCoeff(self): pass
            def SetSegment(self,*args): self.segments.append(args)
            def SetTangent(self,*args): self.tangents.append(args)
            def SetAllPoints(self,points): self.points=points
            def SetName(self,name): self.name=name
            def SetMg(self,matrix): self.matrix=matrix
            def Message(self,*args): pass
        fake=types.ModuleType('c4d')
        fake.Vector=Vector; fake.Matrix=Matrix; fake.SplineObject=Spline
        fake.SPLINETYPE_BEZIER=4; fake.SPLINEOBJECT_CLOSED=1
        fake.SPLINEOBJECT_INTERPOLATION=2; fake.SPLINEOBJECT_INTERPOLATION_ADAPTIVE=3
        fake.MSG_UPDATE=4
        fake.plugins=types.SimpleNamespace(CommandData=object)
        fake.bitmaps=fake.gui=fake.storage=types.SimpleNamespace()
        old=sys.modules.get('c4d'); sys.modules['c4d']=fake
        try:
            module=runpy.run_path(str(ROOT/'svg_loader.pyp'),run_name='adapter_test')
            payload=json.loads(Path(__file__).with_name('svg_import_fixture.json').read_text())
            spline=module['build_spline'](payload)
            self.assertEqual(len(spline.segments),5)
            self.assertTrue(all(s[2] for s in spline.segments))
            self.assertEqual(spline[2],3)
            self.assertEqual(spline.name,'svg_import_fixture')
            self.assertTrue(all(p.y==0 for p in spline.points))
            self.assertEqual(len(spline.tangents),spline.n)
            self.assertEqual(spline.matrix.v1.y,-1)
            self.assertEqual(spline.matrix.v2.z,-1)
            self.assertEqual(spline.matrix.v3.x,1)
            for actual,knot in zip(spline.points,[k for c in payload['contours'] for k in c]):
                self.assertAlmostEqual(actual.z,knot['p'][0])
                self.assertAlmostEqual(-actual.x,knot['p'][1])
            # Check effective C4D cubic controls, not merely stored point positions.
            # Cinema evaluates stored tangents with a 4/3 multiplier.
            for (_,left,right),k in zip(spline.tangents,[k for c in payload['contours'] for k in c]):
                for actual,key in [(left,'left'),(right,'right')]:
                    self.assertAlmostEqual(actual.z*4/3,k[key][0])
                    self.assertAlmostEqual(-actual.x*4/3,k[key][1])
                    self.assertEqual(actual.y,0)
            circle=self.convert_source('<circle cx="50" cy="50" r="35"/>')
            native=module['build_spline'](circle)
            for i,a in enumerate(native.points):
                j=(i+1)%len(native.points);b=native.points[j]
                outgoing=native.tangents[i][2]*(4/3)
                incoming=native.tangents[j][1]*(4/3)
                for t in (.125,.25,.5,.75,.875):
                    u=1-t
                    coords=[u**3*getattr(a,axis)+3*u*u*t*(getattr(a,axis)+getattr(outgoing,axis))+
                            3*u*t*t*(getattr(b,axis)+getattr(incoming,axis))+t**3*getattr(b,axis)
                            for axis in ('x','y','z')]
                    self.assertAlmostEqual(math.sqrt(sum(v*v for v in coords)),35,delta=.011)
        finally:
            if old is None: sys.modules.pop('c4d',None)
            else: sys.modules['c4d']=old


if __name__=='__main__': unittest.main()
