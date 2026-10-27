"""Export a real font outline fixture; fontTools is a test-only dependency."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backups/chamfer-test-deps'))
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen


class CubicPen(BasePen):
    def __init__(self, glyphs, scale, offset):
        super().__init__(glyphs)
        self.scale, self.offset = scale, offset
        self.contours, self.curves, self.current = [], [], None

    def p(self, p): return ((p[0]+self.offset)*self.scale, p[1]*self.scale, 0.)
    def _moveTo(self, p): self.current, self.curves = self.p(p), []
    def _lineTo(self, p):
        end = self.p(p)
        a = tuple((2*x+y)/3 for x,y in zip(self.current,end))
        b = tuple((x+2*y)/3 for x,y in zip(self.current,end))
        self.curves.append((self.current,a,b,end))
        self.current = end

    def _curveToOne(self,a,b,end):
        self.curves.append((self.current,self.p(a),self.p(b),self.p(end)))
        self.current = self.p(end)

    def _qCurveToOne(self,control,end):
        control, end = self.p(control), self.p(end)
        a = tuple((x+2*y)/3 for x,y in zip(self.current,control))
        b = tuple((x+2*y)/3 for x,y in zip(end,control))
        self.curves.append((self.current,a,b,end))
        self.current = end

    def _closePath(self):
        if self.curves and self.current != self.curves[0][0]:
            end = self.curves[0][0]
            a = tuple((2*x+y)/3 for x,y in zip(self.current,end))
            b = tuple((x+2*y)/3 for x,y in zip(self.current,end))
            self.curves.append((self.current,a,b,end))
        if self.curves: self.contours.append((self.curves,True))
        self.curves = []

    def _endPath(self):
        if self.curves: self.contours.append((self.curves,False))
        self.curves = []


def main():
    font = TTFont('C:/Windows/Fonts/arial.ttf')
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    result = {}
    for text in ('chamferPro','TEXT SPLINE','ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'):
        offset, paths = 0, []
        for char in text:
            name = cmap[ord(char)]
            pen = CubicPen(glyphs,200/font['head'].unitsPerEm,offset)
            glyphs[name].draw(pen)
            paths.extend(pen.contours)
            offset += glyphs[name].width
        result[text] = paths
    (ROOT/'tests/chamfer_text_outlines.json').write_text(json.dumps(result),encoding='utf-8')


if __name__ == '__main__': main()
