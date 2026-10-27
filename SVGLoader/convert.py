"""Vector-only SVG conversion: usvg normalization and Skia curve Booleans."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent


def geometric_bounds(contours):
    bounds=[float('inf'),float('inf'),float('-inf'),float('-inf')]
    for knots in contours:
        for index,knot in enumerate(knots):
            following=knots[(index+1)%len(knots)]
            for axis in (0,1):
                p0=knot['p'][axis]; p1=p0+knot['right'][axis]
                p3=following['p'][axis]; p2=p3+following['left'][axis]
                a=-p0+3*p1-3*p2+p3; b=2*(p0-2*p1+p2); c=p1-p0
                ts=[0.,1.]
                if abs(a)<1e-14:
                    if abs(b)>1e-14: ts.append(-c/b)
                else:
                    discriminant=b*b-4*a*c
                    if discriminant>=0:
                        ts.extend(((-b+math.sqrt(discriminant))/(2*a),(-b-math.sqrt(discriminant))/(2*a)))
                for t in ts:
                    if 0<=t<=1:
                        v=(1-t)**3*p0+3*(1-t)**2*t*p1+3*(1-t)*t*t*p2+t**3*p3
                        bounds[axis]=min(bounds[axis],v)
                        bounds[axis+2]=max(bounds[axis+2],v)
    return bounds


def commands_to_contours(commands):
    """Preserve cubic controls; elevate quadratics and adapt rational conics.

    C4D uses polynomial cubics, so rational round caps require a bounded vector
    approximation. This never samples an image or substitutes a polygon.
    """
    contours=[]; knots=[]
    def point(x,y): return [x,-y]
    def knot(p): return {'p':p,'left':[0.,0.],'right':[0.,0.]}
    def append(p,c1=None,c2=None):
        if c1 is not None:
            knots[-1]['right']=[c1[i]-knots[-1]['p'][i] for i in (0,1)]
        k=knot(p)
        if c2 is not None: k['left']=[c2[i]-p[i] for i in (0,1)]
        knots.append(k)
    def finish():
        if len(knots)>1:
            if math.dist(knots[0]['p'],knots[-1]['p'])<1e-7:
                knots[0]['left']=knots[-1]['left'];knots.pop()
            if len(knots)>=2: contours.append(knots[:])
        knots.clear()
    for cmd in commands:
        verb=cmd[0]
        if verb==0:
            finish();knots.append(knot(point(*cmd[1:3])))
        elif verb==1: append(point(*cmd[1:3]))
        elif verb==4: append(point(*cmd[5:7]),point(*cmd[1:3]),point(*cmd[3:5]))
        elif verb==2:
            p0=knots[-1]['p'];q=point(*cmd[1:3]);p=point(*cmd[3:5])
            append(p,[(p0[i]+2*q[i])/3 for i in (0,1)],[(p[i]+2*q[i])/3 for i in (0,1)])
        elif verb==3:
            p0=knots[-1]['p'];p1=point(*cmd[1:3]);p2=point(*cmd[3:5]);w=cmd[5]
            def evaluate(t):
                u=1-t;d=u*u+2*w*u*t+t*t;dd=2*(w-1)*(1-2*t)
                n=[u*u*p0[i]+2*w*u*t*p1[i]+t*t*p2[i] for i in (0,1)]
                dn=[-2*u*p0[i]+2*w*(1-2*t)*p1[i]+2*t*p2[i] for i in (0,1)]
                return [v/d for v in n],[(dn[i]*d-n[i]*dd)/(d*d) for i in (0,1)]
            tolerance=max(1e-7,math.dist(p0,p2)*1e-6)
            def segment(a,b,depth=0):
                pa,da=evaluate(a);pb,db=evaluate(b);dt=(b-a)/3
                c1=[pa[i]+dt*da[i] for i in (0,1)];c2=[pb[i]-dt*db[i] for i in (0,1)]
                error=0
                for t in (.125,.25,.5,.75,.875):
                    u=1-t
                    cubic=[u**3*pa[i]+3*u*u*t*c1[i]+3*u*t*t*c2[i]+t**3*pb[i] for i in (0,1)]
                    error=max(error,math.dist(cubic,evaluate(a+(b-a)*t)[0]))
                if error>tolerance and depth<16:
                    mid=(a+b)/2;segment(a,mid,depth+1);segment(mid,b,depth+1)
                else: append(pb,c1,c2)
            segment(0,1)
        elif verb==5: finish()
        else: raise ValueError('Unsupported vector path verb: '+str(verb))
    finish()
    if sum(map(len,contours))>200000: raise ValueError('SVG produces too many contour points.')
    return contours


def orient_contours(contours):
    """Convert Skia's even-odd output to opposite winding for C4D holes.

    Classify nesting with curve/ray intersections; control points stay untouched.
    """
    def controls(c):
        return [[k['p'],[k['p'][a]+k['right'][a] for a in (0,1)],
                 [c[(i+1)%len(c)]['p'][a]+c[(i+1)%len(c)]['left'][a] for a in (0,1)],
                 c[(i+1)%len(c)]['p']] for i,k in enumerate(c)]
    def value(p,t,axis):
        u=1-t
        return u**3*p[0][axis]+3*u*u*t*p[1][axis]+3*u*t*t*p[2][axis]+t**3*p[3][axis]
    def inside(point,curves):
        hits=0;x,y=point
        for p in curves:
            v=[q[1] for q in p]
            a=-v[0]+3*v[1]-3*v[2]+v[3];b=2*(v[0]-2*v[1]+v[2]);c=v[1]-v[0]
            cuts=[0.,1.]
            if abs(a)<1e-14:
                if abs(b)>1e-14: cuts.append(-c/b)
            elif b*b-4*a*c>=0:
                d=math.sqrt(b*b-4*a*c);cuts.extend(((-b-d)/(2*a),(-b+d)/(2*a)))
            cuts=sorted(t for t in cuts if 0<=t<=1)
            for lo,hi in zip(cuts,cuts[1:]):
                ylo=value(p,lo,1);yhi=value(p,hi,1)
                if (ylo>y)==(yhi>y): continue
                ascending=yhi>ylo
                for _ in range(45):
                    mid=(lo+hi)/2
                    if (value(p,mid,1)<y)==ascending: lo=mid
                    else: hi=mid
                if value(p,(lo+hi)/2,0)>x: hits+=1
        return hits%2==1
    curves=[controls(c) for c in contours]
    bounds=[geometric_bounds([c]) for c in contours]
    # Five-point Gauss integration exactly integrates a cubic's signed area.
    quadrature=[(.5,.5688888888888889),(.23076534494715845,.4786286704993665),
                (.7692346550528415,.4786286704993665),(.046910077030668,.2369268850561891),
                (.953089922969332,.2369268850561891)]
    for i,contour in enumerate(contours):
        p=curves[i][0];probe=[value(p,.371,a) for a in (0,1)]
        depth=sum(inside(probe,other) for j,other in enumerate(curves) if j!=i and
                  bounds[j][0]<=probe[0]<=bounds[j][2] and bounds[j][1]<=probe[1]<=bounds[j][3])
        area=0
        for p in curves[i]:
            for t,w in quadrature:
                dy=3*((1-t)**2*(p[1][1]-p[0][1])+2*(1-t)*t*(p[2][1]-p[1][1])+t*t*(p[3][1]-p[2][1]))
                area+=w*value(p,t,0)*dy
        if (area>0)!=(depth%2==0):
            contour.reverse()
            for k in contour: k['left'],k['right']=k['right'],k['left']


def convert(filename, edge=None):
    # edge is accepted only for compatibility; vector output has no raster resolution.
    def run(script,*args):
        result=subprocess.run([str(ROOT/'vendor'/'node.exe'),str(ROOT/script),*map(str,args)],
            capture_output=True,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode: raise ValueError(result.stderr.decode('utf-8',errors='replace')[-2500:])
    def tree(node):
        return {'tag':node.tag.rsplit('}',1)[-1],'a':dict(node.attrib),'children':[tree(c) for c in node]}
    with tempfile.TemporaryDirectory(prefix='c4d-svg-vector-') as folder:
        folder=Path(folder);normalized=folder/'normalized.svg';source=folder/'tree.json';output=folder/'curves.json'
        run('normalize.cjs',Path(filename).resolve(),normalized)
        source.write_text(json.dumps(tree(ET.parse(normalized).getroot())),encoding='utf-8')
        run('vector.cjs',source,output)
        result=json.loads(output.read_text(encoding='utf-8'))
    contours=commands_to_contours(result['commands'])
    if not contours: raise ValueError('No visible black artwork was found in this SVG.')
    orient_contours(contours)
    bounds=geometric_bounds(contours)
    center=[(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2]
    for contour in contours:
        for k in contour: k['p']=[k['p'][i]-center[i] for i in (0,1)]
    return {'name':Path(filename).stem,'contours':contours,'bounds':bounds,'engine':result['engine']}


if __name__=='__main__':
    try:
        payload=convert(sys.argv[1])
        Path(sys.argv[2]).write_text(json.dumps(payload),encoding='utf-8')
    except Exception as error:
        print(str(error),file=sys.stderr);sys.exit(1)


