"""Plot the actual sampled C4D Text outline and its shortest fillet constraint."""
import json, math, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ChamferPro'))
import chamfer_geometry as g
data=json.loads((ROOT/'tests/chamfer_current_text_points.json').read_text())
paths=[]; start=0
for seg in data['segments']:
    p=data['points'][start:start+seg['count']]; start+=seg['count']
    paths.append(p)
limits=[]
for si,p in enumerate(paths):
    coeff=[]
    for i,q in enumerate(p):
        ti=g.sub(q,p[i-1]); to=g.sub(p[(i+1)%len(p)],q)
        opening=g.corner_angle(ti,to); turn=g.angle(ti,to)
        coeff.append(math.tan(turn/2) if opening+1e-9>=math.radians(89) and turn>math.radians(.05) else 0)
    for i,q in enumerate(p):
        j=(i+1)%len(p); size=g.length(g.sub(p[j],q)); total=coeff[i]+coeff[j]
        if total: limits.append((size/total,si,i,j,size))
limits.sort()
print('Shortest finite-edge constraints:',limits[:5])
curves=[([g.line(a,b) for a,b in zip(p,p[1:]+p[:1])],True) for p in paths]
_,report=g.round_paths_uniform(curves,100,math.radians(89))
print('Sampled-outline solver:',report)

from PIL import Image, ImageDraw, ImageFont
im=Image.new('RGB',(1500,1000),'#181d25'); d=ImageDraw.Draw(im)
font=lambda n:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n)
blue='#0198FC'; yellow='#ffcf4d'; white='#eef4fc'; muted='#a6b4c6'
d.text((55,35),'The feature behind the former Text radius limit',font=font(38),fill=white)
d.text((55,90),'Your C4D outline  |  angle limit 89 degrees  |  requested radius 100',font=font(23),fill=muted)
def project(p): return (85+p[0]*3.7,690-p[1]*3.7)
for p in paths: d.line([project(q) for q in p+p[:1]],fill=blue,width=3)
r,si,i,j,size=limits[0]; p=paths[si]
for _,sj,a,b,sz in limits:
    if abs(sz-size)>1e-8: continue
    x,y=project(g.mix(paths[sj][a],paths[sj][b],.5))
    d.ellipse((x-15,y-15,x+15,y+15),outline=yellow,width=4)
mid=g.mix(p[i],p[j],.5)
x,y=project(mid)
d.line([(1130,175),(x+12,y-16)],fill=yellow,width=4)
d.text((860,135),'Limiting flat tip in the x',font=font(26),fill=yellow)
# A geometrically faithful zoom around the limiting edge.
box=(70,740,620,960); d.rounded_rectangle(box,14,fill='#232d3b')
def zoom(q): return (345+(q[0]-mid[0])*750,845-(q[1]-mid[1])*750)
# Clip lines in a separate canvas so distant adjacent vertices do not escape.
panel=Image.new('RGB',(550,220),'#232d3b'); pd=ImageDraw.Draw(panel)
coords=[(zoom(p[k%len(p)])[0]-70,zoom(p[k%len(p)])[1]-740) for k in (i-1,i,j,j+1)]
pd.line(coords,fill=blue,width=5)
pd.line(coords[1:3],fill=yellow,width=6)
for xx,yy in coords[1:3]: pd.ellipse((xx-7,yy-7,xx+7,yy+7),fill=yellow)
im.paste(panel,(70,740))
d.text((85,750),'Magnified flat tip',font=font(22),fill=white)
d.text((655,755),f'Flat edge: {size:.6f} units',font=font(29),fill=yellow)
d.text((655,805),f'Former sampled radius cap: {r:.6f}',font=font(29),fill=white)
d.text((655,853),'The two corner rounds meet on this tiny edge.',font=font(23),fill=muted)
d.text((655,890),'The other marked tip has a similar limit (0.342).',font=font(23),fill=muted)
d.text((655,927),'Diagram from sampled C4D geometry; not a viewport screenshot.',font=font(18),fill=muted)
out=ROOT/'artifacts'; out.mkdir(exist_ok=True)
im.save(out/'chamfer-text-radius-limit.png')
print(out/'chamfer-text-radius-limit.png')
