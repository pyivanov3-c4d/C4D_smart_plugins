"""Reproducible vector icon and offline geometry contact sheet (Pillow test dependency)."""
from pathlib import Path
import sys
import math
from PIL import Image, ImageDraw
from test_metaspline import circle, run, points
import metaspline_geometry as g
ROOT=Path(__file__).resolve().parents[1]
res=ROOT/'Metaspline/res'
art=ROOT/'artifacts/metaspline'
art.mkdir(parents=True,exist_ok=True)
blue=(1,152,252,255)
# Analytic blended circles on a 512-unit icon grid, then a vector outline.
w=257; step=2
field=[]
for y in range(w):
    for x in range(w):
        a=math.hypot(x*step-202,y*step-310)-139
        b=math.hypot(x*step-348,y*step-164)-96
        k=80; h=max(0,1-abs(a-b)/k)
        field.append(min(a,b)-k*h*h*.25)
ring=max(g.contours(field,w,w,(0,0),step,lambda:None),key=len)
ring=g.smooth_ring(ring,.035,2)
path='M '+' L '.join('{:.3f},{:.3f}'.format(x,y) for x,y in ring)+' Z'
(res/'icon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path d="'+path+'" fill="none" stroke="#0198FC" stroke-width="30" stroke-linejoin="round"/></svg>')
im=Image.new('RGBA',(2048,2048)); d=ImageDraw.Draw(im)
d.line([(round(x*4),round(y*4)) for x,y in ring+[ring[0]]],fill=blue,width=120,joint='curve')
im=im.resize((512,512),Image.Resampling.LANCZOS); im.save(res/'icon.png')
preview=Image.new('RGB',(760,260),(34,37,43)); d=ImageDraw.Draw(preview)
for x,size in ((30,192),(260,96),(400,48),(500,32),(600,16)):
    thumb=im.resize((size,size),Image.Resampling.LANCZOS); preview.paste(thumb,(x,35),thumb)
    d.text((x,230),str(size)+' px',fill='white')
preview.save(art/'icon-sizes.png')
sheet=Image.new('RGB',(1200,760),(26,29,35)); d=ImageDraw.Draw(sheet)
for i,(gap,label) in enumerate(((-20,'Intersecting: union'),(15,'Gap 15: welded'),(25,'Gap 25: attraction'),(40,'Gap 40: attraction'),(65,'Gap 65: unchanged'),(5,'Gap 5: Smooth 60%'))):
    ox=(i%3)*400+55; oy=(i//3)*360+180; scale=1.15
    groups=[[circle()],[circle(100+gap)]]
    def paint(paths,color,width,sampled=False):
        for curves,closed in paths:
            pts=g.flatten(curves,.02,lambda:None) if sampled else [c[0] for c in curves]
            xy=[(ox+(p[0]+50)*scale,oy-p[1]*scale) for p in pts]
            d.line(xy+xy[:1],fill=color,width=width)
    paint([g for group in groups for g in group],(90,94,105),1,True)
    paint(run(groups,s=.6 if i==5 else 0),blue[:3],3,True)
    d.text((i%3*400+24,i//3*360+30),label,fill='white')
d.text((24,735),'Collapse 20 / Fallow 40. Gray: source cubic circles. Blue: kernel output. Offline preview, not a C4D viewport.',fill='white')
sheet.save(art/'geometry-checks.png')
