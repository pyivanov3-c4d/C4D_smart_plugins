"""Offline vector-kernel previews; Pillow is a test-only dependency."""
from pathlib import Path
from PIL import Image, ImageDraw
from test_metaspline import circle, run
import metaspline_geometry as g
ROOT=Path(__file__).resolve().parents[1]
art=ROOT/'artifacts/metaspline';art.mkdir(parents=True,exist_ok=True)
im=Image.new('RGB',(1440,820),(26,29,35));d=ImageDraw.Draw(im)
cases=[('1. Overlap union',[[circle()],[circle(80)]],0,0,0),
       ('2. Collapse bridge',[[circle()],[circle(115)]],20,0,0),
       ('3. Fallow smoothing',[[circle()],[circle(155)]],20,100,0),
       ('4. Unequal outlines',[[circle(0,30,35)],[circle(185,-25,90)]],20,300,0),
       ('5. Hole preserved',[[circle(r=70),circle(r=25)],[circle(105)]],10,15,0),
       ('6. Smooth 100%',[[circle()],[circle(115)]],20,40,1)]
for i,(label,groups,c,f,s) in enumerate(cases):
    ox=(i%3)*480+90;oy=(i//3)*390+200
    def paint(paths,color,width):
        for curves,closed in paths:
            pts=[g.cubic(curve,j/40) for curve in curves for j in range(40)]
            xy=[(ox+p[0],oy-p[1]) for p in pts]
            d.line(xy+xy[:1],fill=color,width=width)
    paint([p for group in groups for p in group],(110,114,125),1)
    result,status=g.process(groups,c,f,s,g.WorkBudget(30))
    paint(result,(1,152,252),3)
    d.text((i%3*480+24,i//3*390+25),label,fill='white')
    d.text((i%3*480+24,i//3*390+350),str(sum(len(curves) for curves,_ in result))+' Bezier knots / '+str(len(result))+' contours',fill='white')
d.text((24,800),'Vector 2.0.0: gray sources, blue output. Offline preview, not a C4D viewport.',fill='white')
im.save(art/'vector-pipeline-2.0.0.png')
