from pathlib import Path
from PIL import Image, ImageDraw
import math
root=Path(__file__).resolve().parents[2]/'NoiseSpread/res'
circles=[(160,220,110),(350,220,80)]
for radius,side in ((60,1),(40,-1)):
    d=190; a=110+radius; b=80+radius
    x=(a*a-b*b+d*d)/(2*d)
    circles.append((160+x,220+side*math.sqrt(a*a-x*x),radius))
svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">\n'
for x,y,r in circles:
    svg+=f'<circle cx="{x:.5f}" cy="{y:.5f}" r="{r}" fill="#0198FC"/>\n'
svg+='</svg>\n'
(root/'icon.svg').write_text(svg)
image=Image.new('RGBA',(2048,2048)); draw=ImageDraw.Draw(image)
for x,y,r in circles:
    draw.ellipse(tuple(round(v*4) for v in (x-r,y-r,x+r,y+r)),fill=(1,152,252,255))
image.resize((512,512),Image.Resampling.LANCZOS).save(root/'icon.png')
