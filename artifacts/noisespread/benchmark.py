"""Unprofiled paired benchmark; old and new use identical inputs and search budgets."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import statistics
import time
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline',type=Path,required=True,help='Path to noisespread_geometry.py from version 1.0.2')
args=parser.parse_args()
old=load('old',args.baseline)
new=load('new',ROOT/'NoiseSpread/noisespread_geometry.py')
def sphere():
    result=[]
    def p(i,j):
        u=i*math.pi/16; v=j*math.tau/32
        return (80*math.sin(u)*math.cos(v),80*math.cos(u),80*math.sin(u)*math.sin(v))
    for i in range(16):
        for j in range(32):
            a,b,c,d=p(i,j),p(i+1,j),p(i+1,j+1),p(i,j+1)
            result.extend(((a,b,c),(a,c,d)))
    return result
plane=[((-100,0,-100),(-100,0,100),(100,0,100)),((-100,0,-100),(100,0,100),(100,0,-100))]
cases=[('flat_uniform',plane,0.),('curved_uniform',sphere(),0.),('curved_noise',sphere(),.4)]
report=[]
for name,triangles,feather in cases:
    times={'before':[],'after':[]}; outputs={}
    for trial in range(3):
        for label,module in (('before',old),('after',new)):
            start=time.perf_counter()
            surface=module.Surface(triangles)
            items,status=module.pack(surface,[8.],lambda h:(h[0][1]+80)/160,feather=feather,attempts=12000)
            times[label].append(time.perf_counter()-start); outputs[label]=items
    a,b=outputs['before'],outputs['after']
    assert len(a)==len(b),(name,len(a),len(b))
    error=max(abs(x-y) for left,right in zip(a,b) for x,y in zip(left[0],right[0]))
    assert error<1e-8,(name,error)
    assert all(x[1:]==y[1:] for x,y in zip(a,b)),name
    before=statistics.median(times['before']); after=statistics.median(times['after'])
    row=dict(case=name,instances=len(b),before_seconds=round(before,4),after_seconds=round(after,4),speedup=round(before/after,2),max_position_difference=error)
    report.append(row); print(json.dumps(row),flush=True)
(ROOT/'artifacts/noisespread/benchmark-results.json').write_text(json.dumps(report,indent=2))
