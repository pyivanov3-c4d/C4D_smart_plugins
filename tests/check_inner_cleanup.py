import json,math,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'ChamferPro'))
import chamfer_geometry as g
cases=json.loads((root/'tests/chamfer_text_outlines.json').read_text())
for name,paths in cases.items():
    for radius in (5,100):
        start=time.monotonic()
        result,report=g.round_paths_fixed(paths,radius,math.radians(30),g.WorkBudget(2))
        for curves,closed in result:
            for a,b in zip(curves,curves[1:]+curves[:1] if closed else curves[1:]):
                assert g.length(g.sub(a[3],b[0]))<1e-5
        print(name,radius,round(time.monotonic()-start,3),report)
