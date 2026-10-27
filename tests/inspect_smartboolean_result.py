import json
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw
root=Path(__file__).resolve().parents[1]
m=json.loads((root/'artifacts/smartBoolean/clean-bevel-mesh.json').read_text())
p,f=m['points'],m['polygons']
counts=Counter(tuple(sorted((a,b))) for poly in f for a,b in zip(poly,poly[1:]+poly[:1]))
assert set(counts.values())=={2},Counter(counts.values())
im=Image.new('RGB',(1100,1000),'#eeeeee')
draw=ImageDraw.Draw(im)
def project(v):
    x,y,z=v; x-=52; y-=52; z+=100
    return (550+9*(x-y),520+5*(x+y)+10*z)
faces=[]
for poly in f:
    pts=[p[v] for v in poly]
    if all(20<x<82 and 20<y<82 and -133<z<-78 for x,y,z in pts): faces.append(pts)
for pts in sorted(faces,key=lambda ps:sum(v[0]+v[1]-v[2] for v in ps)/len(ps)):
    draw.polygon([project(v) for v in pts],fill='#b8c1c9',outline='#30343a')
im.save(root/'artifacts/smartBoolean/clean-bevel-check.png')
print('Watertight result:',len(p),'points;',len(f),'faces; all edges have exactly two incident faces.')
