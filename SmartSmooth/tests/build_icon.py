"""Reproducible vector icon, with a supersampled transparent PNG."""
from pathlib import Path
from PIL import Image
import aggdraw

res = Path(__file__).resolve().parents[1] / 'res'
faces = [
    ('#0198FC', 'M 58 154 C 92 94 175 56 251 49 C 329 57 415 93 454 153 C 415 207 334 241 256 250 C 173 240 98 210 58 154 Z'),
    ('#0186E0', 'M 58 154 C 98 210 173 240 256 250 C 275 319 273 408 251 464 C 164 454 94 409 65 342 C 48 285 46 211 58 154 Z'),
    ('#0174C5', 'M 256 250 C 334 241 415 207 454 153 C 469 213 466 286 448 343 C 414 411 336 455 251 464 C 273 408 275 319 256 250 Z'),
]
edges = [
    'M 58 154 C 98 210 173 240 256 250 C 334 241 415 207 454 153',
    'M 256 250 C 275 319 273 408 251 464',
]
svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
svg += ''.join('<path fill="{}" d="{}"/>'.format(c, p) for c, p in faces)
svg += ''.join('<path fill="none" stroke="white" stroke-width="3" stroke-linecap="round" d="{}"/>'.format(p) for p in edges)
svg += '</svg>'
(res / 'icon.svg').write_text(svg)
im = Image.new('RGBA', (2048, 2048))
ctx = aggdraw.Draw(im)
def path(s):
    tokens = s.split(); p = aggdraw.Path(); i = 0
    while i < len(tokens):
        cmd = tokens[i]; i += 1
        n = {'M': 2, 'C': 6, 'Z': 0}[cmd]
        a = [float(v)*4 for v in tokens[i:i+n]]; i += n
        if cmd == 'M': p.moveto(*a)
        elif cmd == 'C': p.curveto(*a)
        else: p.close()
    return p
for color, shape in faces: ctx.path(path(shape), aggdraw.Brush(color))
for shape in edges: ctx.path(path(shape), None, aggdraw.Pen('white', 12))
ctx.flush()
im.resize((512,512), Image.Resampling.LANCZOS).save(res / 'icon.png')
