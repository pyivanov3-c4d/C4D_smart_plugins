from pathlib import Path
from PIL import Image,ImageDraw
from test_metaspline import circle
import metaspline_geometry as g
im=Image.new('RGB',(1500,340),'white');d=ImageDraw.Draw(im)
for i,(gap,label) in enumerate(((100,'1. Separate'),(35,'2. Bulging'),(19.5,'3. Thin neck'),(8,'4. Thickening'),(-5,'5. Smooth merge'))):
    x=i*300+65;y=145;groups=[[circle(r=45)],[circle(65+gap,r=20)]]
    for cx,radius in ((0,45),(65+gap,20)):
        d.ellipse((x+cx-radius,y-radius,x+cx+radius,y+radius),fill=(235,25,30))
    paths,status=g.process(groups,20,60,0,g.WorkBudget(30))
    for curves,_ in paths:
        points=[g.cubic(c,j/32) for c in curves for j in range(32)]
        xy=[(x+p[0],y-p[1]) for p in points]
        d.line(xy+xy[:1],fill=(15,85,130),width=2)
    d.text((i*300+16,25),label,fill='black')
    d.text((i*300+16,285),'Gap '+str(gap)+' / '+str(len(paths))+' contour(s)',fill='black')
    d.line((i*300,0,i*300,310),fill=(180,180,180),width=2)
d.text((16,320),'Fixed controls: Collapse 20, Fallow 60, Smooth 0%. Only source separation changes. Offline vector preview.',fill='black')
im.save(Path(__file__).resolve().parents[1]/'artifacts/metaspline/progressive-neck-2.1.0.png')
