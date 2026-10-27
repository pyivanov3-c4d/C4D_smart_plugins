import random,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'smartBoolean'))
from smartboolean_spatial import BoxIndex,bounds,overlaps

class SpatialTests(unittest.TestCase):
    def test_candidates_match_brute_force_including_touching_and_long_boxes(self):
        rng=random.Random(116)
        boxes=[bounds([rng.uniform(-100,100) for _ in range(3)],
                      [rng.uniform(-100,100) for _ in range(3)]) for i in range(200)]
        boxes += [bounds((0,0,0),(0,0,0)),bounds((-1e10,0,0),(1e10,0,0))]
        index=BoxIndex(boxes)
        for query in boxes+[bounds((0,0,0),(0,0,0))]:
            self.assertEqual(index.query(query),[i for i,b in enumerate(boxes) if overlaps(b,query)])
        self.assertEqual(BoxIndex([]).query(boxes[0]),[])
