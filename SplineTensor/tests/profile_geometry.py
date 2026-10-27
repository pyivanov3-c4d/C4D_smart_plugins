import sys,json,time,cProfile,pstats,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from st_union import unite_contours
from st_clip import build_clipped
root=Path(__file__).parents[1]
data=json.loads((root/'tests/mask-host-input.json').read_text());base=data[0]['loops'][0];loops=data[1]['loops']
contours=unite_contours(base,loops,nested_masks=True)
def run():return build_clipped(base,contours,5,3,closed=False,quad_bands=True,quality=True,return_edges=True)
t=time.perf_counter();r=run();print('BASELINE SECONDS',time.perf_counter()-t,flush=True)
(root/'tests/perf-baseline.json').write_text(json.dumps(r))
p=cProfile.Profile();p.enable();run();p.disable();s=io.StringIO();pstats.Stats(p,stream=s).sort_stats('cumtime').print_stats(20);print(s.getvalue(),flush=True)
