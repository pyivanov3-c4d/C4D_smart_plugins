"""Vector master plus supersampled PNG for the Cinema 4D plugin icon."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / 'smartBoolean' / 'res'
RES.mkdir(parents=True, exist_ok=True)
# Two offset square planes. The white plane removes the blue upper-right corner.
blue = [(48, 188), (236, 188), (236, 284), (324, 284), (324, 464), (48, 464)]
white = [(236, 48), (464, 48), (464, 284), (236, 284), (236, 48)]
RES.joinpath('icon.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<path d="M48 188H236V284H324V464H48Z" fill="#0198FC"/>
<path d="M236 48H464V284H236Z" fill="none" stroke="#FFFFFF" stroke-width="28" stroke-linejoin="miter"/>
</svg>''', encoding='utf-8')
im = Image.new('RGBA', (2048, 2048))
d = ImageDraw.Draw(im)
d.polygon([(x*4, y*4) for x,y in blue], fill=(1,152,252,255))
d.line([(x*4, y*4) for x,y in white], fill='white', width=112)
im = im.resize((512,512), Image.Resampling.LANCZOS)
im.save(RES / 'icon.png')
preview = Image.new('RGB', (620,220), (44,46,50))
for x,size in ((12,192),(228,96),(354,48),(444,32),(524,16)):
    tile=im.resize((size,size),Image.Resampling.LANCZOS)
    preview.paste(tile,(x,(220-size)//2),tile)
out=ROOT/'artifacts'/'smartBoolean'
out.mkdir(parents=True,exist_ok=True)
preview.save(out/'icon-preview.png')
